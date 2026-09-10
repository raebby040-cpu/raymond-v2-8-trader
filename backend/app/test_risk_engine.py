from app.risk_engine import (
    RiskConfig,
    RiskDecision,
    RiskEngine,
    RiskEngineError,
    SymbolSpecification,
)


def make_symbol_specification(**overrides):
    values = {
        "symbol": "XAUUSD",
        "digits": 2,
        "point": 0.01,
        "tick_size": 0.01,
        "tick_value": 1.0,
        "tick_value_profit": 1.0,
        "tick_value_loss": 1.0,
        "contract_size": 100.0,
        "volume_min": 0.01,
        "volume_max": 100.0,
        "volume_step": 0.01,
        "volume_limit": 0.0,
        "trade_mode": RiskEngine.TRADE_MODE_FULL,
        "trade_execution_mode": 0,
        "trade_stops_level": 0,
        "trade_freeze_level": 0,
        "currency_base": "XAU",
        "currency_profit": "USD",
        "currency_margin": "USD",
        "spread": 10,
        "spread_float": True,
    }

    values.update(overrides)
    return SymbolSpecification(**values)


def test_default_risk_config():
    config = RiskConfig()

    assert config.risk_per_trade_percent == 1.0
    assert config.max_daily_loss_percent == 3.0
    assert config.max_open_positions == 3
    assert config.max_total_exposure_percent == 5.0
    assert config.require_stop_loss is True
    assert config.min_risk_reward == 1.5


def test_risk_config_rejects_invalid_risk_percent():
    try:
        RiskConfig(risk_per_trade_percent=0).validate()
        assert False
    except RiskEngineError:
        assert True


def test_risk_amount():
    engine = RiskEngine()

    assert engine.risk_amount(10000) == 100


def test_daily_loss_limit():
    engine = RiskEngine()

    assert engine.daily_loss_limit(10000) == 300


def test_total_exposure_limit():
    engine = RiskEngine()

    assert engine.total_exposure_limit(10000) == 500


def test_position_size():
    engine = RiskEngine()

    volume = engine.calculate_position_size(
        equity=10000,
        entry_price=2000,
        stop_loss_price=1990,
        risk_per_unit=100,
        volume_step=0.01,
        min_volume=0.01,
        max_volume=100,
    )

    assert volume == 1.0


def test_position_size_respects_max_volume():
    engine = RiskEngine()

    volume = engine.calculate_position_size(
        equity=10000,
        entry_price=2000,
        stop_loss_price=1990,
        risk_per_unit=1,
        volume_step=0.01,
        min_volume=0.01,
        max_volume=0.50,
    )

    assert volume == 0.50


def test_position_size_returns_zero_when_below_minimum():
    engine = RiskEngine()

    volume = engine.calculate_position_size(
        equity=10000,
        entry_price=2000,
        stop_loss_price=1999,
        risk_per_unit=100000,
        volume_step=0.01,
        min_volume=0.01,
        max_volume=100,
    )

    assert volume == 0.0


def test_symbol_aware_position_size():
    engine = RiskEngine()

    specification = make_symbol_specification()

    volume = engine.calculate_position_size_from_symbol(
        equity=10000,
        entry_price=2000,
        stop_loss_price=1990,
        specification=specification,
    )

    assert volume == 0.10


def test_symbol_aware_position_size_respects_max_volume():
    engine = RiskEngine()

    specification = make_symbol_specification(
        tick_value_loss=0.10,
        volume_max=0.50,
    )

    volume = engine.calculate_position_size_from_symbol(
        equity=10000,
        entry_price=2000,
        stop_loss_price=1990,
        specification=specification,
    )

    assert volume == 0.50


def test_stop_loss_required():
    engine = RiskEngine()

    try:
        engine.validate_stop_loss(
            entry_price=2000,
            stop_loss_price=None,
        )
        assert False
    except RiskEngineError:
        assert True


