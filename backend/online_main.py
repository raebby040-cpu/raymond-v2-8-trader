"""Online deployment entrypoint for RAYMOND v2.8."""

from datetime import datetime, timezone

from app.main import app
from app.online_market_api import router as online_market_router
from app.advisory_api import router as advisory_analysis_router
from app.paper_position_management_api import (
    router as paper_position_management_router,
)


# Add the online market-data/analysis routes.
app.include_router(online_market_router)

# STEP 16.4:
# Add the 8-brain advisory comparison API.
app.include_router(advisory_analysis_router)

# STEP 17.2:
# Add the persistent paper-position management API.
#
# SAFETY:
# - Paper positions only.
# - No broker orders.
# - No MT5 execution.
# - Live trading remains disabled.
app.include_router(paper_position_management_router)


@app.get("/health", tags=["Health"])
async def health():
    """Lightweight health check for Render."""
    return {
        "status": "healthy",
        "service": "raymond-v2-8-trader",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "live_trading_enabled": False,
    }


