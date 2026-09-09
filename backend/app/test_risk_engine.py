import os
import sys

import pytest


APP_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


from risk_engine import (  # noqa: E402
    RiskConfig,
    RiskEngine,
    RiskEngineError,
)


def test_default_risk_config():
    config = RiskConfig()

    assert config.risk_per_trade_percent == 1.0
    assert config.max_daily_loss_percent == 3.0
    assert config.max_open_positions == 3
    assert config.max_total_exposure_percent == 5.0
    assert config.require_stop_loss is True
    assert config.min_risk_reward == 1.5


def test_risk_amount():
    engine = RiskEngine()

    assert engine.risk_amount(10000) == 100.0
    assert engine.risk_amount(5000) == 50.0


def test_daily_loss_limit():
    engine = RiskEngine()

    assert engine.daily_loss_limit(10000) == 300.0


def test_position_size():
    engine = RiskEngine()

    volume = engine.calculate_position_size(
        equity=10000,
        entry_price=3350,
        stop_loss_price=3340,
        risk_per_unit=100,
        volume_step=0.01,
        min_volume=0.01,
    )

    assert volume == 1.0


def test_position_size_rounds_down():
    engine = RiskEngine()

    volume = engine.calculate_position_size(
        equity=10000,
        entry_price=3350,
        stop_loss_price=3340,
        risk_per_unit=73,
        volume_step=0.01,
        min_volume=0.01,
    )

    assert volume == 1.36


def test_position_size_below_minimum_returns_zero():
    engine = RiskEngine()

    volume = engine.calculate_position_size(
        equity=100,
        entry_price=3350,
        stop_loss_price=3340,
        risk_per_unit=100,
        volume_step=0.01,
        min_volume=0.10,
    )

    assert volume == 0.0


def test_required_stop_loss():
    engine = RiskEngine()

    with pytest.raises(RiskEngineError):
        engine.validate_stop_loss(
            entry_price=3350,
            stop_loss_price=None,
        )


def test_stop_loss_cannot_equal_entry():
    engine = RiskEngine()

    with pytest.raises(RiskEngineError):
        engine.validate_stop_loss(
            entry_price=3350,
            stop_loss_price=3350,
        )


def test_valid_risk_reward():
    engine = RiskEngine()

    ratio = engine.validate_risk_reward(
        entry_price=3350,
        stop_loss_price=3340,
        take_profit_price=3370,
    )

    assert ratio == 2.0


def test_reject_low_risk_reward():
    engine = RiskEngine()

    with pytest.raises(RiskEngineError):
        engine.validate_risk_reward(
            entry_price=3350,
            stop_loss_price=3340,
            take_profit_price=3360,
        )


def test_invalid_equity():
    engine = RiskEngine()

    with pytest.raises(RiskEngineError):
        engine.risk_amount(0)


def test_invalid_risk_config():
    with pytest.raises(RiskEngineError):
        RiskEngine(
            RiskConfig(
                risk_per_trade_percent=0
            )
)