def test_stop_loss_cannot_equal_entry():
    engine = RiskEngine()

    try:
        engine.validate_stop_loss(
            entry_price=2000,
            stop_loss_price=2000,
        )
        assert False
    except RiskEngineError:
        assert True


def test_valid_stop_loss():
    engine = RiskEngine()

    engine.validate_stop_loss(
        entry_price=2000,
        stop_loss_price=1990,
    )


def test_valid_risk_reward():
    engine = RiskEngine()

    ratio = engine.validate_risk_reward(
        entry_price=2000,
        stop_loss_price=1990,
        take_profit_price=2015,
    )

    assert ratio == 1.5


def test_rejects_low_risk_reward():
    engine = RiskEngine()

    try:
        engine.validate_risk_reward(
            entry_price=2000,
            stop_loss_price=1990,
            take_profit_price=2005,
        )
        assert False
    except RiskEngineError:
        assert True


def test_buy_allowed_on_full_trade_mode():
    engine = RiskEngine()

    engine.validate_trade_direction(
        RiskEngine.TRADE_MODE_FULL,
        "BUY",
    )


def test_sell_allowed_on_full_trade_mode():
    engine = RiskEngine()

    engine.validate_trade_direction(
        RiskEngine.TRADE_MODE_FULL,
        "SELL",
    )


def test_buy_allowed_on_long_only_symbol():
    engine = RiskEngine()

    engine.validate_trade_direction(
        RiskEngine.TRADE_MODE_LONGONLY,
        "BUY",
    )


def test_sell_rejected_on_long_only_symbol():
    engine = RiskEngine()

    try:
        engine.validate_trade_direction(
            RiskEngine.TRADE_MODE_LONGONLY,
            "SELL",
        )
        assert False
    except RiskEngineError:
        assert True


def test_buy_rejected_on_short_only_symbol():
    engine = RiskEngine()

    try:
        engine.validate_trade_direction(
            RiskEngine.TRADE_MODE_SHORTONLY,
            "BUY",
        )
        assert False
    except RiskEngineError:
        assert True


def test_disabled_symbol_rejected():
    engine = RiskEngine()

    try:
        engine.validate_trade_direction(
            RiskEngine.TRADE_MODE_DISABLED,
            "BUY",
        )
        assert False
    except RiskEngineError:
        assert True


def test_close_only_symbol_rejected():
    engine = RiskEngine()

    try:
        engine.validate_trade_direction(
            RiskEngine.TRADE_MODE_CLOSEONLY,
            "BUY",
        )
        assert False
    except RiskEngineError:
        assert True


def test_valid_volume():
    engine = RiskEngine()
    specification = make_symbol_specification()

    engine.validate_volume(
        volume=0.10,
        specification=specification,
    )


def test_volume_below_minimum_rejected():
    engine = RiskEngine()
    specification = make_symbol_specification(
        volume_min=0.10,
    )

    try:
        engine.validate_volume(
            volume=0.01,
            specification=specification,
        )
        assert False
    except RiskEngineError:
        assert True


def test_volume_above_maximum_rejected():
    engine = RiskEngine()
    specification = make_symbol_specification(
        volume_max=1.0,
    )

    try:
        engine.validate_volume(
            volume=1.01,
            specification=specification,
        )
        assert False
    except RiskEngineError:
        assert True


def test_volume_step_rejected():
    engine = RiskEngine()
    specification = make_symbol_specification(
        volume_step=0.10,
    )

    try:
        engine.validate_volume(
            volume=0.15,
            specification=specification,
        )
        assert False
    except RiskEngineError:
        assert True


def test_directional_volume_limit_rejected():
    engine = RiskEngine()
    specification = make_symbol_specification(
        volume_limit=1.0,
    )

    try:
        engine.validate_volume(
            volume=0.60,
            specification=specification,
            existing_direction_volume=0.50,
        )
        assert False
    except RiskEngineError:
        assert True


