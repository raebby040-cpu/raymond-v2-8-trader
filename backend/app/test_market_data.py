import os
import sys

from fastapi.testclient import TestClient

APP_DIR = os.path.dirname(os.path.abspath(__file__))

if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import main  # noqa: E402


class FakeMarketDataService:
    async def get_symbol_tick(self, symbol):
        return {
            "symbol": symbol,
            "time": 1720000000,
            "time_msc": 1720000000123,
            "bid": 3350.10,
            "ask": 3350.40,
            "last": 3350.25,
            "volume": 123.0,
            "volume_real": 100.0,
        }

    async def get_candles(self, symbol, timeframe, limit):
        return [
            {
                "time": 1720000000,
                "open": 3340.0,
                "high": 3360.0,
                "low": 3335.0,
                "close": 3350.0,
                "tick_volume": 1000,
                "spread": 30,
                "volume_real": 500.0,
            }
        ]

    async def get_symbols(self, query=None):
        return [
            {
                "name": "XAUUSD",
                "description": "Gold vs US Dollar",
            },
            {
                "name": "EURUSD",
                "description": "Euro vs US Dollar",
            },
        ]

    async def find_gold_symbols(self):
        return [
            {
                "name": "XAUUSD",
                "description": "Gold vs US Dollar",
            }
        ]


def test_market_price():
    original_service = main.mt5_service
    main.mt5_service = FakeMarketDataService()

    try:
        client = TestClient(main.app)

        response = client.get(
            "/api/market/price",
            params={"symbol": "XAUUSD"},
        )

        assert response.status_code == 200

        data = response.json()

        assert data["symbol"] == "XAUUSD"
        assert data["bid"] == 3350.10
        assert data["ask"] == 3350.40
        assert data["last"] == 3350.25
        assert data["volume_real"] == 100.0

    finally:
        main.mt5_service = original_service


def test_market_candles():
    original_service = main.mt5_service
    main.mt5_service = FakeMarketDataService()

    try:
        client = TestClient(main.app)

        response = client.get(
            "/api/market/candlesticks",
            params={
                "symbol": "XAUUSD",
                "timeframe": "M5",
                "limit": 100,
            },
        )

        assert response.status_code == 200

        data = response.json()

        assert data["symbol"] == "XAUUSD"
        assert data["timeframe"] == "M5"
        assert len(data["candles"]) == 1

        candle = data["candles"][0]

        assert candle["open"] == 3340.0
        assert candle["high"] == 3360.0
        assert candle["low"] == 3335.0
        assert candle["close"] == 3350.0
        assert candle["volume_real"] == 500.0

    finally:
        main.mt5_service = original_service


def test_market_symbols():
    original_service = main.mt5_service
    main.mt5_service = FakeMarketDataService()

    try:
        client = TestClient(main.app)

        response = client.get("/api/market/symbols")

        assert response.status_code == 200

        data = response.json()

        assert len(data["symbols"]) == 2
        assert data["symbols"][0]["name"] == "XAUUSD"

    finally:
        main.mt5_service = original_service


def test_gold_symbols():
    original_service = main.mt5_service
    main.mt5_service = FakeMarketDataService()

    try:
        client = TestClient(main.app)

        response = client.get("/api/market/gold-symbols")

        assert response.status_code == 200

        data = response.json()

        assert len(data["symbols"]) == 1
        assert data["symbols"][0]["name"] == "XAUUSD"

    finally:
        main.mt5_service = original_service
