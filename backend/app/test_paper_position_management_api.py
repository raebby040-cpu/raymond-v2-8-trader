"""
RAYMOND v2.8 - Paper Position Management API Tests

Stage 17.2.2
Paper Position Management API Integration Tests

These tests verify that the API:

- exposes the paper-position management endpoint,
- accepts a valid paper-management request,
- passes the requested symbol and price to the manager,
- serializes management results correctly,
- exposes the safety declaration endpoint,
- remains paper-only,
- remains read-only from an execution/broker perspective,
- never enables live trading,
- never permits broker or MT5 execution,
- rejects invalid current prices,
- handles management-layer errors safely.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.paper_position_management_api import router


# ---------------------------------------------------------------------------
# Test application
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    """Provide a mocked SQLAlchemy session."""
    return Mock(name="sqlalchemy_session")


@pytest.fixture
def app(db):
    """
    Build a small isolated FastAPI application containing only the
    Stage 17.2.2 router.

    This prevents unrelated application startup behavior from affecting
    these API integration tests.
    """
    test_app = FastAPI()
    test_app.include_router(router)

    def override_get_db():
        yield db

    test_app.dependency_overrides[get_db] = override_get_db

    yield test_app

    test_app.dependency_overrides.clear()


@pytest.fixture
def client(app):
    """Return a FastAPI test client."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# Fake management result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FakeManagementResult:
    """Minimal result object returned by the mocked manager."""

    position_id: str
    trade_id: str
    symbol: str
    action: str
    profit_r: float
    current_price: float
    new_stop_loss: float | None
    partial_close_quantity: float
    persisted: bool
    reason: str
    execution_type: str = "paper"
    read_only: bool = True
    broker_order_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize the result exactly like the production result."""
        return {
            "position_id": self.position_id,
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "action": self.action,
            "profit_r": self.profit_r,
            "current_price": self.current_price,
            "new_stop_loss": self.new_stop_loss,
            "partial_close_quantity": self.partial_close_quantity,
            "persisted": self.persisted,
            "reason": self.reason,
            "execution_type": self.execution_type,
            "read_only": self.read_only,
            "broker_order_required": self.broker_order_required,
        }


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------

def test_management_status_endpoint_is_available(client):
    """Stage 17.2.2 safety/status endpoint must be available."""

    response = client.get(
        "/api/online/paper-position-management/status"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["accepted"] is True
    assert data["stage"] == "17.2"
    assert data["component"] == "paper_position_management_api"
    assert data["status"] == "available"

    safety = data["safety"]

    assert safety["paper_only"] is True
    assert safety["read_only"] is True
    assert safety["live_trading_enabled"] is False
    assert safety["execution_authorized"] is False
    assert safety["broker_orders_allowed"] is False
    assert safety["mt5_execution_allowed"] is False
    assert safety["risk_engine_bypass"] is False

    assert isinstance(data["timestamp"], str)
    assert data["timestamp"]


# ---------------------------------------------------------------------------
# Successful management request
# ---------------------------------------------------------------------------

def test_manage_paper_positions_accepts_valid_request(client):
    """
    A valid paper-position management request should reach the
    PaperPositionManager and return its results.
    """

    fake_result = FakeManagementResult(
        position_id="paper-position-1",
        trade_id="paper-trade-1",
        symbol="XAUUSD",
        action="HOLD",
        profit_r=0.75,
        current_price=4310.0,
        new_stop_loss=None,
        partial_close_quantity=0.0,
        persisted=True,
        reason="No management action required.",
    )

    fake_manager = Mock()
    fake_manager.evaluate_symbol.return_value = [
        fake_result
    ]

    with patch(
        "app.paper_position_management_api.PaperPositionManager",
        return_value=fake_manager,
    ) as manager_class:

        response = client.post(
            "/api/online/manage-paper-positions"
            "?symbol=XAUUSD&current_price=4310.0"
        )

    assert response.status_code == 200

    manager_class.assert_called_once()

    fake_manager.evaluate_symbol.assert_called_once_with(
        "XAUUSD",
        4310.0,
    )

    data = response.json()

    assert data["accepted"] is True
    assert data["symbol"] == "XAUUSD"
    assert data["current_price"] == 4310.0
    assert data["count"] == 1

    assert len(data["results"]) == 1

    result = data["results"][0]

    assert result["position_id"] == "paper-position-1"
    assert result["trade_id"] == "paper-trade-1"
    assert result["symbol"] == "XAUUSD"
    assert result["action"] == "HOLD"
    assert result["profit_r"] == 0.75
    assert result["current_price"] == 4310.0
    assert result["persisted"] is True
    assert result["execution_type"] == "paper"
    assert result["read_only"] is True
    assert result["broker_order_required"] is False

    safety = data["safety"]

    assert safety["paper_only"] is True
    assert safety["read_only"] is True
    assert safety["live_trading_enabled"] is False
    assert safety["execution_authorized"] is False
    assert safety["broker_orders_allowed"] is False
    assert safety["mt5_execution_allowed"] is False
    assert safety["risk_engine_bypass"] is False


def test_manage_paper_positions_normalizes_symbol(client):
    """Symbol input should be stripped and normalized to uppercase."""

    fake_manager = Mock()
    fake_manager.evaluate_symbol.return_value = []

    with patch(
        "app.paper_position_management_api.PaperPositionManager",
        return_value=fake_manager,
    ):

        response = client.post(
            "/api/online/manage-paper-positions"
            "?symbol=%20xauusd%20&current_price=4310.5"
        )

    assert response.status_code == 200

    data = response.json()

    assert data["symbol"] == "XAUUSD"
    assert data["current_price"] == 4310.5
    assert data["count"] == 0

    fake_manager.evaluate_symbol.assert_called_once_with(
        "XAUUSD",
        4310.5,
    )


def test_manage_paper_positions_supports_empty_result(client):
    """A symbol with no open paper positions should still return success."""

    fake_manager = Mock()
    fake_manager.evaluate_symbol.return_value = []

    with patch(
        "app.paper_position_management_api.PaperPositionManager",
        return_value=fake_manager,
    ):

        response = client.post(
            "/api/online/manage-paper-positions"
            "?symbol=XAUUSD&current_price=4310"
        )

    assert response.status_code == 200

    data = response.json()

    assert data["accepted"] is True
    assert data["count"] == 0
    assert data["results"] == []


# ---------------------------------------------------------------------------
# Management action serialization
# ---------------------------------------------------------------------------

def test_manage_paper_positions_serializes_break_even_result(client):
    """Break-even management results must be returned correctly."""

    fake_result = FakeManagementResult(
        position_id="paper-position-1",
        trade_id="paper-trade-1",
        symbol="XAUUSD",
        action="MOVE_TO_BREAK_EVEN",
        profit_r=1.0,
        current_price=4310.0,
        new_stop_loss=4300.0,
        partial_close_quantity=0.0,
        persisted=True,
        reason="Break-even threshold reached.",
    )

    fake_manager = Mock()
    fake_manager.evaluate_symbol.return_value = [
        fake_result
    ]

    with patch(
        "app.paper_position_management_api.PaperPositionManager",
        return_value=fake_manager,
    ):

        response = client.post(
            "/api/online/manage-paper-positions"
            "?symbol=XAUUSD&current_price=4310"
        )

    assert response.status_code == 200

    result = response.json()["results"][0]

    assert result["action"] == "MOVE_TO_BREAK_EVEN"
    assert result["new_stop_loss"] == 4300.0
    assert result["partial_close_quantity"] == 0.0
    assert result["persisted"] is True


def test_manage_paper_positions_serializes_trailing_result(client):
    """Trailing-stop management results must be returned correctly."""

    fake_result = FakeManagementResult(
        position_id="paper-position-1",
        trade_id="paper-trade-1",
        symbol="XAUUSD",
        action="TRAIL_STOP",
        profit_r=1.5,
        current_price=4315.0,
        new_stop_loss=4308.0,
        partial_close_quantity=0.0,
        persisted=True,
        reason="Trailing stop improves protection.",
    )

    fake_manager = Mock()
    fake_manager.evaluate_symbol.return_value = [
        fake_result
    ]

    with patch(
        "app.paper_position_management_api.PaperPositionManager",
        return_value=fake_manager,
    ):

        response = client.post(
            "/api/online/manage-paper-positions"
            "?symbol=XAUUSD&current_price=4315"
        )

    assert response.status_code == 200

    result = response.json()["results"][0]

    assert result["action"] == "TRAIL_STOP"
    assert result["new_stop_loss"] == 4308.0
    assert result["persisted"] is True


def test_manage_paper_positions_serializes_partial_close_result(client):
    """Partial-close management results must be returned correctly."""

    fake_result = FakeManagementResult(
        position_id="paper-position-1",
        trade_id="paper-trade-1",
        symbol="XAUUSD",
        action="PARTIAL_CLOSE",
        profit_r=2.0,
        current_price=4320.0,
        new_stop_loss=None,
        partial_close_quantity=0.5,
        persisted=True,
        reason="Partial close threshold reached.",
    )

    fake_manager = Mock()
    fake_manager.evaluate_symbol.return_value = [
        fake_result
    ]

    with patch(
        "app.paper_position_management_api.PaperPositionManager",
        return_value=fake_manager,
    ):

        response = client.post(
            "/api/online/manage-paper-positions"
            "?symbol=XAUUSD&current_price=4320"
        )

    assert response.status_code == 200

    result = response.json()["results"][0]

    assert result["action"] == "PARTIAL_CLOSE"
    assert result["partial_close_quantity"] == 0.5
    assert result["persisted"] is True


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_manage_paper_positions_rejects_missing_current_price(client):
    """Current market price is required."""

    response = client.post(
        "/api/online/manage-paper-positions"
        "?symbol=XAUUSD"
    )

    assert response.status_code == 422


def test_manage_paper_positions_rejects_zero_price(client):
    """A zero price must be rejected."""

    response = client.post(
        "/api/online/manage-paper-positions"
        "?symbol=XAUUSD&current_price=0"
    )

    assert response.status_code == 422


def test_manage_paper_positions_rejects_negative_price(client):
    """A negative price must be rejected."""

    response = client.post(
        "/api/online/manage-paper-positions"
        "?symbol=XAUUSD&current_price=-1"
    )

    assert response.status_code == 422


def test_manage_paper_positions_rejects_non_numeric_price(client):
    """A non-numeric market price must be rejected."""

    response = client.post(
        "/api/online/manage-paper-positions"
        "?symbol=XAUUSD&current_price=invalid"
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_manage_paper_positions_handles_management_error(client):
    """Management-layer validation errors should become HTTP 422."""

    from app.paper_position_manager import (
        PaperPositionManagementError,
    )

    fake_manager = Mock()
    fake_manager.evaluate_symbol.side_effect = (
        PaperPositionManagementError(
            "Unsafe management decision."
        )
    )

    with patch(
        "app.paper_position_management_api.PaperPositionManager",
        return_value=fake_manager,
    ):

        response = client.post(
            "/api/online/manage-paper-positions"
            "?symbol=XAUUSD&current_price=4310"
        )

    assert response.status_code == 422

    detail = response.json()["detail"]

    assert detail["error"] == "Unsafe management decision."
    assert isinstance(detail["timestamp"], str)


def test_manage_paper_positions_handles_unexpected_error(client):
    """Unexpected manager errors should become HTTP 500."""

    fake_manager = Mock()
    fake_manager.evaluate_symbol.side_effect = RuntimeError(
        "unexpected test failure"
    )

    with patch(
        "app.paper_position_management_api.PaperPositionManager",
        return_value=fake_manager,
    ):

        response = client.post(
            "/api/online/manage-paper-positions"
            "?symbol=XAUUSD&current_price=4310"
        )

    assert response.status_code == 500

    detail = response.json()["detail"]

    assert detail["error"] == "Paper position management failed"
    assert detail["message"] == "unexpected test failure"
    assert isinstance(detail["timestamp"], str)


# ---------------------------------------------------------------------------
# Hard safety tests
# ---------------------------------------------------------------------------

def test_management_endpoint_never_enables_live_trading(client):
    """
    The API response must explicitly prove live trading remains disabled.
    """

    fake_manager = Mock()
    fake_manager.evaluate_symbol.return_value = []

    with patch(
        "app.paper_position_management_api.PaperPositionManager",
        return_value=fake_manager,
    ):

        response = client.post(
            "/api/online/manage-paper-positions"
            "?symbol=XAUUSD&current_price=4310"
        )

    assert response.status_code == 200

    safety = response.json()["safety"]

    assert safety["live_trading_enabled"] is False
    assert safety["execution_authorized"] is False
    assert safety["broker_orders_allowed"] is False
    assert safety["mt5_execution_allowed"] is False


def test_management_endpoint_has_no_risk_engine_bypass(client):
    """The management API must never bypass the Risk Engine."""

    fake_manager = Mock()
    fake_manager.evaluate_symbol.return_value = []

    with patch(
        "app.paper_position_management_api.PaperPositionManager",
        return_value=fake_manager,
    ):

        response = client.post(
            "/api/online/manage-paper-positions"
            "?symbol=XAUUSD&current_price=4310"
        )

    assert response.status_code == 200

    safety = response.json()["safety"]

    assert safety["risk_engine_bypass"] is False


def test_management_endpoint_does_not_call_broker_or_mt5(client):
    """
    The endpoint itself must not have a broker or MT5 execution path.
    """

    fake_manager = Mock()
    fake_manager.evaluate_symbol.return_value = []

    fake_broker = Mock()
    fake_mt5 = Mock()

    with patch(
        "app.paper_position_management_api.PaperPositionManager",
        return_value=fake_manager,
    ), patch(
        "app.paper_position_management_api.mt5",
        fake_mt5,
        create=True,
    ), patch(
        "app.paper_position_management_api.broker",
        fake_broker,
        create=True,
    ):

        response = client.post(
            "/api/online/manage-paper-positions"
            "?symbol=XAUUSD&current_price=4310"
        )

    assert response.status_code == 200

    fake_broker.assert_not_called()
    fake_mt5.assert_not_called()

    safety = response.json()["safety"]

    assert safety["paper_only"] is True
    assert safety["broker_orders_allowed"] is False
    assert safety["mt5_execution_allowed"] is False


def test_status_endpoint_performs_no_management_action(client):
    """
    The status endpoint must be read-only and must not instantiate or
    evaluate PaperPositionManager.
    """

    with patch(
        "app.paper_position_management_api.PaperPositionManager"
    ) as manager_class:

        response = client.get(
            "/api/online/paper-position-management/status"
        )

    assert response.status_code == 200

    manager_class.assert_not_called()

    data = response.json()

    assert data["accepted"] is True
    assert data["status"] == "available"


# ---------------------------------------------------------------------------
# Method safety
# ---------------------------------------------------------------------------

def test_management_endpoint_requires_post(client):
    """
    Management is an explicit state-changing paper operation.
    GET must not be accepted as the management method.
    """

    response = client.get(
        "/api/online/manage-paper-positions"
        "?symbol=XAUUSD&current_price=4310"
    )

    assert response.status_code == 405


def test_status_endpoint_rejects_post(client):
    """The status endpoint is GET-only."""

    response = client.post(
        "/api/online/paper-position-management/status"
    )

    assert response.status_code == 405


# ---------------------------------------------------------------------------
# Result safety
# ---------------------------------------------------------------------------

def test_management_result_cannot_request_broker_execution(client):
    """
    A production manager result should be paper/read-only.

    This test confirms the API preserves those safety declarations in
    its serialized result.
    """

    fake_result = FakeManagementResult(
        position_id="paper-position-1",
        trade_id="paper-trade-1",
        symbol="XAUUSD",
        action="HOLD",
        profit_r=0.0,
        current_price=4310.0,
        new_stop_loss=None,
        partial_close_quantity=0.0,
        persisted=True,
        reason="Paper management only.",
        execution_type="paper",
        read_only=True,
        broker_order_required=False,
    )

    fake_manager = Mock()
    fake_manager.evaluate_symbol.return_value = [
        fake_result
    ]

    with patch(
        "app.paper_position_management_api.PaperPositionManager",
        return_value=fake_manager,
    ):

        response = client.post(
            "/api/online/manage-paper-positions"
            "?symbol=XAUUSD&current_price=4310"
        )

    assert response.status_code == 200

    result = response.json()["results"][0]

    assert result["execution_type"] == "paper"
    assert result["read_only"] is True
    assert result["broker_order_required"] is False


def test_management_endpoint_returns_timestamp(client):
    """Successful management responses must contain a timestamp."""

    fake_manager = Mock()
    fake_manager.evaluate_symbol.return_value = []

    with patch(
        "app.paper_position_management_api.PaperPositionManager",
        return_value=fake_manager,
    ):

        response = client.post(
            "/api/online/manage-paper-positions"
            "?symbol=XAUUSD&current_price=4310"
        )

    assert response.status_code == 200

    data = response.json()

    assert isinstance(data["timestamp"], str)
    assert data["timestamp"]


