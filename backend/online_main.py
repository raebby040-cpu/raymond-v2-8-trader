"""Online deployment entrypoint for RAYMOND v2.8."""

from datetime import datetime, timezone

from fastapi import FastAPI

from app.main import app
from app.online_market_api import router as online_market_router


# Add the online market-data/analysis routes.
app.include_router(online_market_router)


@app.get("/health", tags=["Health"])
async def health():
    """Lightweight health check for Render."""
    return {
        "status": "healthy",
        "service": "raymond-v2-8-trader",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "live_trading_enabled": False,
    }
