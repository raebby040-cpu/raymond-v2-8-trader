from app.risk_engine import (
    RiskConfig,
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
        "spread": 20,
        "spread_float": True,
    }

    values.update(overrides)
    return SymbolSpecification(**values)


def test_risk_amount():
    engine = RiskEngine()

    assert engine.risk_amount(10000) == 100.0


def test_daily_loss_limit():
    engine = RiskEngine()

    assert engine.daily_loss_limit(10000) == 300.0


def test_total_exposure_limit():
    engine = RiskEngine()

    assert engine.total_exposure_limit(10000) == 500.0


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


def test_position_size_rounds_down_to_volume_step():
    engine = RiskEngine()

    volume = engine.calculate_position_size(
        equity=10000,
        entry_price=2000,
        stop_loss_price=1990,
        risk_per_unit=333,
        volume_step=0.01,
        min_volume=0.01,
        max_volume=100,
    )

    assert volume == 0.03


def test_position_size_returns_zero_below_minimum():
    engine = RiskEngine()

    volume = engine.calculate_position_size(
        equity=100,
        entry_price=2000,
        stop_loss_price=1990,
        risk_per_unit=100,
        volume_step=0.01,
        min_volume=0.01,
        max_volume=100,
    )

    assert volume == 0.0


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
    except RiskEngineError as exc:
        assert str(exc) == "stop loss is required"


def test_stop_loss_cannot_equal_entry():
    engine = RiskEngine()

    try:
        engine.validate_stop_loss(
            entry_price=2000,
            stop_loss_price=2000,
        )
        assert False
    except RiskEngineError as exc:
        assert str(exc) == "stop loss cannot equal entry price"


def test_risk_reward():
    engine = RiskEngine()

    ratio = engine.validate_risk_reward(
        entry_price=2000,
        stop_loss_price=1990,
        take_profit_price=2020,
    )

    assert ratio == 2.0


def test_risk_reward_rejects_low_ratio():
    engine = RiskEngine()

    try:
        engine.validate_risk_reward(
            entry_price=2000,
            stop_loss_price=1990,
            take_profit_price=2010,
        )
        assert False
    except RiskEngineError as exc:
        assert (
            str(exc)
            == "risk/reward ratio is below the configured minimum"
        )


def test_disabled_symbol_rejected():
    engine = RiskEngine()

    try:
        engine.validate_trade_direction(
            trade_mode=RiskEngine.TRADE_MODE_DISABLED,
            side="BUY",
        )
        assert False
    except RiskEngineError as exc:
        assert str(exc) == "symbol trading is disabled"


def test_close_only_symbol_rejected():
    engine = RiskEngine()

    try:
        engine.validate_trade_direction(
            trade_mode=RiskEngine.TRADE_MODE_CLOSEONLY,
            side="BUY",
        )
        assert False
    except RiskEngineError as exc:
        assert str(exc) == "symbol is close-only"


def test_long_only_rejects_sell():
    engine = RiskEngine()

    try:
        engine.validate_trade_direction(
            trade_mode=RiskEngine.TRADE_MODE_LONGONLY,
            side="SELL",
        )
        assert False
    except RiskEngineError as exc:
        assert str(exc) == "symbol allows long positions only"


def test_short_only_rejects_buy():
    engine = RiskEngine()

    try:
        engine.validate_trade_direction(
            trade_mode=RiskEngine.TRADE_MODE_SHORTONLY,
            side="BUY",
        )
        assert False
    except RiskEngineError as exc:
        assert str(exc) == "symbol allows short positions only"


def test_valid_buy_direction():
    engine = RiskEngine()

    engine.validate_trade_direction(
        trade_mode=RiskEngine.TRADE_MODE_FULL,
        side="BUY",
    )


