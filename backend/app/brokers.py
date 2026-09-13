"""
RAYMOND v2.8 - Safe Broker Adapters

Broker configuration, connection-state reporting, and execution verification
interfaces for MT5 and Exness.

IMPORTANT SAFETY CONTRACT
--------------------------
This module is NOT a live trading engine.

It deliberately does NOT:
- place broker orders
- close broker positions
- modify broker positions
- call MT5 order_send()
- call Exness order APIs
- authorize live trading
- bypass the Risk Engine
- bypass the Emergency Stop
- execute AI decisions directly

The canonical production execution path remains paper/demo only.

Real broker execution, if ever implemented in a future release, must be
introduced as a separately audited component with explicit authorization,
risk checks, acknowledgement, fill reconciliation, slippage handling,
disconnect recovery, and independent safety controls.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


# ============================================================================
# SAFETY CONSTANTS
# ============================================================================

LIVE_TRADING_ENABLED = False
EXECUTION_AUTHORIZED = False
REAL_BROKER_ORDERS_ALLOWED = False


def _utc_now() -> str:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


# ============================================================================
# ENUMS
# ============================================================================

class BrokerType(str, Enum):
    MT5 = "mt5"
    EXNESS = "exness"


class OrderStatus(str, Enum):
    PENDING = "pending"
    PLACED = "placed"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


# ============================================================================
# BASE BROKER ADAPTER
# ============================================================================

class BaseBrokerAdapter:
    """
    Safe broker adapter interface.

    Broker adapters may report configuration and connection state, but this
    implementation intentionally has no real-money execution capability.
    """

    def __init__(self, broker_type: BrokerType):
        self.broker_type = broker_type
        self.is_connected = False
        self.account_info: Dict[str, Any] = {}
        self.open_orders: Dict[str, Dict[str, Any]] = {}
        self.closed_orders: Dict[str, Dict[str, Any]] = {}
        self.execution_history: List[Dict[str, Any]] = []

        logger.info(
            "Initializing safe %s broker adapter; live execution disabled",
            broker_type.value,
        )

    async def connect(self) -> bool:
        """Establish or validate a broker connection."""
        raise NotImplementedError

    async def disconnect(self) -> bool:
        """Disconnect from the broker."""
        raise NotImplementedError

    async def place_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Reject all broker order placement requests.

        This method intentionally exists only for interface compatibility.
        """
        return self._execution_rejected("Broker order placement is disabled")

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        Reject broker order cancellation.

        Cancellation of real broker orders is deliberately not implemented in
        this safe adapter layer.
        """
        return self._execution_rejected(
            "Broker order cancellation is disabled"
        )

    async def close_position(self, position_id: str) -> Dict[str, Any]:
        """
        Reject all broker position-closing requests.
        """
        return self._execution_rejected(
            "Broker position closing is disabled"
        )

    async def get_account_info(self) -> Dict[str, Any]:
        """Return read-only account information."""
        raise NotImplementedError

    async def get_open_positions(self) -> Dict[str, Any]:
        """Return read-only position information."""
        raise NotImplementedError

    def status(self) -> Dict[str, Any]:
        """Return the adapter's safety and connection state."""
        return {
            "broker": self.broker_type.value,
            "connected": self.is_connected,
            "read_only": True,
            "paper_only": True,
            "live_trading_enabled": False,
            "execution_authorized": False,
            "real_orders_allowed": False,
            "timestamp": _utc_now(),
        }

    def _execution_rejected(self, reason: str) -> Dict[str, Any]:
        """Return a standardized fail-closed execution rejection."""
        logger.warning(
            "%s broker execution rejected: %s",
            self.broker_type.value,
            reason,
        )

        return {
            "status": OrderStatus.REJECTED.value,
            "broker": self.broker_type.value,
            "execution_allowed": False,
            "execution_authorized": False,
            "live_trading_enabled": False,
            "real_orders_allowed": False,
            "read_only": True,
            "paper_only": True,
            "reason": reason,
            "timestamp": _utc_now(),
        }


# ============================================================================
# MT5 BROKER ADAPTER
# ============================================================================

