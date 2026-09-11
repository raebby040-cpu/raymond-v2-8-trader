"""End-to-end safety validation for the paper execution boundary."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.emergency_stop import EmergencyStopManager, SafetyConfig
from app.main import app


client = TestClient(app)


def _order_payload() -> dict:
    return {
        "symbol": "XAUUSD",
        "side": "buy",
        "order_type": "market",
        "volume": 0.10,
        "stop_loss": 2300.0,
        "take_profit": 2350.0,
    }


def _replace_safety_manager(manager):
    import app.main as main_module

    original_manager = main_module.safety_manager
    main_module.safety_manager = manager
    return main_module, original_manager


def test_order_is_blocked_without_healthy_connection():
    manager = EmergencyStopManager()

    main_module, original_manager = _replace_safety_manager(manager)

    try:
        response = client.post(
            "/api/trading/place-order",
            json=_order_payload(),
        )

        assert response.status_code == 400
        assert "Trading blocked" in response.json()["detail"]
    finally:
        main_module.safety_manager = original_manager


def test_healthy_connection_allows_paper_execution():
    manager = EmergencyStopManager()
    now = datetime.now(timezone.utc)

    manager.record_heartbeat(now)

    main_module, original_manager = _replace_safety_manager(manager)

    try:
        response = client.post(
            "/api/trading/place-order",
            json=_order_payload(),
        )

        assert response.status_code == 200

        data = response.json()

        assert data["status"] == "accepted"
        assert data["execution_type"] == "paper"
        assert data["broker"] == "paper"
        assert data["symbol"] == "XAUUSD"
        assert data["side"] == "buy"
        assert data["quantity"] == 0.10
        assert data["order_id"].startswith("PAPER-")
    finally:
        main_module.safety_manager = original_manager


def test_emergency_stop_blocks_order_after_healthy_connection():
    manager = EmergencyStopManager()
    now = datetime.now(timezone.utc)

    manager.record_heartbeat(now)
    manager.activate_emergency_stop()

    main_module, original_manager = _replace_safety_manager(manager)

    try:
        response = client.post(
            "/api/trading/place-order",
            json=_order_payload(),
        )

        assert response.status_code == 400
        assert "Emergency stop" in response.json()["detail"]
    finally:
        main_module.safety_manager = original_manager


def test_connection_loss_blocks_order_immediately():
    manager = EmergencyStopManager()
    now = datetime.now(timezone.utc)

    manager.record_heartbeat(now)
    manager.mark_connection_lost()

    main_module, original_manager = _replace_safety_manager(manager)

    try:
        response = client.post(
            "/api/trading/place-order",
            json=_order_payload(),
        )

        assert response.status_code == 400
        assert "MT5 connection is not healthy" in (
            response.json()["detail"]
        )
    finally:
        main_module.safety_manager = original_manager


def test_stale_heartbeat_blocks_order():
    manager = EmergencyStopManager(
        SafetyConfig(
            heartbeat_timeout_seconds=10.0,
        )
    )

    heartbeat_time = datetime(
        2026,
        1,
        1,
        12,
        0,
        0,
        tzinfo=timezone.utc,
    )

    manager.record_heartbeat(heartbeat_time)

    main_module, original_manager = _replace_safety_manager(manager)

    try:
        original_can_trade = manager.can_trade

        def stale_can_trade(now=None):
            return original_can_trade(
                now=heartbeat_time + timedelta(seconds=11)
            )

        manager.can_trade = stale_can_trade

        response = client.post(
            "/api/trading/place-order",
            json=_order_payload(),
        )

        assert response.status_code == 400
        assert "Trading blocked" in response.json()["detail"]
        assert "stale" in response.json()["detail"].lower()
    finally:
        main_module.safety_manager = original_manager


def test_emergency_stop_endpoint_blocks_new_orders():
    manager = EmergencyStopManager()
    now = datetime.now(timezone.utc)

    manager.record_heartbeat(now)

    main_module, original_manager = _replace_safety_manager(manager)

    try:
        stop_response = client.post(
            "/api/admin/emergency-stop"
        )

        assert stop_response.status_code == 200

        stop_data = stop_response.json()

        assert stop_data["new_orders_blocked"] is True
        assert stop_data["trading_allowed"] is False

        order_response = client.post(
            "/api/trading/place-order",
            json=_order_payload(),
        )

        assert order_response.status_code == 400
        assert "Emergency stop" in (
            order_response.json()["detail"]
        )
    finally:
        main_module.safety_manager = original_manager


def test_close_position_remains_disabled():
    response = client.post(
        "/api/trading/close-position",
        params={
            "position_id": "12345",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "disabled"
    assert data["position_id"] == "12345"

    assert data["message"] == (
        "Real MT5 position closing is not implemented yet."
    )
