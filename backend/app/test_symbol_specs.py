import os
import sys

import pytest


APP_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


from main import app  # noqa: E402


class FakeMT5Service:
    async def get_symbol_specification(
        self,
        symbol: str,
    ) -> dict:
        return {
            "symbol": symbol,
            "digits": 2,
            "point": 0.01,
            "spread": 30,
            "spread_float": True,
            "tick_size": 0.01,
            "tick_value": 1.0,
            "tick_value_profit": 1.0,
            "tick_value_loss": 1.0,
            "contract_size": 100.0,
            "volume_min": 0.01,
            "volume_max": 100.0,
            "volume_step": 0.01,
            "volume_limit": 0.0,
            "trade_mode": 4,
            "trade_execution_mode": 2,
            "trade_stops_level": 0,
            "trade_freeze_level": 0,
            "currency_base": "XAU",
            "currency_profit": "USD",
            "currency_margin": "XAU",
        }


@pytest.mark.asyncio
async def test_symbol_specification_endpoint():
    original_service = app.state.__dict__.get(
        "test_mt5_service"
    )

    import main as main_module

    original_global_service = (
        main_module.mt5_service
    )

    fake_service = FakeMT5Service()
    main_module.mt5_service = fake_service

    try:
        from httpx import (
            ASGITransport,
            AsyncClient,
        )

        transport = ASGITransport(
            app=app
        )

        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/market/symbol-specification",
                params={
                    "symbol": "XAUUSD"
                },
            )

        assert response.status_code == 200

        data = response.json()

        assert data["status"] == "ok"
        assert data["symbol"] == "XAUUSD"
        assert data["source"] == "mt5"
        assert data["read_only"] is True

        specification = data[
            "specification"
        ]

        assert specification[
            "symbol"
        ] == "XAUUSD"

        assert specification[
            "tick_size"
        ] == 0.01

        assert specification[
            "tick_value_loss"
        ] == 1.0

        assert specification[
            "volume_min"
        ] == 0.01

        assert specification[
            "volume_max"
        ] == 100.0

        assert specification[
            "volume_step"
        ] == 0.01

        assert specification[
            "currency_profit"
        ] == "USD"

    finally:
        main_module.mt5_service = (
            original_global_service
        )

        if original_service is not None:
            app.state.test_mt5_service = (
                original_service
            )


@pytest.mark.asyncio
async def test_symbol_specification_endpoint_uses_requested_symbol():
    import main as main_module

    original_global_service = (
        main_module.mt5_service
    )

    main_module.mt5_service = (
        FakeMT5Service()
    )

    try:
        from httpx import (
            ASGITransport,
            AsyncClient,
        )

        transport = ASGITransport(
            app=app
        )

        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/market/symbol-specification",
                params={
                    "symbol": "XAUUSDm"
                },
            )

        assert response.status_code == 200

        data = response.json()

        assert data["symbol"] == "XAUUSDm"
        assert data[
            "specification"
        ]["symbol"] == "XAUUSDm"

    finally:
        main_module.mt5_service = (
            original_global_service
      )