class MT5BrokerAdapter(BaseBrokerAdapter):
    """
    Safe MetaTrader 5 adapter.

    This class stores MT5 configuration and exposes read-only state only.
    It does not import or invoke the MT5 trading API.
    """

    def __init__(self):
        super().__init__(BrokerType.MT5)

        self.login = os.getenv("MT5_LOGIN", "")
        self.password_configured = bool(os.getenv("MT5_PASSWORD"))
        self.server = os.getenv("MT5_SERVER", "")
        self.account_type = os.getenv("MT5_ACCOUNT_TYPE", "demo").lower()

    async def connect(self) -> bool:
        """
        Validate safe MT5 configuration.

        This does not perform broker authentication and does not open a
        trading connection.
        """
        self.is_connected = False

        configured = bool(self.server) and bool(self.login)

        self.account_info = {
            "login_configured": bool(self.login),
            "password_configured": self.password_configured,
            "server_configured": bool(self.server),
            "account_type": self.account_type,
            "demo_account": self.account_type == "demo",
            "live_account": self.account_type == "live",
            "read_only": True,
            "live_trading_enabled": False,
            "real_orders_allowed": False,
        }

        logger.info(
            "MT5 adapter configuration checked: configured=%s account_type=%s",
            configured,
            self.account_type,
        )

        return configured

    async def disconnect(self) -> bool:
        """Clear adapter connection state."""
        self.is_connected = False
        logger.info("MT5 safe adapter disconnected")
        return True

    async def get_account_info(self) -> Dict[str, Any]:
        """Return read-only MT5 adapter information."""
        return {
            "broker": BrokerType.MT5.value,
            "account_info": dict(self.account_info),
            "connected": self.is_connected,
            "read_only": True,
            "live_trading_enabled": False,
            "real_orders_allowed": False,
            "timestamp": _utc_now(),
        }

    async def get_open_positions(self) -> Dict[str, Any]:
        """
        Return the adapter's locally known read-only state.

        This does not query or alter live broker positions.
        """
        return {
            "broker": BrokerType.MT5.value,
            "positions": [],
            "total": 0,
            "source": "safe_adapter_local_state",
            "live_broker_query": False,
            "read_only": True,
            "live_trading_enabled": False,
            "real_orders_allowed": False,
            "timestamp": _utc_now(),
        }


# ============================================================================
# EXNESS BROKER ADAPTER
# ============================================================================

class ExnessBrokerAdapter(BaseBrokerAdapter):
    """
    Safe Exness adapter.

    Configuration is retained for future integration, but no Exness trading
    API is called and no real order is permitted.
    """

    def __init__(self):
        super().__init__(BrokerType.EXNESS)

        self.api_token_configured = bool(os.getenv("EXNESS_TOKEN"))
        self.account_id = os.getenv("EXNESS_ACCOUNT_ID", "")
        self.account_type = os.getenv(
            "EXNESS_ACCOUNT_TYPE",
            "demo",
        ).lower()

        # Retained as configuration metadata only.
        self.api_base_url = "https://api.exness.com/v1"

    async def connect(self) -> bool:
        """
        Validate safe Exness configuration.

        This does not authenticate against Exness and does not establish a
        live trading session.
        """
        self.is_connected = False

        configured = bool(self.account_id)

        self.account_info = {
            "account_id_configured": bool(self.account_id),
            "api_token_configured": self.api_token_configured,
            "account_type": self.account_type,
            "demo_account": self.account_type == "demo",
            "live_account": self.account_type == "live",
            "read_only": True,
            "live_trading_enabled": False,
            "real_orders_allowed": False,
        }

        logger.info(
            "Exness adapter configuration checked: configured=%s account_type=%s",
            configured,
            self.account_type,
        )

        return configured

    async def disconnect(self) -> bool:
        """Clear adapter connection state."""
        self.is_connected = False
        logger.info("Exness safe adapter disconnected")
        return True

    async def get_account_info(self) -> Dict[str, Any]:
        """Return read-only Exness adapter information."""
        return {
            "broker": BrokerType.EXNESS.value,
            "account_info": dict(self.account_info),
            "connected": self.is_connected,
            "read_only": True,
            "live_trading_enabled": False,
            "real_orders_allowed": False,
            "timestamp": _utc_now(),
        }

    async def get_open_positions(self) -> Dict[str, Any]:
        """
        Return safe local state only.

        No Exness position query or trading operation is performed here.
        """
        return {
            "broker": BrokerType.EXNESS.value,
            "positions": [],
            "total": 0,
            "source": "safe_adapter_local_state",
            "live_broker_query": False,
            "read_only": True,
            "live_trading_enabled": False,
            "real_orders_allowed": False,
            "timestamp": _utc_now(),
        }


