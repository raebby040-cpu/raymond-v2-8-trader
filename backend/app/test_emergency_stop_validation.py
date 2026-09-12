"""Step 11B - Emergency-stop and fail-closed safety validation."""

from datetime import datetime, timedelta, timezone

import pytest

from app.emergency_stop import (
    EmergencyStopError,
    EmergencyStopManager,
    SafetyConfig,
)


def test_new_manager_fails_closed():
    manager = EmergencyStopManager()

    status = manager.status()

    assert status.trading_allowed is False
    assert status.emergency_stop_active is False
    assert status.connection_healthy is False
    assert status.connection_stale is True
    assert status.reason == "MT5 connection is not healthy."
    assert status.last_heartbeat is None


def test_new_manager_blocks_trade_permission():
    manager = EmergencyStopManager()

    with pytest.raises(
        EmergencyStopError,
        match="MT5 connection is not healthy",
    ):
        manager.require_trade_permission()


def test_healthy_heartbeat_allows_trading():
    manager = EmergencyStopManager()

    heartbeat = datetime(
        2026,
        1,
        1,
        12,
        0,
        0,
        tzinfo=timezone.utc,
    )

    status = manager.record_heartbeat(heartbeat)

    assert status.trading_allowed is True
    assert status.emergency_stop_active is False
    assert status.connection_healthy is True
    assert status.connection_stale is False
    assert status.reason == "Trading safety checks passed."
    assert status.last_heartbeat == heartbeat

    manager.require_trade_permission(
        now=heartbeat + timedelta(seconds=5)
    )


def test_emergency_stop_blocks_healthy_connection():
    manager = EmergencyStopManager()

    heartbeat = datetime(
        2026,
        1,
        1,
        12,
        0,
        0,
        tzinfo=timezone.utc,
    )

    manager.record_heartbeat(heartbeat)

    status = manager.activate_emergency_stop()

    assert status.trading_allowed is False
    assert status.emergency_stop_active is True
    assert status.connection_healthy is True
    assert status.reason == "Emergency stop is active."

    with pytest.raises(
        EmergencyStopError,
        match="Emergency stop is active",
    ):
        manager.require_trade_permission(
            now=heartbeat + timedelta(seconds=5)
        )


def test_reset_does_not_bypass_unhealthy_connection():
    manager = EmergencyStopManager()

    manager.activate_emergency_stop()
    status = manager.reset_emergency_stop()

    assert status.emergency_stop_active is False
    assert status.connection_healthy is False
    assert status.connection_stale is True
    assert status.trading_allowed is False
    assert status.reason == "MT5 connection is not healthy."

    with pytest.raises(
        EmergencyStopError,
        match="MT5 connection is not healthy",
    ):
        manager.require_trade_permission()


def test_reset_allows_trading_only_when_connection_is_healthy():
    manager = EmergencyStopManager()

    heartbeat = datetime(
        2026,
        1,
        1,
        12,
        0,
        0,
        tzinfo=timezone.utc,
    )

    manager.record_heartbeat(heartbeat)
    manager.activate_emergency_stop()

    stopped = manager.status(
        now=heartbeat + timedelta(seconds=5)
    )

    assert stopped.trading_allowed is False
    assert stopped.emergency_stop_active is True

    manager.reset_emergency_stop()

    reset_status = manager.status(
        now=heartbeat + timedelta(seconds=5)
    )

    assert reset_status.trading_allowed is True
    assert reset_status.emergency_stop_active is False
    assert reset_status.connection_healthy is True
    assert reset_status.connection_stale is False
    assert reset_status.reason == "Trading safety checks passed."


def test_connection_loss_blocks_trading_immediately():
    manager = EmergencyStopManager()

    heartbeat = datetime(
        2026,
        1,
        1,
        12,
        0,
        0,
        tzinfo=timezone.utc,
    )

    manager.record_heartbeat(heartbeat)

    status = manager.mark_connection_lost()

    assert status.trading_allowed is False
    assert status.connection_healthy is False

    with pytest.raises(
        EmergencyStopError,
        match="MT5 connection is not healthy",
    ):
        manager.require_trade_permission(
            now=heartbeat + timedelta(seconds=1)
        )


def test_stale_heartbeat_blocks_trading():
    manager = EmergencyStopManager(
        SafetyConfig(
            heartbeat_timeout_seconds=10.0,
        )
    )

    heartbeat = datetime(
        2026,
        1,
        1,
        12,
        0,
        0,
        tzinfo=timezone.utc,
    )

    manager.record_heartbeat(heartbeat)

    now = heartbeat + timedelta(seconds=11)

    status = manager.status(now=now)

    assert status.trading_allowed is False
    assert status.connection_healthy is True
    assert status.connection_stale is True
    assert status.reason == "MT5 heartbeat is stale."

    with pytest.raises(
        EmergencyStopError,
        match="MT5 heartbeat is stale",
    ):
        manager.require_trade_permission(now=now)


def test_fresh_heartbeat_does_not_block_trading():
    manager = EmergencyStopManager(
        SafetyConfig(
            heartbeat_timeout_seconds=10.0,
        )
    )

    heartbeat = datetime(
        2026,
        1,
        1,
        12,
        0,
        0,
        tzinfo=timezone.utc,
    )

    manager.record_heartbeat(heartbeat)

    status = manager.status(
        now=heartbeat + timedelta(seconds=10)
    )

    assert status.trading_allowed is True
    assert status.connection_stale is False


def test_heartbeat_timeout_must_be_positive():
    with pytest.raises(
        EmergencyStopError,
        match="heartbeat_timeout_seconds must be greater than zero",
    ):
        EmergencyStopManager(
            SafetyConfig(
                heartbeat_timeout_seconds=0.0,
            )
        )


def test_naive_heartbeat_timestamp_is_normalized_to_utc():
    manager = EmergencyStopManager()

    heartbeat = datetime(
        2026,
        1,
        1,
        12,
        0,
        0,
    )

    status = manager.record_heartbeat(heartbeat)

    assert status.last_heartbeat == heartbeat.replace(
        tzinfo=timezone.utc
    )
    assert status.trading_allowed is True


def test_emergency_stop_has_priority_over_stale_heartbeat():
    manager = EmergencyStopManager(
        SafetyConfig(
            heartbeat_timeout_seconds=10.0,
        )
    )

    heartbeat = datetime(
        2026,
        1,
        1,
        12,
        0,
        0,
        tzinfo=timezone.utc,
    )

    manager.record_heartbeat(heartbeat)
    manager.activate_emergency_stop()

    status = manager.status(
        now=heartbeat + timedelta(seconds=100)
    )

    assert status.trading_allowed is False
    assert status.emergency_stop_active is True
    assert status.connection_stale is True
    assert status.reason == "Emergency stop is active."


def test_connection_loss_remains_blocked_after_reset():
    manager = EmergencyStopManager()

    heartbeat = datetime(
        2026,
        1,
        1,
        12,
        0,
        0,
        tzinfo=timezone.utc,
    )

    manager.record_heartbeat(heartbeat)
    manager.activate_emergency_stop()
    manager.mark_connection_lost()
    manager.reset_emergency_stop()

    status = manager.status()

    assert status.emergency_stop_active is False
    assert status.connection_healthy is False
    assert status.trading_allowed is False

    with pytest.raises(
        EmergencyStopError,
        match="MT5 connection is not healthy",
    ):
        manager.require_trade_permission()
