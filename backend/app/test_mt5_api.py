import os
import sys

from fastapi.testclient import TestClient


APP_DIR = os.path.dirname(os.path.abspath(__file__))

if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


import main  # noqa: E402


class FakeMT5Service:
    async def heartbeat(self):
        return {
            "connected": True,
            "timestamp": "2026-09-10T00:00:00+00:00",
            "last_error": None,
            "account_login": 12345678,
            "server": "ExampleBroker-Demo",
            "trade_allowed": True,
            "tradeapi_disabled": False,
        }

    async def get_account_info(self):
        return {
            "login": 12345678,
            "server": "ExampleBroker-Demo",
            "company": "Example Broker Ltd",
            "currency": "USD",
            "trade_mode": 0,
            "leverage": 500,
            "trade_allowed": True,
            "trade_expert": True,
            "balance": 10000.0,
            "credit": 0.0,
            "profit": 125.0,
            "equity": 10125.0,
            "margin": 100.0,
            "margin_free": 10025.0,
            "margin_level": 10125.0,
            "margin_so_call": 50.0,
            "margin_so_so": 30.0,
            "name": "Should Not Be Returned",
        }

    async def get_terminal_info(self):
        return {
            "connected": True,
            "trade_allowed": True,
            "tradeapi_disabled": False,
            "build": 5000,
            "company": "MetaQuotes Software Corp.",
            "name": "Example Terminal",
            "path": "C:/Users/private/terminal64.exe",
        }

    async def shutdown(self):
        return True


def test_mt5_status():
    original_service = main.mt5_service

    try:
        main.mt5_service = FakeMT5Service()

        client = TestClient(main.app)

        response = client.get("/api/mt5/status")

        assert response.status_code == 200

        data = response.json()

        assert data["status"] == "connected"
        assert data["connected"] is True
        assert data["account_login"] == 12345678
        assert data["server"] == "ExampleBroker-Demo"

    finally:
        main.mt5_service = original_service


def test_mt5_account():
    original_service = main.mt5_service

    try:
        main.mt5_service = FakeMT5Service()

        client = TestClient(main.app)

        response = client.get("/api/mt5/account")

        assert response.status_code == 200

        data = response.json()

        account = data["account"]

        assert account["login"] == 12345678
        assert account["company"] == "Example Broker Ltd"
        assert account["server"] == "ExampleBroker-Demo"
        assert account["balance"] == 10000.0

        # Sensitive/unnecessary account holder name
        # must not be exposed.
        assert "name" not in account

    finally:
        main.mt5_service = original_service


def test_mt5_terminal():
    original_service = main.mt5_service

    try:
        main.mt5_service = FakeMT5Service()

        client = TestClient(main.app)

        response = client.get("/api/mt5/terminal")

        assert response.status_code == 200

        data = response.json()

        terminal = data["terminal"]

        assert terminal["connected"] is True
        assert terminal["build"] == 5000

        # Local filesystem path must not be exposed.
        assert "path" not in terminal

    finally:
        main.mt5_service = original_service


def test_mt5_disconnect():
    original_service = main.mt5_service

    try:
        main.mt5_service = FakeMT5Service()

        client = TestClient(main.app)

        response = client.post("/api/mt5/disconnect")

        assert response.status_code == 200
        assert response.json()["status"] == "disconnected"

    finally:
        main.mt5_service = original_service
