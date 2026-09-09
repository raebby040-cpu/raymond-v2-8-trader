import pytest

from backend.app.mt5_service import (
    MT5ConnectionConfig,
    MT5Service,
    MT5ServiceError,
)


def test_mt5_config_defaults(monkeypatch):
    """
    Test that MT5 configuration uses the correct defaults
    when no environment variables are provided.
    """

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
    """
    Test that MT5 configuration correctly reads environment variables.
    """

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

    assert config.terminal_path == (
        "C:/MT5/terminal64.exe"
    )

    assert config.timeout_ms == 30000
    assert config.portable is True


def test_mt5_config_accepts_account_alias(monkeypatch):
    """
    Test that MT5_ACCOUNT can be used instead of MT5_LOGIN.
    """

    monkeypatch.delenv("MT5_LOGIN", raising=False)
    monkeypatch.setenv("MT5_ACCOUNT", "87654321")
    monkeypatch.setenv("MT5_PASSWORD", "test-password")
    monkeypatch.setenv("MT5_SERVER", "Test-Server")

    config = MT5ConnectionConfig.from_env()

    assert config.login == 87654321
    assert config.password == "test-password"
    assert config.server == "Test-Server"


def test_invalid_mt5_login(monkeypatch):
    """
    Test that an invalid MT5 login is rejected.
    """

    monkeypatch.setenv("MT5_LOGIN", "not-a-number")

    with pytest.raises(ValueError):
        MT5ConnectionConfig.from_env()


def test_invalid_mt5_timeout(monkeypatch):
    """
    Test that an invalid timeout is rejected.
    """

    monkeypatch.setenv("MT5_TIMEOUT_MS", "not-a-number")

    with pytest.raises(ValueError):
        MT5ConnectionConfig.from_env()


@pytest.mark.asyncio
async def test_service_requires_mt5_package(monkeypatch):
    """
    Test that the service fails safely when the MetaTrader5
    Python package is unavailable.
    """

    import backend.app.mt5_service as service_module

    monkeypatch.setattr(
        service_module,
        "mt5",
        None,
    )

    service = MT5Service()

    with pytest.raises(MT5ServiceError):
        await service.initialize()
