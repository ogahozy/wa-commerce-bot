import os
import logging
import httpx
import asyncio
import json
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from contextlib import asynccontextmanager

from order_engine import get_bot_reply, get_product_by_id, get_greeting

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "davids_commerce_token")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "")
RENDER_URL = os.getenv("RENDER_URL", "https://wa-commerce-bot.onrender.com")
OWNER_NUMBER = os.getenv("OWNER_NUMBER", "")  # business owner's WhatsApp number to notify

# In-memory conversation store: {customer_number: [{"role":..., "content":...}]}
CONVERSATIONS = {}
SEEN_MESSAGE_IDS = set()


async def keep_alive():
    await asyncio.sleep(60)
    while True:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{RENDER_URL}/ping", timeout=10)
                logger.info(f"Keep-alive ping: {r.status_code}")
        except Exception as e:
            logger.warning(f"Keep-alive failed: {e}")
        await asyncio.sleep(240)


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(keep_alive())
    yield


app = FastAPI(title="WA Commerce Bot", lifespan=lifespan)


@app.get("/")
async def root():
    return {"status": "WA Commerce Bot is running"}


@app.get("/ping")
async def ping():
    return {"status": "alive"}


@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    mode = params.get("hub.mode") or params.get("hub_mode")
    token = params.get("hub.verify_token") or params.get("hub_verify_token")
    challenge = params.get("hub.challenge") or params.get("hub_challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("Verified successfully")
        return PlainTextResponse(content=challenge, status_code=200)
    return PlainTextResponse(content="Forbidden", status_code=403)


@app.post("/webhook")
async def receive_message(request: Request):
    body = await request.json()

    try:
        entry = body["entry"][0]
        value = entry["changes"][0]["value"]

        if "statuses" in value:
            return {"status": "ok"}

        messages = value.get("messages", [])
        if not messages:
            return {"status": "ok"}

        message = messages[0]
        message_id = message.get("id")

        # Dedup
        if message_id in SEEN_MESSAGE_IDS:
            return {"status": "ok"}
        SEEN_MESSAGE_IDS.add(message_id)

        from_number = message["from"]
        msg_type = message.get("type", "text")

        if msg_type != "text":
            await send_reply(from_number, "We currently only understand text messages. Please type your question or order 🙏")
            return {"status": "ok"}

        text = message["text"]["body"]
        logger.info(f"From {from_number}: {text}")

        # Get or create conversation history
        history = CONVERSATIONS.get(from_number, [])

        # First message ever from this customer -> send greeting first
        if not history:
            greeting = get_greeting()
            await send_reply(from_number, greeting)
            history.append({"role": "assistant", "content": greeting})

        # Get bot reply
        reply, order_data = get_bot_reply(history, text)

        # Update conversation history
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": reply})
        CONVERSATIONS[from_number] = history[-20:]  # keep last 20 messages

        await send_reply(from_number, reply)

        # If order is ready, notify owner and customer
        if order_data:
            await handle_completed_order(from_number, order_data)

    except Exception as e:
        logger.error(f"Error processing message: {e}")

    return {"status": "ok"}


async def handle_completed_order(customer_number: str, order_data: dict):
    """When an order is finalized, notify the owner and confirm with customer."""
    product_id = order_data.get("product_id", "")
    product = get_product_by_id(product_id)

    product_name = product["name"] if product else product_id
    price = product["price"] if product else 0
    quantity = order_data.get("quantity", "1")
    size = order_data.get("size", "N/A")
    color = order_data.get("color", "N/A")
    address = order_data.get("address", "N/A")

    try:
        qty_num = int(quantity)
    except Exception:
        qty_num = 1

    total = price * qty_num

    order_summary = (
        f"🛍️ NEW ORDER\n"
        f"Customer: wa.me/{customer_number}\n"
        f"Item: {product_name}\n"
        f"Size: {size} | Color: {color}\n"
        f"Quantity: {quantity}\n"
        f"Total: ₦{total:,}\n"
        f"Delivery to: {address}"
    )

    logger.info(f"Order completed: {order_summary}")

    # Notify business owner
    if OWNER_NUMBER:
        await send_reply(OWNER_NUMBER, order_summary)

    # Confirm to customer with payment placeholder (Paystack integration comes next)
    confirm_msg = (
        f"Your order is confirmed! 🎉\n\n"
        f"{product_name} x{quantity} — ₦{total:,}\n\n"
        f"We'll send your payment link shortly. Thank you for shopping with us!"
    )
    await send_reply(customer_number, confirm_msg)


async def send_reply(to: str, message: str):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message}
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(url, json=payload, headers=headers)
        logger.info(f"Reply sent to {to}: {r.status_code}")