def test_valid_sell_direction():
    engine = RiskEngine()

    engine.validate_trade_direction(
        trade_mode=RiskEngine.TRADE_MODE_FULL,
        side="SELL",
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
    except RiskEngineError as exc:
        assert str(exc) == "volume is below broker minimum"


def test_volume_above_maximum_rejected():
    engine = RiskEngine()

    specification = make_symbol_specification(
        volume_max=1.00,
    )

    try:
        engine.validate_volume(
            volume=2.00,
            specification=specification,
        )
        assert False
    except RiskEngineError as exc:
        assert str(exc) == "volume exceeds broker maximum"


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
    except RiskEngineError as exc:
        assert (
            str(exc)
            == "volume is not aligned to broker volume step"
        )


def test_directional_volume_limit_rejected():
    engine = RiskEngine()

    specification = make_symbol_specification(
        volume_limit=1.00,
    )

    try:
        engine.validate_volume(
            volume=0.60,
            specification=specification,
            existing_direction_volume=0.50,
        )
        assert False
    except RiskEngineError as exc:
        assert (
            str(exc)
            == "volume exceeds broker directional volume limit"
        )


def test_pre_trade_check_allows_valid_trade():
    engine = RiskEngine()

    specification = make_symbol_specification()

    decision = engine.pre_trade_check(
        equity=10000,
        daily_loss=0,
        open_positions=0,
        current_exposure=0,
        proposed_exposure=100,
        entry_price=2000,
        stop_loss_price=1990,
        take_profit_price=2020,
        volume=0.10,
        side="BUY",
        specification=specification,
    )

    assert decision.allowed is True
    assert decision.reason == "risk checks passed"


def test_pre_trade_check_rejects_daily_loss_limit():
    engine = RiskEngine()

    specification = make_symbol_specification()

    decision = engine.pre_trade_check(
        equity=10000,
        daily_loss=300,
        open_positions=0,
        current_exposure=0,
        proposed_exposure=100,
        entry_price=2000,
        stop_loss_price=1990,
        take_profit_price=2020,
        volume=0.10,
        side="BUY",
        specification=specification,
    )

    assert decision.allowed is False
    assert decision.reason == "maximum daily loss reached"


def test_pre_trade_check_rejects_max_open_positions():
    engine = RiskEngine()

    specification = make_symbol_specification()

    decision = engine.pre_trade_check(
        equity=10000,
        daily_loss=0,
        open_positions=3,
        current_exposure=0,
        proposed_exposure=100,
        entry_price=2000,
        stop_loss_price=1990,
        take_profit_price=2020,
        volume=0.10,
        side="BUY",
        specification=specification,
    )

    assert decision.allowed is False
    assert decision.reason == "maximum open positions reached"


def test_pre_trade_check_rejects_total_exposure():
    engine = RiskEngine()

    specification = make_symbol_specification()

    decision = engine.pre_trade_check(
        equity=10000,
        daily_loss=0,
        open_positions=0,
        current_exposure=450,
        proposed_exposure=100,
        entry_price=2000,
        stop_loss_price=1990,
        take_profit_price=2020,
        volume=0.10,
        side="BUY",
        specification=specification,
    )

    assert decision.allowed is False
    assert decision.reason == "maximum total exposure exceeded"


def test_pre_trade_check_rejects_missing_stop_loss():
    engine = RiskEngine()

    specification = make_symbol_specification()

    decision = engine.pre_trade_check(
        equity=10000,
        daily_loss=0,
        open_positions=0,
        current_exposure=0,
        proposed_exposure=100,
        entry_price=2000,
        stop_loss_price=None,
        take_profit_price=2020,
        volume=0.10,
        side="BUY",
        specification=specification,
    )

    assert decision.allowed is False
    assert decision.reason == "stop loss is required"


def test_pre_trade_check_rejects_low_risk_reward():
    engine = RiskEngine()

    specification = make_symbol_specification()

    decision = engine.pre_trade_check(
        equity=10000,
        daily_loss=0,
        open_positions=0,
        current_exposure=0,
        proposed_exposure=100,
        entry_price=2000,
        stop_loss_price=1990,
        take_profit_price=2010,
        volume=0.10,
        side="BUY",
        specification=specification,
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
        equity=10000,
        daily_loss=0,
        open_positions=0,
        current_exposure=0,
        proposed_exposure=100,
        entry_price=2000,
        stop_loss_price=1990,
        take_profit_price=2020,
        volume=0.10,
        side="BUY",
        specification=specification,
    )

    assert decision.allowed is False
    assert decision.reason == "symbol trading is disabled"


def test_pre_trade_check_rejects_invalid_volume():
    engine = RiskEngine()

    specification = make_symbol_specification(
        volume_min=0.10,
    )

    decision = engine.pre_trade_check(
        equity=10000,
        daily_loss=0,
        open_positions=0,
        current_exposure=0,
        proposed_exposure=100,
        entry_price=2000,
        stop_loss_price=1990,
        take_profit_price=2020,
        volume=0.01,
        side="BUY",
        specification=specification,
    )

    assert decision.allowed is False
    assert decision.reason == "volume is below broker minimum"
