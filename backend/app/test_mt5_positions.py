import os
import sys

from fastapi.testclient import TestClient


APP_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


import main  # noqa: E402


class FakeMT5Service:
    """
    Fake MT5 service for automated tests.

    No real broker connection is made.
    """

    async def get_positions(self, symbol=None):
        positions = [
            {
                "ticket": 123456789,
                "time": 1720000000,
                "time_update": 1720000100,
                "symbol": "XAUUSD",
                "type": 0,
                "volume": 0.10,
                "price_open": 3350.00,
                "price_current": 3360.00,
                "sl": 3340.00,
                "tp": 3380.00,
                "profit": 100.00,
                "swap": -1.50,
                "commission": -0.50,
                "magic": 280001,
                "comment": "RAYMOND_TEST",
            },
            {
                "ticket": 987654321,
                "time": 1720000200,
                "time_update": 1720000300,
                "symbol": "EURUSD",
                "type": 1,
                "volume": 0.20,
                "price_open": 1.1000,
                "price_current": 1.0980,
                "sl": 1.1050,
                "tp": 1.0900,
                "profit": 40.00,
                "swap": -0.50,
                "commission": -0.25,
                "magic": 280002,
                "comment": "RAYMOND_TEST_SELL",
            },
        ]

        if symbol:
            return [
                position
                for position in positions
                if position["symbol"]
                == symbol.upper()
            ]

        return positions


def test_positions_read_only():
    original_service = main.mt5_service

    try:
        main.mt5_service = FakeMT5Service()

        client = TestClient(main.app)

        response = client.get(
            "/api/trading/positions"
        )

        assert response.status_code == 200

        data = response.json()

        assert data["status"] == "ok"
        assert data["source"] == "mt5_read_only"
        assert data["total_positions"] == 2
        assert data["live_trading_enabled"] is False

        positions = data["positions"]

        assert positions[0]["ticket"] == 123456789
        assert positions[0]["symbol"] == "XAUUSD"
        assert positions[0]["type_name"] == "BUY"
        assert positions[0]["volume"] == 0.10
        assert positions[0]["price_open"] == 3350.00
        assert positions[0]["price_current"] == 3360.00
        assert positions[0]["price_stop_loss"] == 3340.00
        assert positions[0]["price_take_profit"] == 3380.00
        assert positions[0]["profit"] == 100.00

        assert positions[1]["ticket"] == 987654321
        assert positions[1]["symbol"] == "EURUSD"
        assert positions[1]["type_name"] == "SELL"

    finally:
        main.mt5_service = original_service


def test_positions_symbol_filter():
    original_service = main.mt5_service

    try:
        main.mt5_service = FakeMT5Service()

        client = TestClient(main.app)

        response = client.get(
            "/api/trading/positions",
            params={
                "symbol": "XAUUSD"
            },
        )

        assert response.status_code == 200

        data = response.json()

        assert data["status"] == "ok"
        assert data["total_positions"] == 1

        position = data["positions"][0]

        assert position["symbol"] == "XAUUSD"
        assert position["type_name"] == "BUY"
        assert position["volume"] == 0.10

    finally:
        main.mt5_service = original_service


def test_positions_sell_mapping():
    original_service = main.mt5_service

    try:
        main.mt5_service = FakeMT5Service()

        client = TestClient(main.app)

        response = client.get(
            "/api/trading/positions",
            params={
                "symbol": "EURUSD"
            },
        )

        assert response.status_code == 200

        data = response.json()

        assert data["total_positions"] == 1

        position = data["positions"][0]

        assert position["symbol"] == "EURUSD"
        assert position["type_name"] == "SELL"
        assert position["volume"] == 0.20

    finally:
        main.mt5_service = original_service


def test_close_position_is_still_disabled():
    client = TestClient(main.app)

    response = client.post(
        "/api/trading/close-position",
        params={
            "position_id": "123456789"
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "disabled"
