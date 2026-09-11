"""
Step 15 - Application trading pipeline integration tests.
"""

import pytest

from app.ai_trading_decision import (
    AIDirection,
    AITradingDecisionEngine,
)
from app.execution_gateway import (
    PaperExecutionGateway,
)
from app.risk_engine import (
    RiskConfig,
    RiskEngine,
    SymbolSpecification,
)
from app.technical_indicators import (
    IndicatorResult,
)
from app.trading_pipeline_service import (
    PaperRiskState,
    TradingPipelineService,
)


def _symbol_specification() -> SymbolSpecification:
    return SymbolSpecification(
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


def _bullish_indicator_result() -> IndicatorResult:
    return IndicatorResult(
        symbol="XAUUSD",
        timeframe="H1",
        close=2300.0,
        ema20=2295.0,
        ema50=2285.0,
        rsi14=60.0,
        atr14=10.0,
        macd=5.0,
        macd_signal=3.0,
        macd_histogram=2.0,
        trend="Bullish",
        score=80,
        signal="BUY",
        candles_used=200,
    )


def _bearish_indicator_result() -> IndicatorResult:
    return IndicatorResult(
        symbol="XAUUSD",
        timeframe="H1",
        close=2300.0,
        ema20=2305.0,
        ema50=2315.0,
        rsi14=40.0,
        atr14=10.0,
        macd=-5.0,
        macd_signal=-3.0,
        macd_histogram=-2.0,
        trend="Bearish",
        score=20,
        signal="SELL",
        candles_used=200,
    )


def _neutral_indicator_result() -> IndicatorResult:
    return IndicatorResult(
        symbol="XAUUSD",
        timeframe="H1",
        close=2300.0,
        ema20=2300.0,
        ema50=2300.0,
        rsi14=50.0,
        atr14=10.0,
        macd=0.0,
        macd_signal=0.0,
        macd_histogram=0.0,
        trend="Neutral",
        score=50,
        signal="WAIT",
        candles_used=200,
    )


def _candles():
    return [
        {
            "time": index,
            "open": 2299.0,
            "high": 2301.0,
            "low": 2298.0,
            "close": 2300.0,
        }
        for index in range(200)
    ]


def _service(
    *,
    risk_engine=None,
) -> TradingPipelineService:
    return TradingPipelineService(
        ai_engine=AITradingDecisionEngine(),
        risk_engine=(
            risk_engine
            or RiskEngine(
                RiskConfig(
                    risk_per_trade_percent=1.0,
                    max_daily_loss_percent=3.0,
                    max_open_positions=3,
                    max_total_exposure_percent=100.0,
                    require_stop_loss=True,
                    min_risk_reward=1.5,
                )
            )
        ),
        execution_gateway=PaperExecutionGateway(
            live_trading_enabled=False,
        ),
    )


def test_indicator_result_maps_to_technical_context():
    service = _service()

    result = _bullish_indicator_result()

    context = service.indicator_to_context(
        result
    )

    assert context.symbol == "XAUUSD"
    assert context.timeframe == "H1"
    assert context.close == 2300.0
    assert context.ema20 == 2295.0
    assert context.ema50 == 2285.0
    assert context.rsi14 == 60.0
    assert context.atr14 == 10.0
    assert context.trend == "Bullish"
    assert context.score == 80
    assert context.signal == "BUY"
    assert context.candles_used == 200


def test_build_context_uses_existing_indicator_engine(
    monkeypatch,
):
    service = _service()

    expected = _bullish_indicator_result()

    def fake_calculate_indicators(
        *,
        symbol,
        timeframe,
        candles,
    ):
        assert symbol == "XAUUSD"
        assert timeframe == "H1"
        assert len(candles) == 200

        return expected

    monkeypatch.setattr(
        "app.trading_pipeline_service.calculate_indicators",
        fake_calculate_indicators,
    )

    context = service.build_context(
        symbol="XAUUSD",
        timeframe="H1",
        candles=_candles(),
    )

    assert context.symbol == "XAUUSD"
    assert context.trend == "Bullish"
    assert context.signal == "BUY"
    assert context.score == 80


def test_decision_path_produces_buy(
    monkeypatch,
):
    service = _service()

    monkeypatch.setattr(
        "app.trading_pipeline_service.calculate_indicators",
        lambda **kwargs: _bullish_indicator_result(),
    )

    decision = service.evaluate_decision(
        symbol="XAUUSD",
        timeframe="H1",
        candles=_candles(),
    )

    assert decision.direction is AIDirection.BUY
    assert decision.proposal is not None
    assert decision.proposal.stop_loss is not None
    assert decision.proposal.take_profit is not None


def test_decision_path_produces_sell(
    monkeypatch,
):
    service = _service()

    monkeypatch.setattr(
        "app.trading_pipeline_service.calculate_indicators",
        lambda **kwargs: _bearish_indicator_result(),
    )

    decision = service.evaluate_decision(
        symbol="XAUUSD",
        timeframe="H1",
        candles=_candles(),
    )

    assert decision.direction is AIDirection.SELL
    assert decision.proposal is not None


def test_decision_path_produces_wait(
    monkeypatch,
):
    service = _service()

    monkeypatch.setattr(
        "app.trading_pipeline_service.calculate_indicators",
        lambda **kwargs: _neutral_indicator_result(),
    )

    decision = service.evaluate_decision(
        symbol="XAUUSD",
        timeframe="H1",
        candles=_candles(),
    )

    assert decision.direction is AIDirection.WAIT
    assert decision.proposal is None


@pytest.mark.asyncio
async def test_risk_rejection_stops_before_paper_execution(
    monkeypatch,
):
    risk_engine = RiskEngine(
        RiskConfig(
            risk_per_trade_percent=1.0,
            max_daily_loss_percent=3.0,
            max_open_positions=3,
            max_total_exposure_percent=100.0,
            require_stop_loss=True,
            min_risk_reward=1.5,
        )
    )

    service = _service(
        risk_engine=risk_engine,
    )

    monkeypatch.setattr(
        "app.trading_pipeline_service.calculate_indicators",
        lambda **kwargs: _bullish_indicator_result(),
    )

    result = await service.execute_paper(
        symbol="XAUUSD",
        timeframe="H1",
        candles=_candles(),
        specification=_symbol_specification(),
        account_equity=10_000.0,
        risk_state=PaperRiskState(
            daily_loss=500.0,
            open_positions=0,
            total_exposure=0.0,
        ),
    )

    assert result.risk_decision is not None
    assert result.risk_decision.allowed is False
    assert result.execution_result is None


@pytest.mark.asyncio
async def test_wait_never_reaches_execution(
    monkeypatch,
):
    service = _service()

    monkeypatch.setattr(
        "app.trading_pipeline_service.calculate_indicators",
        lambda **kwargs: _neutral_indicator_result(),
    )

    result = await service.execute_paper(
        symbol="XAUUSD",
        timeframe="H1",
        candles=_candles(),
        specification=_symbol_specification(),
        account_equity=10_000.0,
        risk_state=PaperRiskState(
            daily_loss=0.0,
            open_positions=0,
            total_exposure=0.0,
        ),
    )

    assert result.decision.direction is AIDirection.WAIT
    assert result.risk_decision is None
    assert result.execution_result is None


def test_serialization_contains_expected_layers(
    monkeypatch,
):
    service = _service()

    monkeypatch.setattr(
        "app.trading_pipeline_service.calculate_indicators",
        lambda **kwargs: _neutral_indicator_result(),
    )

    result = service.evaluate_risk(
        symbol="XAUUSD",
        timeframe="H1",
        candles=_candles(),
        specification=_symbol_specification(),
        account_equity=10_000.0,
        risk_state=PaperRiskState(
            daily_loss=0.0,
            open_positions=0,
            total_exposure=0.0,
        ),
    )

    response = service.serialize_step14_result(
        result
    )

    assert "decision" in response
    assert "risk" in response
    assert "position_size" in response
    assert "execution" in response

    assert (
        response["decision"]["direction"]
        == "wait"
    )
