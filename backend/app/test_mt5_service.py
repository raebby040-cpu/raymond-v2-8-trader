import os
import sys

import pytest

APP_DIR = os.path.dirname(os.path.abspath(__file__))

if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from mt5_service import (
    MT5ConnectionConfig,
    MT5Service,
    MT5ServiceError,
)


def test_default_connection_config():
    config = MT5ConnectionConfig()

    assert config.login is None
    assert config.password is None
    assert config.server is None
    assert config.terminal_path is None
    assert config.timeout_ms == 60000
    assert config.portable is False


def test_connection_config_values():
    config = MT5ConnectionConfig(
        login=123456,
        password="test-password",
        server="Test-Server",
        terminal_path="/test/terminal.exe",
        timeout_ms=30000,
        portable=True,
    )

    assert config.login == 123456
    assert config.password == "test-password"
    assert config.server == "Test-Server"
    assert config.terminal_path == "/test/terminal.exe"
    assert config.timeout_ms == 30000
    assert config.portable is True


def test_connection_config_from_env(monkeypatch):
    monkeypatch.setenv("MT5_LOGIN", "123456")
    monkeypatch.setenv("MT5_PASSWORD", "password")
    monkeypatch.setenv("MT5_SERVER", "Broker-Demo")
    monkeypatch.setenv(
        "MT5_TERMINAL_PATH",
        "/test/terminal.exe",
    )
    monkeypatch.setenv("MT5_TIMEOUT_MS", "45000")
    monkeypatch.setenv("MT5_PORTABLE", "true")

    config = MT5ConnectionConfig.from_env()

    assert config.login == 123456
    assert config.password == "password"
    assert config.server == "Broker-Demo"
    assert config.terminal_path == "/test/terminal.exe"
    assert config.timeout_ms == 45000
    assert config.portable is True


def test_connection_config_supports_mt5_account(monkeypatch):
    monkeypatch.delenv("MT5_LOGIN", raising=False)
    monkeypatch.setenv("MT5_ACCOUNT", "987654")

    config = MT5ConnectionConfig.from_env()

    assert config.login == 987654


def test_invalid_mt5_login(monkeypatch):
    monkeypatch.setenv("MT5_LOGIN", "not-a-number")

    with pytest.raises(ValueError):
        MT5ConnectionConfig.from_env()


def test_service_starts_disconnected():
    service = MT5Service()

    assert service.connected is False


@pytest.mark.asyncio
async def test_service_requires_mt5_package(monkeypatch):
    import mt5_service as service_module

    monkeypatch.setattr(
        service_module,
        "mt5",
        None,
    )

    service = MT5Service()

    with pytest.raises(MT5ServiceError):
        await service.initialize()


@pytest.mark.asyncio
async def test_shutdown_without_mt5_package(monkeypatch):
    import mt5_service as service_module

    monkeypatch.setattr(
        service_module,
        "mt5",
        None,
    )

    service = MT5Service()

    result = await service.shutdown()

    assert result is True
    assert service.connected is False


def test_to_dict_with_none():
    service = MT5Service()

    assert service._to_dict(None) == {}


def test_to_dict_with_namedtuple():
    service = MT5Service()

    from collections import namedtuple

    TestValue = namedtuple(
        "TestValue",
        ["name", "value"],
    )

    value = TestValue(
        name="test",
        value=123,
    )

    result = service._to_dict(value)

    assert result["name"] == "test"
    assert result["value"] == 123
