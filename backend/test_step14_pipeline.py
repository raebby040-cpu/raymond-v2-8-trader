from app.ai_trading_decision import (
    AIDirection,
    AITradingDecisionEngine,
    TechnicalContext,
)
from app.execution_gateway import (
    ExecutionGatewayError,
    PaperExecutionGateway,
)
from app.risk_engine import (
    RiskConfig,
    RiskEngine,
    SymbolSpecification,
)
from app.step14_pipeline import (
    Step14Pipeline,
    Step14PipelineError,
)


def context(**overrides):
    values = {
        "symbol": "XAUUSD",
        "timeframe": "M15",
        "close": 2000.0,
        "ema20": 2005.0,
        "ema50": 1995.0,
        "rsi14": 58.0,
        "atr14": 10.0,
        "macd": 1.0,
        "macd_signal": 0.5,
        "macd_histogram": 0.5,
        "trend": "Bullish",
        "score": 80.0,
        "signal": "BUY",
        "candles_used": 100,
    }

    values.update(overrides)
    return TechnicalContext(**values)


def specification():
    return SymbolSpecification(
        symbol="XAUUSD",
        digits=2,
        point=0.01,
        tick_size=0.01,
        tick_value=1.0,
        tick_value_profit=1.0,
        tick_value_loss=1.0,
        contract_size=1.0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
        volume_limit=100.0,
        trade_mode=4,
        trade_execution_mode=0,
        trade_stops_level=0,
        trade_freeze_level=0,
        currency_base="XAU",
        currency_profit="USD",
        currency_margin="USD",
        spread=10,
        spread_float=True,
    )


def make_pipeline():
    ai_engine = AITradingDecisionEngine()
    risk_engine = RiskEngine(
        RiskConfig(
            risk_per_trade_percent=1.0,
            max_daily_loss_percent=3.0,
            max_open_positions=3,
            max_total_exposure_percent=5.0,
            require_stop_loss=True,
            min_risk_reward=1.5,
        )
    )

    gateway = PaperExecutionGateway()

    return Step14Pipeline(
        ai_engine=ai_engine,
        risk_engine=risk_engine,
        execution_gateway=gateway,
    )


def test_step13_buy_flows_into_step14_risk_and_paper_execution():
    pipeline = make_pipeline()

    result = pipeline.evaluate_and_execute_paper(
        context(),
        specification(),
        account_equity=10_000.0,
    )

    assert result.decision.direction is AIDirection.BUY
    assert result.risk_decision is not None
    assert result.risk_decision.allowed is True
    assert result.execution_result is not None


def test_conflicting_ai_context_stops_before_risk_and_execution():
    pipeline = make_pipeline()

    result = pipeline.evaluate_and_execute_paper(
        context(
            trend="Bearish",
            signal="SELL",
            score=20.0,
        ),
        specification(),
        account_equity=10_000.0,
    )

    assert result.decision.direction is AIDirection.WAIT
    assert result.risk_decision is None
    assert result.execution_result is None


def test_risk_rejection_never_reaches_execution():
    pipeline = make_pipeline()

    result = pipeline.evaluate_and_execute_paper(
        context(),
        specification(),
        account_equity=10_000.0,
        daily_loss=300.0,
    )

    assert result.risk_decision is not None
    assert result.risk_decision.allowed is False
    assert result.execution_result is None


def test_live_enabled_gateway_is_rejected_by_step14():
    pipeline = make_pipeline()

    pipeline.execution_gateway.live_trading_enabled = True

    try:
        pipeline.evaluate_and_execute_paper(
            context(),
            specification(),
            account_equity=10_000.0,
        )
    except Step14PipelineError as exc:
        assert "Live trading" in str(exc)
    else:
        raise AssertionError(
            "Step 14 allowed a live-enabled gateway."
        )


def test_missing_atr_fails_closed_to_wait():
    pipeline = make_pipeline()

    result = pipeline.evaluate_and_execute_paper(
        context(atr14=None),
        specification(),
        account_equity=10_000.0,
    )

    assert result.decision.direction is AIDirection.WAIT
    assert result.risk_decision is None
    assert result.execution_result is None


def test_ai_direction_is_conservative():
    engine = AITradingDecisionEngine()

    buy = engine.evaluate(context())

    assert buy.direction is AIDirection.BUY

    wait = engine.evaluate(
        context(
            signal="BUY",
            trend="Bearish",
            score=80.0,
        )
    )

    assert wait.direction is AIDirection.WAIT


def test_paper_gateway_still_refuses_live_execution():
    gateway = PaperExecutionGateway()

    gateway.live_trading_enabled = True

    try:
        gateway.execute(
            None
        )
    except ExecutionGatewayError as exc:
        assert "live execution" in str(exc).lower()
    else:
        raise AssertionError(
            "Paper gateway accepted live execution."
        )
