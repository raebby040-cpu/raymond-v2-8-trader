"""
RAYMOND v2.8 - LIVE safety gate tests.

These tests verify that real-money execution remains fail-closed.

They intentionally do NOT enable real trading.

Coverage:
- live trading is disarmed by default
- missing/short arm token cannot arm
- invalid arm token cannot arm
- valid arm token can arm
- armed state is explicit
- disarm immediately closes the execution gate
- emergency disarm closes the execution gate
- environment gate and ARM gate are both required
- restart-style reset starts disarmed
- configured token is never exposed
"""

from __future__ import annotations

import app.live_safety_gate as safety


VALID_TOKEN = (
    "raymond-test-live-arm-token-"
    "abcdefghijklmnopqrstuvwxyz123456"
)


def _reset_gate(monkeypatch):
    """
    Force every test to begin from a known disarmed state.
    """

    safety.disarm_live_trading(
        reason="test_reset"
    )

    monkeypatch.delenv(
        "RAYMOND_LIVE_ARM_TOKEN",
        raising=False,
    )


def test_live_gate_starts_disarmed(monkeypatch):
    _reset_gate(monkeypatch)

    assert safety.is_live_armed() is False

    status = safety.live_safety_status()

    assert status["armed"] is False
    assert status["arm_token_configured"] is False
    assert status["fail_closed"] is True


def test_missing_token_cannot_arm(monkeypatch):
    _reset_gate(monkeypatch)

    monkeypatch.delenv(
        "RAYMOND_LIVE_ARM_TOKEN",
        raising=False,
    )

    try:
        safety.arm_live_trading(
            token=VALID_TOKEN,
            armed_by="test",
        )
        assert False, "Live trading must not arm without a configured token."
    except PermissionError:
        pass

    assert safety.is_live_armed() is False


def test_short_configured_token_cannot_arm(monkeypatch):
    _reset_gate(monkeypatch)

    monkeypatch.setenv(
        "RAYMOND_LIVE_ARM_TOKEN",
        "too-short",
    )

    try:
        safety.arm_live_trading(
            token="too-short",
            armed_by="test",
        )
        assert False, "Short arm tokens must be rejected."
    except PermissionError:
        pass

    assert safety.is_live_armed() is False


def test_invalid_token_cannot_arm(monkeypatch):
    _reset_gate(monkeypatch)

    monkeypatch.setenv(
        "RAYMOND_LIVE_ARM_TOKEN",
        VALID_TOKEN,
    )

    try:
        safety.arm_live_trading(
            token="wrong-token-" + ("x" * 40),
            armed_by="test",
        )
        assert False, "An invalid arm token must be rejected."
    except PermissionError:
        pass

    assert safety.is_live_armed() is False


def test_valid_token_arms_live_gate(monkeypatch):
    _reset_gate(monkeypatch)

    monkeypatch.setenv(
        "RAYMOND_LIVE_ARM_TOKEN",
        VALID_TOKEN,
    )

    result = safety.arm_live_trading(
        token=VALID_TOKEN,
        armed_by="test",
    )

    assert result["armed"] is True
    assert result["arm_token_configured"] is True
    assert result["armed_by"] == "test"
    assert result["armed_at"] is not None

    assert safety.is_live_armed() is True


def test_require_live_armed_blocks_when_disarmed(monkeypatch):
    _reset_gate(monkeypatch)

    try:
        safety.require_live_armed()
        assert False, "Disarmed LIVE execution must fail closed."
    except PermissionError as exc:
        assert "not armed" in str(exc).lower()


def test_require_live_armed_allows_explicitly_armed_state(
    monkeypatch,
):
    _reset_gate(monkeypatch)

    monkeypatch.setenv(
        "RAYMOND_LIVE_ARM_TOKEN",
        VALID_TOKEN,
    )

    safety.arm_live_trading(
        token=VALID_TOKEN,
        armed_by="test",
    )

    safety.require_live_armed()

    assert safety.is_live_armed() is True


def test_disarm_immediately_closes_live_gate(monkeypatch):
    _reset_gate(monkeypatch)

    monkeypatch.setenv(
        "RAYMOND_LIVE_ARM_TOKEN",
        VALID_TOKEN,
    )

    safety.arm_live_trading(
        token=VALID_TOKEN,
        armed_by="test",
    )

    assert safety.is_live_armed() is True

    result = safety.disarm_live_trading(
        reason="test_disarm",
    )

    assert result["armed"] is False
    assert result["armed_at"] is None
    assert result["armed_by"] is None

    assert safety.is_live_armed() is False

    try:
        safety.require_live_armed()
        assert False, "Disarm must immediately block LIVE execution."
    except PermissionError:
        pass


def test_emergency_disarm_closes_live_gate(monkeypatch):
    _reset_gate(monkeypatch)

    monkeypatch.setenv(
        "RAYMOND_LIVE_ARM_TOKEN",
        VALID_TOKEN,
    )

    safety.arm_live_trading(
        token=VALID_TOKEN,
        armed_by="test",
    )

    assert safety.is_live_armed() is True

    result = safety.disarm_live_trading(
        reason="emergency_disarm",
    )

    assert result["armed"] is False
    assert result["disarm_reason"] == "emergency_disarm"

    assert safety.is_live_armed() is False


