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


def test_healthy_heartbeat_allows_trading():
    manager = EmergencyStopManager()

    now = datetime.now(timezone.utc)

    status = manager.record_heartbeat(now)

    assert status.trading_allowed is True
    assert status.connection_healthy is True
    assert status.connection_stale is False
    assert status.last_heartbeat == now


def test_emergency_stop_blocks_trading():
    manager = EmergencyStopManager()

    now = datetime.now(timezone.utc)

    manager.record_heartbeat(now)

    status = manager.activate_emergency_stop()

    assert status.trading_allowed is False
    assert status.emergency_stop_active is True
    assert "Emergency stop" in status.reason


def test_emergency_stop_reset_requires_healthy_connection():
    manager = EmergencyStopManager()

    now = datetime.now(timezone.utc)

    manager.record_heartbeat(now)
    manager.activate_emergency_stop()

    manager.mark_connection_lost()

    status = manager.reset_emergency_stop()

    assert status.trading_allowed is False
    assert status.emergency_stop_active is False
    assert status.connection_healthy is False


def test_emergency_stop_reset_allows_trading_when_connection_is_healthy():
    manager = EmergencyStopManager()

    now = datetime.now(timezone.utc)

    manager.record_heartbeat(now)
    manager.activate_emergency_stop()

    status = manager.reset_emergency_stop()

    assert status.trading_allowed is True
    assert status.emergency_stop_active is False


def test_stale_heartbeat_blocks_trading():
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

    later = heartbeat_time + timedelta(seconds=11)

    status = manager.status(now=later)

    assert status.trading_allowed is False
    assert status.connection_healthy is True
    assert status.connection_stale is True
    assert "stale" in status.reason.lower()


def test_heartbeat_inside_timeout_allows_trading():
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

    later = heartbeat_time + timedelta(seconds=5)

    status = manager.status(now=later)

    assert status.trading_allowed is True
    assert status.connection_stale is False


def test_connection_loss_blocks_trading_immediately():
    manager = EmergencyStopManager()

    now = datetime.now(timezone.utc)

    manager.record_heartbeat(now)

    assert manager.can_trade(now=now) is True

    status = manager.mark_connection_lost()

    assert status.trading_allowed is False
    assert status.connection_healthy is False


def test_connection_recovery_requires_new_heartbeat():
    manager = EmergencyStopManager()

    now = datetime.now(timezone.utc)

    manager.record_heartbeat(now)
    manager.mark_connection_lost()

    assert manager.can_trade(now=now) is False

    recovered = manager.record_heartbeat(
        now + timedelta(seconds=2)
    )

    assert recovered.connection_healthy is True
    assert recovered.connection_stale is False
    assert recovered.trading_allowed is True


def test_require_trade_permission_allows_healthy_connection():
    manager = EmergencyStopManager()

    now = datetime.now(timezone.utc)

    manager.record_heartbeat(now)

    manager.require_trade_permission(now=now)


def test_require_trade_permission_rejects_when_unsafe():
    manager = EmergencyStopManager()

    with pytest.raises(EmergencyStopError) as exc_info:
        manager.require_trade_permission()

    assert "Trading blocked" in str(exc_info.value)


def test_require_trade_permission_rejects_emergency_stop():
    manager = EmergencyStopManager()

    now = datetime.now(timezone.utc)

    manager.record_heartbeat(now)
    manager.activate_emergency_stop()

    with pytest.raises(EmergencyStopError) as exc_info:
        manager.require_trade_permission(now=now)

    assert "Emergency stop" in str(exc_info.value)


def test_invalid_timeout_is_rejected():
    with pytest.raises(EmergencyStopError) as exc_info:
        EmergencyStopManager(
            SafetyConfig(
                heartbeat_timeout_seconds=0,
            )
        )

    assert "heartbeat_timeout_seconds" in str(exc_info.value)


def test_naive_datetime_is_treated_as_utc():
    manager = EmergencyStopManager()

    naive_time = datetime(
        2026,
        1,
        1,
        12,
        0,
        0,
    )

    status = manager.record_heartbeat(naive_time)

    assert status.trading_allowed is True
    assert status.last_heartbeat.tzinfo == timezone.utc
