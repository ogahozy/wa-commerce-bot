import os
import logging
import httpx
import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "davids_commerce_token")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "")
RENDER_URL = os.getenv("RENDER_URL", "https://wa-commerce-bot.onrender.com")


async def keep_alive():
    """Ping self every 4 minutes to prevent Render free tier sleep"""
    await asyncio.sleep(60)  # Wait 1 min after startup
    while True:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{RENDER_URL}/ping", timeout=10)
                logger.info(f"Keep-alive ping: {r.status_code}")
        except Exception as e:
            logger.warning(f"Keep-alive failed: {e}")
        await asyncio.sleep(240)  # Ping every 4 minutes


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
    
    # Meta sends both dot and underscore versions
    mode = params.get("hub.mode") or params.get("hub_mode")
    token = params.get("hub.verify_token") or params.get("hub_verify_token")
    challenge = params.get("hub.challenge") or params.get("hub_challenge")

    logger.info(f"Webhook hit — mode={mode}, token={token}, challenge={challenge}")
    logger.info(f"Expected token={VERIFY_TOKEN}, match={token == VERIFY_TOKEN}")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("Verified successfully")
        return PlainTextResponse(content=challenge, status_code=200)
    
    logger.warning(f"Verification failed — mode={mode}, token={token}")
    return PlainTextResponse(content="Forbidden", status_code=403)


@app.post("/webhook")
async def receive_message(request: Request):
    body = await request.json()
    logger.info(f"Incoming: {body}")
    try:
        entry = body["entry"][0]
        value = entry["changes"][0]["value"]
        if "statuses" in value:
            return {"status": "ok"}
        messages = value.get("messages", [])
        if not messages:
            return {"status": "ok"}
        message = messages[0]
        from_number = message["from"]
        text = message.get("text", {}).get("body", "")
        logger.info(f"From {from_number}: {text}")
        await send_reply(from_number, "Hi! Thanks for your message. Our bot is setting up shortly!")
    except Exception as e:
        logger.error(f"Error: {e}")
    return {"status": "ok"}


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
        logger.info(f"Reply sent: {r.status_code}")
