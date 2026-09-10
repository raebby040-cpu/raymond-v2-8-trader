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
    SymbolSpecification,
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


def test_symbol_specification_defaults():
    specification = SymbolSpecification(
        symbol="XAUUSD",
        digits=2,
        point=0.01,
        tick_size=0.01,
        tick_value=1.0,
        tick_value_profit=1.0,
        tick_value_loss=1.0,
        contract_size=100.0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
        volume_limit=0.0,
        trade_mode=4,
        trade_execution_mode=2,
        trade_stops_level=0,
        trade_freeze_level=0,
        currency_base="XAU",
        currency_profit="USD",
        currency_margin="XAU",
        spread=30,
        spread_float=True,
    )

    specification.validate()

    assert specification.symbol == "XAUUSD"
    assert specification.tick_size == 0.01
    assert specification.tick_value_loss == 1.0
    assert specification.volume_step == 0.01


def test_symbol_aware_position_size():
    engine = RiskEngine()

    specification = SymbolSpecification(
        symbol="XAUUSD",
        digits=2,
        point=0.01,
        tick_size=0.01,
        tick_value=1.0,
        tick_value_profit=1.0,
        tick_value_loss=1.0,
        contract_size=100.0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
        volume_limit=0.0,
        trade_mode=4,
        trade_execution_mode=2,
        trade_stops_level=0,
        trade_freeze_level=0,
        currency_base="XAU",
        currency_profit="USD",
        currency_margin="XAU",
        spread=30,
        spread_float=True,
    )

    volume = engine.calculate_position_size_from_symbol(
        equity=10000,
        entry_price=3350.00,
        stop_loss_price=3340.00,
        specification=specification,
    )

    assert volume == 1.0


def test_symbol_aware_position_size_respects_max_volume():
    engine = RiskEngine()

    specification = SymbolSpecification(
        symbol="XAUUSD",
        digits=2,
        point=0.01,
        tick_size=0.01,
        tick_value=1.0,
        tick_value_profit=1.0,
        tick_value_loss=1.0,
        contract_size=100.0,
        volume_min=0.01,
        volume_max=0.50,
        volume_step=0.01,
        volume_limit=0.0,
        trade_mode=4,
        trade_execution_mode=2,
        trade_stops_level=0,
        trade_freeze_level=0,
        currency_base="XAU",
        currency_profit="USD",
        currency_margin="XAU",
        spread=30,
        spread_float=True,
    )

    volume = engine.calculate_position_size_from_symbol(
        equity=10000,
        entry_price=3350.00,
        stop_loss_price=3340.00,
        specification=specification,
    )

    assert volume == 0.50


def test_symbol_specification_rejects_invalid_tick_size():
    specification = SymbolSpecification(
        symbol="XAUUSD",
        digits=2,
        point=0.01,
        tick_size=0,
        tick_value=1.0,
        tick_value_profit=1.0,
        tick_value_loss=1.0,
        contract_size=100.0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
        volume_limit=0.0,
        trade_mode=4,
        trade_execution_mode=2,
        trade_stops_level=0,
        trade_freeze_level=0,
        currency_base="XAU",
        currency_profit="USD",
        currency_margin="XAU",
        spread=30,
        spread_float=True,
    )

    with pytest.raises(RiskEngineError):
        specification.validate()


def test_symbol_specification_rejects_invalid_volume_step():
    specification = SymbolSpecification(
        symbol="XAUUSD",
        digits=2,
        point=0.01,
        tick_size=0.01,
        tick_value=1.0,
        tick_value_profit=1.0,
        tick_value_loss=1.0,
        contract_size=100.0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0,
        volume_limit=0.0,
        trade_mode=4,
        trade_execution_mode=2,
        trade_stops_level=0,
        trade_freeze_level=0,
        currency_base="XAU",
        currency_profit="USD",
        currency_margin="XAU",
        spread=30,
        spread_float=True,
    )

    with pytest.raises(RiskEngineError):
        specification.validate()


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
