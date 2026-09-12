"""Step 11C - Connection-loss and stale-data safety validation."""

from datetime import datetime, timedelta, timezone

import pytest

from app.emergency_stop import (
    EmergencyStopError,
    EmergencyStopManager,
    SafetyConfig,
)


def test_missing_heartbeat_is_unsafe():
    manager = EmergencyStopManager()

    status = manager.status()

    assert status.connection_healthy is False
    assert status.connection_stale is True
    assert status.trading_allowed is False


def test_missing_heartbeat_blocks_trade_permission():
    manager = EmergencyStopManager()

    with pytest.raises(
        EmergencyStopError,
        match="MT5 connection is not healthy",
    ):
        manager.require_trade_permission()


def test_healthy_connection_with_fresh_heartbeat_allows_trading():
    manager = EmergencyStopManager(
        SafetyConfig(
            heartbeat_timeout_seconds=15.0,
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
        now=heartbeat + timedelta(seconds=5)
    )

    assert status.connection_healthy is True
    assert status.connection_stale is False
    assert status.trading_allowed is True

    manager.require_trade_permission(
        now=heartbeat + timedelta(seconds=5)
    )


def test_stale_heartbeat_blocks_trading():
    manager = EmergencyStopManager(
        SafetyConfig(
            heartbeat_timeout_seconds=15.0,
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

    stale_time = heartbeat + timedelta(seconds=16)

    status = manager.status(now=stale_time)

    assert status.connection_healthy is True
    assert status.connection_stale is True
    assert status.trading_allowed is False
    assert status.reason == "MT5 heartbeat is stale."

    with pytest.raises(
        EmergencyStopError,
        match="MT5 heartbeat is stale",
    ):
        manager.require_trade_permission(now=stale_time)


def test_connection_loss_blocks_trading():
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

    manager.mark_connection_lost()

    status = manager.status(
        now=heartbeat + timedelta(seconds=1)
    )

    assert status.connection_healthy is False
    assert status.trading_allowed is False
    assert status.reason == "MT5 connection is not healthy."

    with pytest.raises(
        EmergencyStopError,
        match="MT5 connection is not healthy",
    ):
        manager.require_trade_permission(
            now=heartbeat + timedelta(seconds=1)
        )


def test_connection_loss_cannot_be_bypassed_by_fresh_time():
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
    manager.mark_connection_lost()

    later = heartbeat + timedelta(seconds=1)

    status = manager.status(now=later)

    assert status.connection_healthy is False
    assert status.trading_allowed is False


def test_new_heartbeat_restores_connection_health():
    manager = EmergencyStopManager()

    first_heartbeat = datetime(
        2026,
        1,
        1,
        12,
        0,
        0,
        tzinfo=timezone.utc,
    )

    second_heartbeat = first_heartbeat + timedelta(seconds=20)

    manager.record_heartbeat(first_heartbeat)
    manager.mark_connection_lost()

    blocked = manager.status(now=second_heartbeat)

    assert blocked.connection_healthy is False
    assert blocked.trading_allowed is False

    restored = manager.record_heartbeat(second_heartbeat)

    assert restored.connection_healthy is True
    assert restored.connection_stale is False
    assert restored.trading_allowed is True

    manager.require_trade_permission(
        now=second_heartbeat + timedelta(seconds=1)
    )


def test_old_heartbeat_does_not_keep_connection_healthy_forever():
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
        now=heartbeat + timedelta(seconds=60)
    )

    assert status.connection_healthy is True
    assert status.connection_stale is True
    assert status.trading_allowed is False


def test_heartbeat_exactly_at_timeout_is_still_fresh():
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

    assert status.connection_stale is False
    assert status.trading_allowed is True


def test_stale_heartbeat_becomes_safe_after_new_heartbeat():
    manager = EmergencyStopManager(
        SafetyConfig(
            heartbeat_timeout_seconds=10.0,
        )
    )

    first_heartbeat = datetime(
        2026,
        1,
        1,
        12,
        0,
        0,
        tzinfo=timezone.utc,
    )

    stale_time = first_heartbeat + timedelta(seconds=11)

    manager.record_heartbeat(first_heartbeat)

    stale_status = manager.status(now=stale_time)

    assert stale_status.connection_stale is True
    assert stale_status.trading_allowed is False

    fresh_heartbeat = stale_time

    fresh_status = manager.record_heartbeat(
        fresh_heartbeat
    )

    assert fresh_status.connection_healthy is True
    assert fresh_status.connection_stale is False
    assert fresh_status.trading_allowed is True


def test_emergency_stop_still_blocks_after_connection_recovery():
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

    manager.record_heartbeat(
        heartbeat + timedelta(seconds=5)
    )

    status = manager.status(
        now=heartbeat + timedelta(seconds=5)
    )

    assert status.connection_healthy is True
    assert status.connection_stale is False
    assert status.emergency_stop_active is True
    assert status.trading_allowed is False
    assert status.reason == "Emergency stop is active."

    with pytest.raises(
        EmergencyStopError,
        match="Emergency stop is active",
    ):
        manager.require_trade_permission(
            now=heartbeat + timedelta(seconds=5)
        )


def test_reset_after_connection_recovery_allows_trading():
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

    recovered_heartbeat = heartbeat + timedelta(seconds=5)

    manager.record_heartbeat(
        recovered_heartbeat
    )

    stopped = manager.status(
        now=recovered_heartbeat
    )

    assert stopped.trading_allowed is False

    reset = manager.reset_emergency_stop()

    assert reset.emergency_stop_active is False
    assert reset.connection_healthy is True

    reset_status = manager.status(
        now=recovered_heartbeat
    )

    assert reset_status.connection_stale is False
    assert reset_status.trading_allowed is True
    assert reset_status.reason == "Trading safety checks passed."

    manager.require_trade_permission(
        now=recovered_heartbeat
    )


def test_naive_timestamp_is_normalized_to_utc():
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


def test_negative_heartbeat_timeout_is_rejected():
    with pytest.raises(
        EmergencyStopError,
        match="heartbeat_timeout_seconds must be greater than zero",
    ):
        EmergencyStopManager(
            SafetyConfig(
                heartbeat_timeout_seconds=-1.0,
            )
        )