def test_environment_gate_requires_both_conditions(
    monkeypatch,
):
    _reset_gate(monkeypatch)

    monkeypatch.setenv(
        "RAYMOND_LIVE_ARM_TOKEN",
        VALID_TOKEN,
    )

    # Environment OFF + ARM OFF
    status = safety.combined_live_gate_status(
        environment_enabled=False,
    )

    assert status["environment_enabled"] is False
    assert status["explicitly_armed"] is False
    assert status["execution_gate_open"] is False
    assert status["fail_closed"] is True

    # Environment ON + ARM OFF
    status = safety.combined_live_gate_status(
        environment_enabled=True,
    )

    assert status["environment_enabled"] is True
    assert status["explicitly_armed"] is False
    assert status["execution_gate_open"] is False

    # Environment ON + ARM ON
    safety.arm_live_trading(
        token=VALID_TOKEN,
        armed_by="test",
    )

    status = safety.combined_live_gate_status(
        environment_enabled=True,
    )

    assert status["environment_enabled"] is True
    assert status["explicitly_armed"] is True
    assert status["execution_gate_open"] is True


def test_environment_disabled_blocks_even_when_armed(
    monkeypatch,
):
    _reset_gate(monkeypatch)

    monkeypatch.setenv(
        "RAYMOND_LIVE_ARM_TOKEN",
        VALID_TOKEN,
    )

    safety.arm_live_trading(
        token=VALID_TOKEN,
        armed_by="test",
    )

    status = safety.combined_live_gate_status(
        environment_enabled=False,
    )

    assert status["explicitly_armed"] is True
    assert status["environment_enabled"] is False
    assert status["execution_gate_open"] is False


def test_environment_enabled_does_not_arm_by_itself(
    monkeypatch,
):
    _reset_gate(monkeypatch)

    status = safety.combined_live_gate_status(
        environment_enabled=True,
    )

    assert status["environment_enabled"] is True
    assert status["explicitly_armed"] is False
    assert status["execution_gate_open"] is False


def test_token_configuration_status_never_returns_secret(
    monkeypatch,
):
    _reset_gate(monkeypatch)

    monkeypatch.setenv(
        "RAYMOND_LIVE_ARM_TOKEN",
        VALID_TOKEN,
    )

    status = safety.token_configuration_status()

    assert status["configured"] is True
    assert status["minimum_length"] >= 32
    assert (
        status["environment_variable"]
        == "RAYMOND_LIVE_ARM_TOKEN"
    )

    assert VALID_TOKEN not in str(status)


def test_live_safety_status_never_returns_token(
    monkeypatch,
):
    _reset_gate(monkeypatch)

    monkeypatch.setenv(
        "RAYMOND_LIVE_ARM_TOKEN",
        VALID_TOKEN,
    )

    status = safety.live_safety_status()

    assert status["arm_token_configured"] is True
    assert VALID_TOKEN not in str(status)


def test_wrong_token_does_not_change_existing_disarmed_state(
    monkeypatch,
):
    _reset_gate(monkeypatch)

    monkeypatch.setenv(
        "RAYMOND_LIVE_ARM_TOKEN",
        VALID_TOKEN,
    )

    try:
        safety.arm_live_trading(
            token="wrong-" + ("x" * 40),
            armed_by="attacker",
        )
        assert False, "Invalid token must not arm LIVE trading."
    except PermissionError:
        pass

    status = safety.live_safety_status()

    assert status["armed"] is False
    assert status["armed_by"] is None
    assert status["armed_at"] is None


def test_restart_style_state_is_disarmed(
    monkeypatch,
):
    """
    The production gate stores ARM state only in process memory.

    This test simulates the important restart invariant:
    after clearing the in-memory state, LIVE starts disarmed even
    when the server-side token remains configured.
    """

    _reset_gate(monkeypatch)

    monkeypatch.setenv(
        "RAYMOND_LIVE_ARM_TOKEN",
        VALID_TOKEN,
    )

    safety.arm_live_trading(
        token=VALID_TOKEN,
        armed_by="test",
    )

    assert safety.is_live_armed() is True

    # Simulate the state reset that occurs on process restart.
    safety.disarm_live_trading(
        reason="simulated_restart",
    )

    status = safety.live_safety_status()

    assert status["armed"] is False
    assert status["arm_token_configured"] is True
    assert status["fail_closed"] is True


def test_disarm_does_not_reconfigure_or_expose_token(
    monkeypatch,
):
    _reset_gate(monkeypatch)

    monkeypatch.setenv(
        "RAYMOND_LIVE_ARM_TOKEN",
        VALID_TOKEN,
    )

    result = safety.disarm_live_trading(
        reason="test",
    )

    assert result["armed"] is False
    assert result["arm_token_configured"] is True
    assert VALID_TOKEN not in str(result)
