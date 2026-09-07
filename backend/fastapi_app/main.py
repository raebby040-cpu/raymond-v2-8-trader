# Minimal FastAPI sample with feature-flag, emergency-stop skeleton, and joke endpoint

from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
import os
import httpx
import asyncio
from typing import Dict

app = FastAPI(title="Raymond V2.8 Trader - FastAPI sample")

LIVE_TRADING = os.getenv("LIVE_TRADING", "false").lower() in ["1", "true", "yes"]
EMERGENCY_API_KEY = os.getenv("EMERGENCY_API_KEY", "")

# In-memory placeholder for positions — replace with DB-backed store in production
positions = []

class EmergencyAction(BaseModel):
    reason: str


def verify_emergency_key(x_api_key: str | None = Header(None)):
    if not EMERGENCY_API_KEY:
        # No key configured; disallow emergency endpoint until configured in secrets
        raise HTTPException(status_code=503, detail="Emergency endpoint not configured")
    if x_api_key != EMERGENCY_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


@app.get("/health")
async def health():
    return {"status": "ok", "live_trading_enabled": LIVE_TRADING}


@app.post("/emergency-stop")
async def emergency_stop(action: EmergencyAction, authorized: bool = Depends(verify_emergency_key)):
    """
    Emergency stop endpoint skeleton.

    Behavior: when called with a valid API key (configured via secrets), this endpoint should close all open positions
    and set the system into a safe state. This implementation is a placeholder and does NOT perform any live trades.

    Do NOT enable LIVE_TRADING in production without thorough review.
    """
    # Placeholder: record the action in journal and return success
    # TODO: implement actual close logic, e.g., call execution.close_all_positions()
    # Persistent journal call would go here
    return {"result": "ok", "action": action.reason, "positions_closed": len(positions)}


# -------------------------
# Random joke generator
# -------------------------
# Uses https://icanhazdadjoke.com/ (no API key required for basic use).
# Falls back to a small cached joke if the external service fails.
JOKE_API_URL = "https://icanhazdadjoke.com/"
FALLBACK_JOKES = [
    {"id": "fallback-1", "joke": "Why don’t programmers like nature? It has too many bugs."},
    {"id": "fallback-2", "joke": "Why do Java developers wear glasses? Because they don't C#."},
]

async def fetch_joke_from_api(timeout: float = 2.0) -> Dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": "raymond-v2.8-joke-client/1.0"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(JOKE_API_URL, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        # icanhazdadjoke returns { "id": "...", "joke": "..." }
        return {"source": "icanhazdadjoke", "id": data.get("id", ""), "joke": data.get("joke", "")}

# Simple rotating fallback index
_fallback_idx = 0
_fallback_lock = asyncio.Lock()

async def get_fallback_joke():
    global _fallback_idx
    async with _fallback_lock:
        joke = FALLBACK_JOKES[_fallback_idx % len(FALLBACK_JOKES)]
        _fallback_idx += 1
        return {"source": "fallback", **joke}


@app.get("/joke")
async def random_joke():
    """
    Returns a random joke fetched from an external API (icanhazdadjoke).
    If the external API is unavailable or slow, returns a cached fallback joke.
    """
    try:
        joke = await fetch_joke_from_api()
        # minimal validation
        if not joke.get("joke"):
            raise ValueError("Empty joke from API")
        return {"ok": True, "joke": joke}
    except Exception:
        # If anything goes wrong, return a fallback joke quickly
        fallback = await get_fallback_joke()
        return {"ok": False, "error": "external API unavailable, returning fallback", "joke": fallback}
