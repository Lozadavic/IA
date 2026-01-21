import json
import logging
import os
from typing import Any, Dict, Optional

import requests
from fastapi import APIRouter, HTTPException, Request
from dotenv import load_dotenv

from app.agent import support_agent
from app.utils import InMemoryRateLimiter, RateLimitConfig, sanitize_text

logger = logging.getLogger(__name__)

load_dotenv()

router = APIRouter()
rate_limiter = InMemoryRateLimiter(RateLimitConfig(max_requests=12, window_seconds=60))

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "")
GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v20.0")
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "es")


def _extract_message(payload: Dict[str, Any]) -> Optional[Dict[str, str]]:
    try:
        entry = payload["entry"][0]
        change = entry["changes"][0]
        value = change["value"]
        messages = value.get("messages", [])
        if not messages:
            return None
        message = messages[0]
        if message.get("type") != "text":
            return None
        return {
            "from": message["from"],
            "text": message["text"]["body"],
        }
    except (KeyError, IndexError, TypeError):
        return None


def send_whatsapp_message(phone: str, text: str) -> None:
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        raise RuntimeError("WhatsApp credentials not configured")
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"preview_url": False, "body": text},
        "language": {"code": DEFAULT_LANGUAGE},
    }
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
    if not response.ok:
        logger.error("WhatsApp send failed: %s", response.text)
        response.raise_for_status()


@router.get("/")
async def verify_webhook(request: Request) -> str:
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge or ""
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/")
async def receive_message(request: Request) -> Dict[str, str]:
    payload = await request.json()
    message = _extract_message(payload)
    if not message:
        return {"status": "ignored"}

    phone = message["from"]
    if not rate_limiter.allow(phone):
        logger.warning("Rate limit exceeded for %s", phone)
        return {"status": "rate_limited"}

    user_text = sanitize_text(message["text"])
    if not user_text:
        return {"status": "empty"}

    try:
        reply = support_agent.generate_response(phone, user_text)
        send_whatsapp_message(phone, reply)
        return {"status": "sent"}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to process message: %s", exc)
        raise HTTPException(status_code=500, detail="Processing error") from exc
