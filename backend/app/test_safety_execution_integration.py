"""End-to-end safety validation for the paper execution boundary.

The legacy direct-order endpoint is intentionally disabled. These tests
verify that the disabled boundary cannot be used to bypass the AI/Risk
pipeline, while the emergency-stop and connection-safety controls remain
independently validated.
"""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.emergency_stop import EmergencyStopManager, SafetyConfig
from app.main import app


client = TestClient(app)


def _order_payload() -> dict:
    """Return a representative legacy direct-order payload."""
    return {
        "symbol": "XAUUSD",
        "side": "buy",
        "order_type": "market",
        "volume": 0.10,
        "stop_loss": 2300.0,
        "take_profit": 2350.0,
    }


def _replace_safety_manager(manager):
    """Temporarily replace the application's safety manager."""
    import app.main as main_module

    original_manager = main_module.safety_manager
    main_module.safety_manager = manager
    return main_module, original_manager


def _assert_direct_order_disabled(response):
    """Verify the unsafe legacy direct-order boundary is closed."""
    assert response.status_code == 410

    data = response.json()
    detail = data["detail"]

    assert detail["error"] == "Direct order endpoint disabled"
    assert detail["execution_mode"] == "paper_only"
    assert detail["live_trading_enabled"] is False
    assert detail["risk_engine_required"] is True
    assert detail["canonical_endpoint"] == "/api/strategy/paper-trade"


def test_legacy_direct_order_endpoint_is_disabled_without_healthy_connection():
    """Client-supplied orders cannot bypass the canonical pipeline."""
    manager = EmergencyStopManager()

    main_module, original_manager = _replace_safety_manager(manager)

    try:
        response = client.post(
            "/api/trading/place-order",
            json=_order_payload(),
        )

        _assert_direct_order_disabled(response)
    finally:
        main_module.safety_manager = original_manager


def test_legacy_direct_order_endpoint_is_disabled_with_healthy_connection():
    """A healthy connection must not reopen the unsafe legacy endpoint."""
    manager = EmergencyStopManager()
    manager.record_heartbeat(datetime.now(timezone.utc))

    main_module, original_manager = _replace_safety_manager(manager)

    try:
        response = client.post(
            "/api/trading/place-order",
            json=_order_payload(),
        )

        _assert_direct_order_disabled(response)
    finally:
        main_module.safety_manager = original_manager


def test_emergency_stop_blocks_new_orders():
    """Emergency stop independently prevents new trading."""
    manager = EmergencyStopManager()
    now = datetime.now(timezone.utc)

    manager.record_heartbeat(now)

    assert manager.can_trade(now=now) is True

    manager.activate_emergency_stop()

    assert manager.can_trade(now=now) is False


def test_connection_loss_blocks_orders_immediately():
    """Connection loss independently blocks trading."""
    manager = EmergencyStopManager()
    now = datetime.now(timezone.utc)

    manager.record_heartbeat(now)
    assert manager.can_trade(now=now) is True

    manager.mark_connection_lost()

    assert manager.can_trade(now=now) is False


def test_stale_heartbeat_blocks_orders():
    """A heartbeat older than the configured timeout is unsafe."""
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

    assert manager.can_trade(
        now=heartbeat_time + timedelta(seconds=11)
    ) is False


def test_emergency_stop_endpoint_blocks_new_orders():
    """The emergency-stop API reports the system as unable to trade."""
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

        # The direct-order endpoint remains disabled regardless of the
        # emergency-stop state. This prevents a client from bypassing
        # the canonical AI/Risk paper-trading path.
        order_response = client.post(
            "/api/trading/place-order",
            json=_order_payload(),
        )

        _assert_direct_order_disabled(order_response)
    finally:
        main_module.safety_manager = original_manager


def test_close_position_remains_disabled():
    """Real MT5 position closing remains explicitly unimplemented."""
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
