"""
RAYMOND v2.8 - DEMO account safety tests.

These tests verify that the DEMO execution boundary:
- accepts DEMO accounts only
- rejects REAL accounts
- requires account trading permission
- requires expert/API trading permission
- requires MT5 terminal trading permission
- rejects disabled external trading API access

No real broker connection is used.
"""

from __future__ import annotations

from app.demo_mt5_execution import (
    DemoExecutionError,
    DemoMT5ExecutionEngine,
)


def _engine(monkeypatch, account, terminal):
    engine = DemoMT5ExecutionEngine()

    async def fake_account_info():
        return account

    async def fake_terminal_info():
        return terminal

    monkeypatch.setattr(
        engine,
        "account_info",
        fake_account_info,
    )

    monkeypatch.setattr(
        engine,
        "terminal_info",
        fake_terminal_info,
    )

    return engine


def test_demo_account_is_accepted(monkeypatch):
    import app.demo_mt5_execution as module

    demo_mode = getattr(
        module.mt5,
        "ACCOUNT_TRADE_MODE_DEMO",
        0,
    )

    engine = _engine(
        monkeypatch,
        {
            "trade_mode": demo_mode,
            "trade_allowed": True,
            "trade_expert": True,
            "login": 123456,
            "balance": 1000.0,
            "equity": 1000.0,
        },
        {
            "trade_allowed": True,
            "tradeapi_disabled": False,
        },
    )

    result = __import__("asyncio").run(
        engine.require_demo_account()
    )

    assert result["demo"] is True
    assert result["account"]["trade_mode"] == demo_mode
    assert result["account"]["trade_allowed"] is True
    assert result["account"]["trade_expert"] is True
    assert result["terminal"]["trade_allowed"] is True
    assert result["terminal"]["tradeapi_disabled"] is False


def test_real_account_is_rejected(monkeypatch):
    import app.demo_mt5_execution as module

    demo_mode = getattr(
        module.mt5,
        "ACCOUNT_TRADE_MODE_DEMO",
        0,
    )

    real_mode = (
        2
        if demo_mode != 2
        else 1
    )

    engine = _engine(
        monkeypatch,
        {
            "trade_mode": real_mode,
            "trade_allowed": True,
            "trade_expert": True,
            "login": 999999,
            "balance": 1000.0,
            "equity": 1000.0,
        },
        {
            "trade_allowed": True,
            "tradeapi_disabled": False,
        },
    )

    import asyncio

    try:
        asyncio.run(
            engine.require_demo_account()
        )
        assert False, (
            "REAL accounts must never pass the DEMO gate."
        )
    except DemoExecutionError as exc:
        assert "not an mt5 demo account" in str(
            exc
        ).lower()


def test_demo_account_with_trading_disabled_is_rejected(
    monkeypatch,
):
    import asyncio
    import app.demo_mt5_execution as module

    demo_mode = getattr(
        module.mt5,
        "ACCOUNT_TRADE_MODE_DEMO",
        0,
    )

    engine = _engine(
        monkeypatch,
        {
            "trade_mode": demo_mode,
            "trade_allowed": False,
            "trade_expert": True,
        },
        {
            "trade_allowed": True,
            "tradeapi_disabled": False,
        },
    )

    try:
        asyncio.run(
            engine.require_demo_account()
        )
        assert False
    except DemoExecutionError as exc:
        assert "account trading is disabled" in str(
            exc
        ).lower()


def test_demo_account_without_expert_trading_is_rejected(
    monkeypatch,
):
    import asyncio
    import app.demo_mt5_execution as module

    demo_mode = getattr(
        module.mt5,
        "ACCOUNT_TRADE_MODE_DEMO",
        0,
    )

    engine = _engine(
        monkeypatch,
        {
            "trade_mode": demo_mode,
            "trade_allowed": True,
            "trade_expert": False,
        },
        {
            "trade_allowed": True,
            "tradeapi_disabled": False,
        },
    )

    try:
        asyncio.run(
            engine.require_demo_account()
        )
        assert False
    except DemoExecutionError as exc:
        assert "expert/api trading is disabled" in str(
            exc
        ).lower()


def test_mt5_external_api_disabled_is_rejected(
    monkeypatch,
):
    import asyncio
    import app.demo_mt5_execution as module

    demo_mode = getattr(
        module.mt5,
        "ACCOUNT_TRADE_MODE_DEMO",
        0,
    )

    engine = _engine(
        monkeypatch,
        {
            "trade_mode": demo_mode,
            "trade_allowed": True,
            "trade_expert": True,
        },
        {
            "trade_allowed": True,
            "tradeapi_disabled": True,
        },
    )

    try:
        asyncio.run(
            engine.require_demo_account()
        )
        assert False
    except DemoExecutionError as exc:
        assert "external python api" in str(
            exc
        ).lower()


def test_mt5_terminal_trading_disabled_is_rejected(
    monkeypatch,
):
    import asyncio
    import app.demo_mt5_execution as module

    demo_mode = getattr(
        module.mt5,
        "ACCOUNT_TRADE_MODE_DEMO",
        0,
    )

    engine = _engine(
        monkeypatch,
        {
            "trade_mode": demo_mode,
            "trade_allowed": True,
            "trade_expert": True,
        },
        {
            "trade_allowed": False,
            "tradeapi_disabled": False,
        },
    )

    try:
        asyncio.run(
            engine.require_demo_account()
        )
        assert False
    except DemoExecutionError as exc:
        assert "terminal trading is disabled" in str(
            exc
        ).lower()
