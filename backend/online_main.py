"""Online deployment entrypoint for RAYMOND v2.8.

This entrypoint keeps the existing Raymond backend intact and adds
the broker-independent online market-data and analysis API.

Live trading remains disabled.
"""

from app.main import app
from app.online_market_api import router as online_market_router


# Add the online market-data/analysis routes.
app.include_router(online_market_router)
