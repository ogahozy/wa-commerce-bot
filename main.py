import os
import logging
from fastapi import FastAPI, Request, HTTPExceptionimport os
import logging
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="WA Commerce Bot")

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "davids_commerce_token")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")


@app.get("/")
async def root():
    return {"status": "WA Commerce Bot is running"}


@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    logger.info(f"Webhook hit — mode={mode}, token={token}, challenge={challenge}")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("Verified successfully")
        return PlainTextResponse(content=challenge, status_code=200)

    logger.warning("Verification failed")
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

        await send_reply(from_number, "Hi! Thanks for your message. Our bot is setting up. We will reply soon!")

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
from fastapi.responses import PlainTextResponse
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="WA Commerce Bot")

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "davids_commerce_token")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")


@app.get("/")
async def root():
    return {"status": "WA Commerce Bot is running"}


@app.get("/webhook")
async def verify_webhook(request: Request):
    """Meta webhook verification"""
    params = dict(request.query_params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("Webhook verified successfully")
        return PlainTextResponse(content=challenge)
    
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook")
async def receive_message(request: Request):
    """Receive incoming WhatsApp messages"""
    body = await request.json()
    logger.info(f"Incoming message: {body}")

    try:
        entry = body["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        # Ignore status updates
        if "statuses" in value:
            return {"status": "ok"}

        messages = value.get("messages", [])
        if not messages:
            return {"status": "ok"}

        message = messages[0]
        from_number = message["from"]
        msg_type = message.get("type", "text")

        if msg_type == "text":
            text = message["text"]["body"]
            logger.info(f"Message from {from_number}: {text}")
            await send_reply(from_number, f"Hi! We received your message: '{text}'. Our bot is coming soon!")

    except Exception as e:
        logger.error(f"Error processing message: {e}")

    return {"status": "ok"}


async def send_reply(to: str, message: str):
    """Send a WhatsApp message"""
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
        response = await client.post(url, json=payload, headers=headers)
        logger.info(f"Send reply response: {response.status_code}")
