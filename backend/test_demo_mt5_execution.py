"""
RAYMOND v2.8 - DEMO execution integration safety tests.

These tests exercise the DEMO execution boundary without requiring a
real MetaTrader 5 terminal or broker account.

They verify:
- deterministic signal identity
- persistent execution-state reconstruction
- duplicate signal blocking
- no duplicate broker order submission
- DEMO worker safety
- clean worker shutdown
- LIVE evaluation does not automatically execute
- LIVE payload validation
- broker market price remains controlled by the execution gateway
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.demo_execution_worker import DemoExecutionWorker
from app.demo_mt5_execution import (
    DemoExecutionResult,
    DemoMT5ExecutionEngine,
)
from app.execution_mode import ExecutionMode
from app.unified_execution_api import (
    ExecutionRequest,
    LiveExecutionPayload,
    evaluate_execution,
)


def _fake_record(**overrides):
    values = {
        "status": "verified",
        "execution_mode": "demo",
        "idempotency_key": "signal-1",
        "symbol": "XAUUSD",
        "side": "BUY",
        "volume": 0.01,
        "requested_price": 3000.10,
        "executed_price": 3000.10,
        "stop_loss": 2995.0,
        "take_profit": 3010.0,
        "order_ticket": 123,
        "deal_ticket": 456,
        "position_ticket": 789,
        "broker_retcode": 10009,
        "broker_comment": "done",
        "verified": True,
        "reason": "verified",
        "updated_at": SimpleNamespace(
            isoformat=lambda: "2026-10-08T00:00:00+00:00"
        ),
    }

    values.update(overrides)

    return SimpleNamespace(**values)


def test_signal_id_is_deterministic():
    engine = DemoMT5ExecutionEngine()

    first = engine.build_signal_id(
        symbol="XAUUSD",
        timeframe="M15",
        direction="BUY",
        entry_price=3000.10,
        stop_loss=2995.0,
        take_profit=3010.0,
        candle_time=123456,
    )

    second = engine.build_signal_id(
        symbol="XAUUSD",
        timeframe="M15",
        direction="BUY",
        entry_price=3000.10,
        stop_loss=2995.0,
        take_profit=3010.0,
        candle_time=123456,
    )

    assert first == second
    assert len(first) == 64


def test_signal_id_changes_when_trade_parameters_change():
    engine = DemoMT5ExecutionEngine()

    first = engine.build_signal_id(
        symbol="XAUUSD",
        timeframe="M15",
        direction="BUY",
        entry_price=3000.10,
        stop_loss=2995.0,
        take_profit=3010.0,
        candle_time=123456,
    )

    changed_tp = engine.build_signal_id(
        symbol="XAUUSD",
        timeframe="M15",
        direction="BUY",
        entry_price=3000.10,
        stop_loss=2995.0,
        take_profit=3015.0,
        candle_time=123456,
    )

    assert first != changed_tp


def test_broker_comment_contains_signal_fingerprint():
    signal_id = "a" * 64

    comment = DemoMT5ExecutionEngine._broker_comment(
        signal_id
    )

    assert comment == "RAYMOND_D_" + "a" * 16


def test_record_to_result_preserves_persistent_execution_state():
    record = _fake_record()

    result = DemoMT5ExecutionEngine._record_to_result(
        record
    )

    assert isinstance(
        result,
        DemoExecutionResult,
    )

    assert result.execution_mode == "demo"
    assert result.status == "verified"
    assert result.signal_id == "signal-1"
    assert result.symbol == "XAUUSD"
    assert result.side == "BUY"
    assert result.volume == 0.01
    assert result.verified is True
    assert result.order_ticket == 123
    assert result.deal_ticket == 456
    assert result.position_ticket == 789


@pytest.mark.asyncio
async def test_duplicate_signal_is_blocked_before_order_send(
    monkeypatch,
):
    engine = DemoMT5ExecutionEngine()

    class FakeMT5:
        ORDER_TYPE_BUY = 0
        POSITION_TYPE_BUY = 0

        def positions_get(self, symbol=None):
            return ()

        def symbol_info_tick(self, symbol):
            return SimpleNamespace(
                ask=3000.20,
                bid=3000.00,
            )

        def order_send(self, request):
            raise AssertionError(
                "Duplicate signal must never reach order_send."
            )

    fake_mt5 = FakeMT5()

    monkeypatch.setattr(
        "app.demo_mt5_execution.mt5",
        fake_mt5,
    )

    async def fake_account():
        return {
            "equity": 1000.0,
            "balance": 1000.0,
        }

    async def fake_spec(symbol):
        return SimpleNamespace()

    async def fake_candles(**kwargs):
        return [
            {
                "time": 123456,
                "open": 3000.0,
                "high": 3001.0,
                "low": 2999.0,
                "close": 3000.5,
            }
        ]

    monkeypatch.setattr(
        engine,
        "require_demo_account",
        fake_account,
    )

    monkeypatch.setattr(
        engine,
        "symbol_specification",
        fake_spec,
    )

    monkeypatch.setattr(
        engine,
        "candles",
        fake_candles,
    )

    proposal = SimpleNamespace(
        entry_price=3000.10,
        stop_loss=2995.0,
        take_profit=3010.0,
    )

    decision = SimpleNamespace(
        proposal=proposal,
        direction=SimpleNamespace(
            value="BUY"
        ),
    )

    pipeline_result = SimpleNamespace(
        decision=decision,
        risk_decision=SimpleNamespace(
            allowed=True,
            reason="allowed",
        ),
        position_size=0.01,
    )

    engine.pipeline = SimpleNamespace(
        evaluate_risk=lambda **kwargs: pipeline_result
    )

    signal_id = engine.build_signal_id(
        symbol="XAUUSD",
        timeframe="M15",
        direction="BUY",
        entry_price=3000.10,
        stop_loss=2995.0,
        take_profit=3010.0,
        candle_time=123456,
    )

    existing = _fake_record(
        idempotency_key=signal_id
    )

    monkeypatch.setattr(
        engine,
        "_get_execution_record",
        lambda signal_id: existing,
    )

    result = await engine.evaluate_and_execute(
        symbol="XAUUSD",
        timeframe="M15",
        candle_limit=100,
    )

    assert result.status == "duplicate_blocked"
    assert result.execution_mode == "demo"
    assert result.signal_id == signal_id
    assert result.order_ticket == 123
    assert result.verified is True


@pytest.mark.asyncio
async def test_worker_disabled_by_default(
    monkeypatch,
):
    monkeypatch.delenv(
        "RAYMOND_MT5_DEMO_WORKER_ENABLED",
        raising=False,
    )

    worker = DemoExecutionWorker()

    assert worker.enabled is False

    await worker.start()

    status = worker.status()

    assert status["running"] is False
    assert status["execution_mode"] == "demo"
    assert status["live_authorization"] is False
    assert status["live_trading_enabled"] is False
    assert status["strategy_frozen"] is True


@pytest.mark.asyncio
async def test_worker_can_be_stopped_without_start():
    worker = DemoExecutionWorker()

    await worker.stop()

    status = worker.status()

    assert status["running"] is False


@pytest.mark.asyncio
async def test_worker_run_once_fails_closed_on_execution_error(
    monkeypatch,
):
    worker = DemoExecutionWorker()

    async def fail_execution(**kwargs):
        raise RuntimeError(
            "simulated DEMO execution failure"
        )

    monkeypatch.setattr(
        "app.demo_execution_worker."
        "demo_mt5_execution_engine."
        "evaluate_and_execute",
        fail_execution,
    )

    result = await worker.run_once()

    assert result["status"] == "error"
    assert result["execution_mode"] == "demo"
    assert result["verified"] is False
    assert "simulated DEMO execution failure" in result["reason"]


@pytest.mark.asyncio
async def test_live_evaluate_never_executes_order():
    request = ExecutionRequest(
        mode=ExecutionMode.LIVE,
        symbol="XAUUSD",
        timeframe="M15",
        candle_limit=100,
    )

    result = await evaluate_execution(
        request
    )

    assert (
        result["status"]
        == "live_requires_explicit_order"
    )

    assert result["execution_mode"] == "live"
    assert result["strategy_frozen"] is True


def test_live_payload_requires_live_mode():
    payload = LiveExecutionPayload(
        mode=ExecutionMode.LIVE,
        symbol="XAUUSD",
        side="BUY",
        volume=0.01,
        stop_loss=2995.0,
        take_profit=3010.0,
    )

    assert payload.mode is ExecutionMode.LIVE
    assert payload.symbol == "XAUUSD"
    assert payload.volume == 0.01


def test_live_payload_rejects_non_positive_volume():
    with pytest.raises(Exception):
        LiveExecutionPayload(
            mode=ExecutionMode.LIVE,
            symbol="XAUUSD",
            side="BUY",
            volume=0,
            stop_loss=2995.0,
            take_profit=3010.0,
        )


def test_live_payload_rejects_non_positive_stop_loss():
    with pytest.raises(Exception):
        LiveExecutionPayload(
            mode=ExecutionMode.LIVE,
            symbol="XAUUSD",
            side="BUY",
            volume=0.01,
            stop_loss=0,
            take_profit=3010.0,
        )


def test_live_payload_rejects_non_positive_take_profit():
    with pytest.raises(Exception):
        LiveExecutionPayload(
            mode=ExecutionMode.LIVE,
            symbol="XAUUSD",
            side="BUY",
            volume=0.01,
            stop_loss=2995.0,
            take_profit=0,
        )


def test_live_payload_does_not_accept_market_price():
    with pytest.raises(Exception):
        LiveExecutionPayload(
            mode=ExecutionMode.LIVE,
            symbol="XAUUSD",
            side="BUY",
            volume=0.01,
            stop_loss=2995.0,
            take_profit=3010.0,
            price=3000.10,
        )


def test_demo_result_is_explicitly_demo():
    result = DemoExecutionResult(
        status="no_trade",
        execution_mode="demo",
        signal_id=None,
        symbol="XAUUSD",
        side=None,
        volume=None,
        requested_price=None,
        executed_price=None,
        stop_loss=None,
        take_profit=None,
        order_ticket=None,
        deal_ticket=None,
        position_ticket=None,
        broker_retcode=None,
        broker_comment=None,
        verified=False,
        reason="Raymond returned WAIT.",
        timestamp="2026-10-08T00:00:00+00:00",
    )

    assert result.execution_mode == "demo"
    assert result.verified is False
    assert result.order_ticket is None
