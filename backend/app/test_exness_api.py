from __future__ import annotations

import os

import pytest

from exness_api import ExnessAPIConfig, ExnessAPIClient, ExnessAPIError


def test_exness_config_defaults_to_safe_demo_mode():
    config = ExnessAPIConfig()

    assert config.enabled is False
    assert config.demo_only is True
    assert config.account_type == "demo"


def test_exness_config_reads_environment(monkeypatch):
    monkeypatch.setenv("EXNESS_API_ENABLED", "true")
    monkeypatch.setenv("EXNESS_DEMO_ONLY", "true")
    monkeypatch.setenv("EXNESS_API_TOKEN", "test-token")
    monkeypatch.setenv("EXNESS_ACCOUNT_ID", "demo-account")
    monkeypatch.setenv("EXNESS_ACCOUNT_TYPE", "demo")
    monkeypatch.setenv("EXNESS_API_BASE_URL", "https://example.test")

    config = ExnessAPIConfig.from_env()

    assert config.enabled is True
    assert config.demo_only is True
    assert config.api_token == "test-token"
    assert config.account_id == "demo-account"
    assert config.account_type == "demo"
    assert config.base_url == "https://example.test"


@pytest.mark.asyncio
async def test_disabled_connector_refuses_requests():
    config = ExnessAPIConfig(
        enabled=False,
        demo_only=True,
    )

    client = ExnessAPIClient(config)

    with pytest.raises(ExnessAPIError, match="connector is disabled"):
        await client.health()


def test_missing_token_is_rejected():
    config = ExnessAPIConfig(
        enabled=True,
        demo_only=True,
        api_token=None,
        base_url="https://example.test",
    )

    client = ExnessAPIClient(config)

    with pytest.raises(ExnessAPIError, match="EXNESS_API_TOKEN"):
        client._ensure_enabled()


def test_missing_base_url_is_rejected():
    config = ExnessAPIConfig(
        enabled=True,
        demo_only=True,
        api_token="test-token",
        base_url="",
    )

    client = ExnessAPIClient(config)

    with pytest.raises(ExnessAPIError, match="EXNESS_API_BASE_URL"):
        client._ensure_enabled()


def test_demo_only_blocks_non_demo_account():
    config = ExnessAPIConfig(
        enabled=True,
        demo_only=True,
        api_token="test-token",
        base_url="https://example.test",
        account_type="live",
    )

    client = ExnessAPIClient(config)

    with pytest.raises(
        ExnessAPIError,
        match="account_type",
    ):
        client._ensure_trade_safety()


@pytest.mark.asyncio
async def test_order_requires_configured_endpoint():
    config = ExnessAPIConfig(
        enabled=True,
        demo_only=True,
        api_token="test-token",
        base_url="https://example.test",
        account_type="demo",
        order_path="",
    )

    client = ExnessAPIClient(config)

    with pytest.raises(
        ExnessAPIError,
        match="endpoint is not configured",
    ):
        await client.place_order(
            {
                "symbol": "XAUUSD",
                "direction": "buy",
                "quantity": 0.01,
            }
        )


def test_live_trading_remains_disabled_by_default(monkeypatch):
    monkeypatch.delenv(
        "LIVE_TRADING_ENABLED",
        raising=False,
    )

    config = ExnessAPIConfig(
        enabled=True,
        demo_only=False,
        api_token="test-token",
        base_url="https://example.test",
        account_type="live",
    )

    client = ExnessAPIClient(config)

    with pytest.raises(
        ExnessAPIError,
        match="Live trading is disabled",
    ):
        client._ensure_trade_safety()