def make_valid_pre_trade_kwargs(**overrides):
    values = {
        "equity": 10000,
        "daily_loss": 0,
        "open_positions": 1,
        "current_exposure": 100,
        "proposed_exposure": 100,
        "entry_price": 2000,
        "stop_loss_price": 1990,
        "take_profit_price": 2015,
        "volume": 0.10,
        "side": "BUY",
        "specification": make_symbol_specification(),
        "existing_direction_volume": 0.0,
    }

    values.update(overrides)
    return values


def test_pre_trade_check_allows_valid_trade():
    engine = RiskEngine()

    decision = engine.pre_trade_check(
        **make_valid_pre_trade_kwargs()
    )

    assert isinstance(decision, RiskDecision)
    assert decision.allowed is True
    assert decision.reason == "risk checks passed"
    assert decision.risk_amount == 100
    assert decision.daily_loss_limit == 300
    assert decision.total_exposure_limit == 500


def test_pre_trade_check_rejects_daily_loss_limit():
    engine = RiskEngine()

    decision = engine.pre_trade_check(
        **make_valid_pre_trade_kwargs(
            daily_loss=300,
        )
    )

    assert decision.allowed is False
    assert decision.reason == "maximum daily loss reached"


def test_pre_trade_check_rejects_max_open_positions():
    engine = RiskEngine()

    decision = engine.pre_trade_check(
        **make_valid_pre_trade_kwargs(
            open_positions=3,
        )
    )

    assert decision.allowed is False
    assert decision.reason == "maximum open positions reached"


def test_pre_trade_check_rejects_total_exposure():
    engine = RiskEngine()

    decision = engine.pre_trade_check(
        **make_valid_pre_trade_kwargs(
            current_exposure=450,
            proposed_exposure=100,
        )
    )

    assert decision.allowed is False
    assert decision.reason == "maximum total exposure exceeded"


def test_pre_trade_check_rejects_missing_stop_loss():
    engine = RiskEngine()

    decision = engine.pre_trade_check(
        **make_valid_pre_trade_kwargs(
            stop_loss_price=None,
        )
    )

    assert decision.allowed is False
    assert decision.reason == "stop loss is required"


def test_pre_trade_check_rejects_low_risk_reward():
    engine = RiskEngine()

    decision = engine.pre_trade_check(
        **make_valid_pre_trade_kwargs(
            take_profit_price=2005,
        )
    )

    assert decision.allowed is False
    assert (
        decision.reason
        == "risk/reward ratio is below the configured minimum"
    )


def test_pre_trade_check_rejects_disabled_symbol():
    engine = RiskEngine()

    specification = make_symbol_specification(
        trade_mode=RiskEngine.TRADE_MODE_DISABLED,
    )

    decision = engine.pre_trade_check(
        **make_valid_pre_trade_kwargs(
            specification=specification,
        )
    )

    assert decision.allowed is False
    assert decision.reason == "symbol trading is disabled"


def test_pre_trade_check_rejects_invalid_volume():
    engine = RiskEngine()

    decision = engine.pre_trade_check(
        **make_valid_pre_trade_kwargs(
            volume=0.015,
        )
    )

    assert decision.allowed is False
    assert decision.reason == (
        "volume is not aligned to broker volume step"
    )


def test_pre_trade_check_rejects_wrong_direction():
    engine = RiskEngine()

    specification = make_symbol_specification(
        trade_mode=RiskEngine.TRADE_MODE_LONGONLY,
    )

    decision = engine.pre_trade_check(
        **make_valid_pre_trade_kwargs(
            side="SELL",
            specification=specification,
        )
    )

    assert decision.allowed is False
    assert decision.reason == (
        "symbol allows long positions only"
    )


def test_pre_trade_check_rejects_broker_volume_limit():
    engine = RiskEngine()

    specification = make_symbol_specification(
        volume_limit=0.15,
    )

    decision = engine.pre_trade_check(
        **make_valid_pre_trade_kwargs(
            volume=0.10,
            existing_direction_volume=0.10,
            specification=specification,
        )
    )

    assert decision.allowed is False
    assert decision.reason == (
        "volume exceeds broker directional volume limit"
    )
