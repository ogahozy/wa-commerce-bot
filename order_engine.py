import os
import json
import logging
from groq import Groq

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
client = Groq(api_key=GROQ_API_KEY)

with open("catalog.json", "r") as f:
    CATALOG = json.load(f)


def build_system_prompt():
    products_text = "\n".join([
        f"- {p['name']} (ID: {p['id']}) — ₦{p['price']:,} — Sizes: {', '.join(p.get('sizes', ['N/A']))} — Colors: {', '.join(p.get('colors', ['N/A']))}"
        for p in CATALOG["products"]
    ])

    return f"""You are a friendly WhatsApp sales assistant for {CATALOG['business_name']}, a {CATALOG['business_type']} business in Nigeria.

PRODUCTS AVAILABLE:
{products_text}

DELIVERY INFO: {CATALOG['delivery_info']}
PAYMENT INFO: {CATALOG['payment_info']}

YOUR JOB:
1. Answer questions about products, prices, sizes, colors naturally and warmly.
2. Help customers choose items and build an order.
3. When a customer wants to order, collect: product, size/color (if applicable), quantity, delivery address.
4. Once you have ALL order details, summarize the order clearly INCLUDING subtotal, delivery fee, and total, and ask for confirmation.
5. Respond in a warm, conversational Nigerian tone — natural English, can lightly use Pidgin expressions if customer uses Pidgin first. Keep replies SHORT (2-4 sentences max), like a real WhatsApp chat.
6. If asked something you don't know, say you'll have the business owner confirm.
7. NEVER invent products, prices, or sizes not listed above.

CRITICAL RULE: Only after the customer explicitly confirms the order (says "yes", "confirm", "go ahead", etc. to your summary), respond with a short confirmation sentence FOLLOWED IMMEDIATELY by this exact tag on its own line, with NO other text after it:
[ORDER_READY: product_id=X, quantity=Y, size=Z, color=W, address=ADDRESS, delivery_fee=FEE, total=TOTAL]

Rules for the tag:
- delivery_fee must be a plain number, no currency symbol, no commas (e.g. delivery_fee=1500)
- total must be a plain number, no currency symbol, no commas (e.g. total=31500)
- total = (product_price x quantity) + delivery_fee — always calculate this correctly
- Do NOT include the tag while still gathering order details or before the customer confirms
- The tag must be the LAST thing in your message
"""


def get_bot_reply(conversation_history: list, user_message: str) -> tuple[str, dict | None]:
    """
    conversation_history: list of {"role": "user"/"assistant", "content": "..."}
    Returns: (reply_text, order_dict_or_None)
    """
    messages = [{"role": "system", "content": build_system_prompt()}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_message})

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.5,
            max_tokens=500,
        )
        reply = response.choices[0].message.content
        logger.info(f"RAW AI RESPONSE: {reply}")

        order_data = None
        if "[ORDER_READY:" in reply:
            try:
                tag_start = reply.index("[ORDER_READY:")
                tag_end = reply.index("]", tag_start)
                tag_content = reply[tag_start + len("[ORDER_READY:"):tag_end]
                order_data = {}
                for pair in tag_content.split(","):
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        order_data[k.strip()] = v.strip()
                reply = reply[:tag_start].strip()
                logger.info(f"PARSED ORDER DATA: {order_data}")
            except Exception as e:
                logger.error(f"Failed to parse order tag: {e}")

        return reply, order_data

    except Exception as e:
        logger.error(f"Groq error: {e}")
        return "Sorry, I'm having trouble right now. Please give me a moment or the business owner will respond shortly.", None


def get_product_by_id(product_id: str) -> dict | None:
    for p in CATALOG["products"]:
        if p["id"] == product_id:
            return p
    return None


def get_greeting() -> str:
    return CATALOG["greeting"]
