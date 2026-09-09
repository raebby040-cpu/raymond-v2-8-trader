import os
import sys

import pytest


# Make backend/app importable when pytest runs from the repository root.
APP_DIR = os.path.dirname(os.path.abspath(__file__))

if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


from mt5_service import (  # noqa: E402
    MT5ConnectionConfig,
    MT5Service,
    MT5ServiceError,
)


def test_mt5_config_defaults(monkeypatch):
    monkeypatch.delenv("MT5_LOGIN", raising=False)
    monkeypatch.delenv("MT5_ACCOUNT", raising=False)
    monkeypatch.delenv("MT5_PASSWORD", raising=False)
    monkeypatch.delenv("MT5_SERVER", raising=False)
    monkeypatch.delenv("MT5_TERMINAL_PATH", raising=False)
    monkeypatch.delenv("MT5_TIMEOUT_MS", raising=False)
    monkeypatch.delenv("MT5_PORTABLE", raising=False)

    config = MT5ConnectionConfig.from_env()

    assert config.login is None
    assert config.password is None
    assert config.server is None
    assert config.terminal_path is None
    assert config.timeout_ms == 60000
    assert config.portable is False


def test_mt5_config_reads_environment(monkeypatch):
    monkeypatch.setenv("MT5_LOGIN", "12345678")
    monkeypatch.setenv("MT5_PASSWORD", "test-password")
    monkeypatch.setenv("MT5_SERVER", "Test-Server")
    monkeypatch.setenv(
        "MT5_TERMINAL_PATH",
        "C:/MT5/terminal64.exe",
    )
    monkeypatch.setenv("MT5_TIMEOUT_MS", "30000")
    monkeypatch.setenv("MT5_PORTABLE", "true")

    config = MT5ConnectionConfig.from_env()

    assert config.login == 12345678
    assert config.password == "test-password"
    assert config.server == "Test-Server"
    assert config.terminal_path == "C:/MT5/terminal64.exe"
    assert config.timeout_ms == 30000
    assert config.portable is True


def test_mt5_config_accepts_account_alias(monkeypatch):
    monkeypatch.delenv("MT5_LOGIN", raising=False)
    monkeypatch.setenv("MT5_ACCOUNT", "87654321")
    monkeypatch.setenv("MT5_PASSWORD", "test-password")
    monkeypatch.setenv("MT5_SERVER", "Test-Server")

    config = MT5ConnectionConfig.from_env()

    assert config.login == 87654321
    assert config.password == "test-password"
    assert config.server == "Test-Server"


def test_invalid_mt5_login(monkeypatch):
    monkeypatch.setenv("MT5_LOGIN", "not-a-number")

    with pytest.raises(ValueError):
        MT5ConnectionConfig.from_env()


def test_invalid_mt5_timeout(monkeypatch):
    monkeypatch.setenv("MT5_TIMEOUT_MS", "not-a-number")

    with pytest.raises(ValueError):
        MT5ConnectionConfig.from_env()


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