# ============================================================================
# BROKER FACTORY
# ============================================================================

class BrokerFactory:
    """Factory for creating safe broker adapters."""

    _adapters = {
        BrokerType.MT5: MT5BrokerAdapter,
        BrokerType.EXNESS: ExnessBrokerAdapter,
    }

    @staticmethod
    def create_adapter(broker_type: BrokerType) -> BaseBrokerAdapter:
        """Create a safe broker adapter."""
        if isinstance(broker_type, str):
            try:
                broker_type = BrokerType(broker_type.lower())
            except ValueError as exc:
                raise ValueError(
                    f"Unknown broker type: {broker_type}"
                ) from exc

        adapter_class = BrokerFactory._adapters.get(broker_type)

        if not adapter_class:
            raise ValueError(f"Unknown broker type: {broker_type}")

        return adapter_class()


# ============================================================================
# EXECUTION VERIFIER
# ============================================================================

class ExecutionVerifier:
    """
    Safe execution verifier.

    Verification only examines the supplied adapter's read-only state.
    It does not create, modify, cancel, or close orders.
    """

    def __init__(self):
        self.verification_history: List[Dict[str, Any]] = []

    async def verify_order(
        self,
        order_data: Dict[str, Any],
        broker_adapter: BaseBrokerAdapter,
    ) -> Dict[str, Any]:
        """
        Verify whether an order appears in safe local adapter state.

        Real broker execution is never assumed to have occurred.
        """
        order_id = order_data.get("order_id")

        verification: Dict[str, Any] = {
            "timestamp": _utc_now(),
            "order_id": order_id,
            "broker": broker_adapter.broker_type.value,
            "expected_status": order_data.get("status"),
            "verified": False,
            "execution_confirmed": False,
            "real_broker_execution": False,
            "live_trading_enabled": False,
            "real_orders_allowed": False,
            "discrepancies": [],
        }

        positions = await broker_adapter.get_open_positions()

        order_found = any(
            item.get("order_id") == order_id
            for item in positions.get("positions", [])
            if isinstance(item, dict)
        )

        if order_found:
            verification["discrepancies"].append(
                "Order appears in adapter state only; real broker execution "
                "is not confirmed."
            )
        else:
            verification["discrepancies"].append(
                "Order not found in safe adapter state."
            )

        self.verification_history.append(verification)

        logger.info(
            "Safe order verification: %s - broker execution confirmed=%s",
            order_id,
            verification["execution_confirmed"],
        )

        return verification

    def get_verification_report(self) -> Dict[str, Any]:
        """Return the verification history without implying live execution."""
        total = len(self.verification_history)

        verified = sum(
            1
            for item in self.verification_history
            if item.get("verified") is True
        )

        return {
            "total_verifications": total,
            "verified_count": verified,
            "failed_count": total - verified,
            "verification_rate": (
                verified / total * 100
                if total > 0
                else 0.0
            ),
            "real_broker_execution_confirmed": False,
            "live_trading_enabled": False,
            "real_orders_allowed": False,
            "recent_verifications": self.verification_history[-10:],
        }


# ============================================================================
# SAFETY STATUS
# ============================================================================

def broker_execution_safety_status() -> Dict[str, Any]:
    """
    Return the absolute execution status exposed by this module.
    """
    return {
        "live_trading_enabled": False,
        "execution_authorized": False,
        "real_broker_orders_allowed": False,
        "read_only": True,
        "paper_only": True,
        "broker_order_placement": False,
        "broker_position_closing": False,
        "broker_position_modification": False,
        "timestamp": _utc_now(),
    }



