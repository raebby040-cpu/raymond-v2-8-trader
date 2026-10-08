"""
RAYMOND v2.8 - Broker Account Management

STEP 17.8A

Provides:
- Multiple broker-account records
- MT5 account configuration
- Masked account numbers
- Selected/active account
- Connection status
- MT5 account verification
- Trading permission state
- Explicit live-trading authorization state
- MT5 connect/disconnect
- Demo/live-capable account connection architecture

SECURITY:
- Raw broker passwords are NEVER stored in BrokerAccount.
- Raw broker passwords are NEVER returned by API responses.
- The password supplied to the connect endpoint is request-scoped.
- credential_ref is only an opaque reference to a secure credential
  record/secret store.
- Connecting/verifying an account NEVER authorizes live trading.
- Connecting/verifying an account NEVER creates an order.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
import secrets

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Float, Integer, String

try:
    from .database import Base, SessionLocal
except ImportError:
    from database import Base, SessionLocal


# ============================================================
# DATABASE MODEL
# ============================================================

class BrokerAccount(Base):
    """
    Persistent broker-account metadata.

    IMPORTANT:
    credential_ref is NOT the broker password.

    It is an opaque reference to credentials stored separately.
    """

    __tablename__ = "broker_accounts"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    account_id = Column(
        String,
        unique=True,
        index=True,
        nullable=False,
    )

    broker = Column(
        String,
        nullable=False,
    )

    platform = Column(
        String,
        nullable=False,
        default="MT5",
    )

    server = Column(
        String,
        nullable=False,
    )

    account_number = Column(
        String,
        nullable=False,
    )

    credential_ref = Column(
        String,
        nullable=False,
    )

    connection_status = Column(
        String,
        nullable=False,
        default="disconnected",
    )

    account_verified = Column(
        Integer,
        nullable=False,
        default=0,
    )

    trading_allowed = Column(
        Integer,
        nullable=False,
        default=0,
    )

    selected = Column(
        Integer,
        nullable=False,
        default=0,
    )

    live_trading_authorized = Column(
        Integer,
        nullable=False,
        default=0,
    )

    last_balance = Column(
        Float,
        nullable=True,
    )

    last_equity = Column(
        Float,
        nullable=True,
    )

    last_free_margin = Column(
        Float,
        nullable=True,
    )

    last_error = Column(
        String,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


# ============================================================
# API MODELS
# ============================================================

class BrokerAccountCreate(BaseModel):
    broker: str = Field(
        min_length=1,
        max_length=100,
    )

    platform: str = Field(
        default="MT5",
        min_length=1,
        max_length=50,
    )

    server: str = Field(
        min_length=1,
        max_length=200,
    )

    account_number: str = Field(
        min_length=1,
        max_length=100,
    )

    credential_ref: str = Field(
        min_length=1,
        max_length=500,
    )


class BrokerAccountUpdate(BaseModel):
    broker: Optional[str] = Field(
        default=None,
        max_length=100,
    )

    server: Optional[str] = Field(
        default=None,
        max_length=200,
    )

    credential_ref: Optional[str] = Field(
        default=None,
        max_length=500,
    )


class BrokerAccountConnect(BaseModel):
    """
    Request-scoped MT5 connection credentials.

    SECURITY:
    - password is accepted only for this connection request
    - password is never persisted
    - password is never returned
    """

    password: str = Field(
        min_length=1,
        max_length=500,
    )

    terminal_path: Optional[str] = Field(
        default=None,
        max_length=500,
    )


# ============================================================
# HELPERS
# ============================================================

def _mask_account_number(
    account_number: str,
) -> str:
    value = str(account_number)

    if len(value) <= 4:
        return "*" * len(value)

    return "*" * (len(value) - 4) + value[-4:]


def _serialize(
    account: BrokerAccount,
) -> dict:
    """
    Convert a BrokerAccount into a safe API representation.

    Never expose:
    - password
    - raw credentials
    """

    return {
        "account_id": account.account_id,
        "broker": account.broker,
        "platform": account.platform,
        "server": account.server,
        "account_number": _mask_account_number(
            account.account_number
        ),
        "connection_status": account.connection_status,
        "account_verified": bool(
            account.account_verified
        ),
        "trading_allowed": bool(
            account.trading_allowed
        ),
        "selected": bool(
            account.selected
        ),
        "live_trading_authorized": bool(
            account.live_trading_authorized
        ),
        "balance": account.last_balance,
        "equity": account.last_equity,
        "free_margin": account.last_free_margin,
        "last_error": account.last_error,
        "created_at": (
            account.created_at.isoformat()
            if account.created_at
            else None
        ),
        "updated_at": (
            account.updated_at.isoformat()
            if account.updated_at
            else None
        ),
    }


def _get_account(
    db,
    account_id: str,
) -> BrokerAccount:
    account = (
        db.query(BrokerAccount)
        .filter(
            BrokerAccount.account_id == account_id
        )
        .first()
    )

    if account is None:
        raise HTTPException(
            status_code=404,
            detail="Broker account not found.",
        )

    return account


# ============================================================
# ROUTER
# ============================================================

router = APIRouter(
    prefix="/api/broker-accounts",
    tags=["Broker Accounts"],
)


# ============================================================
# LIST ACCOUNTS
# ============================================================

@router.get("")
def list_broker_accounts():
    db = SessionLocal()

    try:
        accounts = (
            db.query(BrokerAccount)
            .order_by(
                BrokerAccount.created_at.asc()
            )
            .all()
        )

        return {
            "status": "ok",
            "accounts": [
                _serialize(account)
                for account in accounts
            ],
        }

    finally:
        db.close()


# ============================================================
# GET ACCOUNT
# ============================================================

@router.get("/{account_id}")
def get_broker_account(
    account_id: str,
):
    db = SessionLocal()

    try:
        account = _get_account(
            db,
            account_id,
        )

        return {
            "status": "ok",
            "account": _serialize(account),
        }

    finally:
        db.close()


# ============================================================
# CREATE ACCOUNT
# ============================================================

@router.post("")
def create_broker_account(
    payload: BrokerAccountCreate,
):
    db = SessionLocal()

    try:
        existing = (
            db.query(BrokerAccount)
            .filter(
                BrokerAccount.account_number
                == payload.account_number.strip()
            )
            .first()
        )

        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "A broker account with this "
                    "account number already exists."
                ),
            )

        account_id = (
            "BROKER-"
            + secrets.token_hex(10).upper()
        )

        account = BrokerAccount(
            account_id=account_id,
            broker=payload.broker.strip(),
            platform=payload.platform.strip().upper(),
            server=payload.server.strip(),
            account_number=(
                payload.account_number.strip()
            ),
            credential_ref=(
                payload.credential_ref.strip()
            ),
            connection_status="disconnected",
            account_verified=0,
            trading_allowed=0,
            selected=0,
            live_trading_authorized=0,
        )

        db.add(account)
        db.commit()
        db.refresh(account)

        return {
            "status": "created",
            "account": _serialize(account),
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# ============================================================
# UPDATE ACCOUNT
# ============================================================

@router.patch("/{account_id}")
def update_broker_account(
    account_id: str,
    payload: BrokerAccountUpdate,
):
    db = SessionLocal()

    try:
        account = _get_account(
            db,
            account_id,
        )

        if payload.broker is not None:
            account.broker = payload.broker.strip()

        if payload.server is not None:
            account.server = payload.server.strip()

            # Changing the server invalidates the previous
            # verification state.
            account.connection_status = "disconnected"
            account.account_verified = 0
            account.trading_allowed = 0
            account.live_trading_authorized = 0

        if payload.credential_ref is not None:
            account.credential_ref = (
                payload.credential_ref.strip()
            )

            # Credential changes require reconnect/
            # re-verification.
            account.connection_status = "disconnected"
            account.account_verified = 0
            account.trading_allowed = 0
            account.live_trading_authorized = 0

        account.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(account)

        return {
            "status": "updated",
            "account": _serialize(account),
        }

    finally:
        db.close()


# ============================================================
# SELECT ACCOUNT
# ============================================================

@router.post("/{account_id}/select")
def select_broker_account(
    account_id: str,
):
    db = SessionLocal()

    try:
        account = _get_account(
            db,
            account_id,
        )

        (
            db.query(BrokerAccount)
            .update(
                {
                    BrokerAccount.selected: 0,
                    BrokerAccount.live_trading_authorized: 0,
                },
                synchronize_session=False,
            )
        )

        account.selected = 1

        # Selecting an account never arms live trading.
        account.live_trading_authorized = 0

        account.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(account)

        return {
            "status": "selected",
            "account": _serialize(account),
        }

    finally:
        db.close()


# ============================================================
# CONNECT + VERIFY MT5 ACCOUNT
# ============================================================

@router.post("/{account_id}/connect")
async def connect_broker_account(
    account_id: str,
    payload: BrokerAccountConnect,
):
    """
    Connect one broker account to MT5 and verify it.

    Verification checks:

    1. MT5 terminal is connected.
    2. MT5 account number matches the configured account.
    3. MT5 server matches the configured server.
    4. MT5 account/terminal trading permissions are read.

    IMPORTANT:
    - No order is created here.
    - No position is modified here.
    - Live authorization remains disabled.
    - Password is never stored in BrokerAccount.
    """

    db = SessionLocal()

    try:
        account = _get_account(
            db,
            account_id,
        )

        if account.platform.upper() != "MT5":
            raise HTTPException(
                status_code=400,
                detail=(
                    "Only MT5 accounts are supported "
                    "by the MT5 connection flow."
                ),
            )

        try:
            login = int(
                account.account_number.strip()
            )
        except ValueError as exc:
            account.connection_status = "error"
            account.account_verified = 0
            account.trading_allowed = 0
            account.live_trading_authorized = 0
            account.last_error = (
                "MT5 account number must be numeric."
            )
            account.updated_at = datetime.utcnow()

            db.commit()

            raise HTTPException(
                status_code=400,
                detail=account.last_error,
            ) from exc

        # Import lazily so the broker-account module itself
        # remains importable when MT5 is unavailable.
        try:
            from .mt5_service import (
                MT5ConnectionConfig,
                MT5Service,
            )
            from .mt5_broker_adapter import (
                BrokerAdapterError,
                mt5_broker_adapter,
            )
        except ImportError:
            from mt5_service import (
                MT5ConnectionConfig,
                MT5Service,
            )
            from mt5_broker_adapter import (
                BrokerAdapterError,
                mt5_broker_adapter,
            )

        # Clear stale verification state before connecting.
        account.connection_status = "connecting"
        account.account_verified = 0
        account.trading_allowed = 0

        # Explicitly prevent a connection from authorizing live.
        account.live_trading_authorized = 0

        account.last_error = None
        account.updated_at = datetime.utcnow()

        db.commit()

        # The adapter currently represents one active MT5 terminal
        # connection. Disconnect any previous session before switching.
        try:
            await mt5_broker_adapter.disconnect()
        except Exception:
            pass

        config = MT5ConnectionConfig(
            login=login,
            password=payload.password,
            server=account.server.strip(),
            terminal_path=(
                payload.terminal_path.strip()
                if payload.terminal_path
                else None
            ),
        )

        # The password exists only inside this request-scoped
        # MT5Service configuration. It is never written to DB.
        mt5_broker_adapter.service = MT5Service(
            config
        )

        try:
            await mt5_broker_adapter.connect()

            broker_info = (
                await mt5_broker_adapter.account_info()
            )

            terminal_info = (
                await mt5_broker_adapter.terminal_info()
            )

        except BrokerAdapterError as exc:
            account.connection_status = "error"
            account.account_verified = 0
            account.trading_allowed = 0
            account.live_trading_authorized = 0
            account.last_error = str(exc)
            account.updated_at = datetime.utcnow()

            db.commit()

            raise HTTPException(
                status_code=503,
                detail={
                    "error": "MT5_CONNECTION_FAILED",
                    "message": str(exc),
                    "live_authorization": False,
                    "order_created": False,
                },
            ) from exc

        except Exception as exc:
            account.connection_status = "error"
            account.account_verified = 0
            account.trading_allowed = 0
            account.live_trading_authorized = 0
            account.last_error = str(exc)
            account.updated_at = datetime.utcnow()

            db.commit()

            raise HTTPException(
                status_code=503,
                detail={
                    "error": "MT5_CONNECTION_FAILED",
                    "message": str(exc),
                    "live_authorization": False,
                    "order_created": False,
                },
            ) from exc

        # ========================================================
        # VERIFY TERMINAL
        # ========================================================

        terminal_connected = bool(
            terminal_info.get(
                "connected",
                False,
            )
        )

        # ========================================================
        # VERIFY ACCOUNT NUMBER
        # ========================================================

        broker_login = broker_info.get(
            "login"
        )

        login_matches = (
            str(broker_login)
            == str(login)
        )

        # ========================================================
        # VERIFY SERVER
        # ========================================================

        broker_server = str(
            broker_info.get("server")
            or ""
        ).strip()

        expected_server = (
            account.server.strip()
        )

        server_matches = (
            broker_server.lower()
            == expected_server.lower()
        )

        # ========================================================
        # ACCOUNT VERIFICATION
        # ========================================================

        verified = (
            terminal_connected
            and login_matches
            and server_matches
        )

        # ========================================================
        # TRADING PERMISSION
        # ========================================================

        account_trade_allowed = bool(
            broker_info.get(
                "trade_allowed",
                False,
            )
        )

        account_trade_expert = bool(
            broker_info.get(
                "trade_expert",
                False,
            )
        )

        terminal_trade_allowed = bool(
            terminal_info.get(
                "trade_allowed",
                False,
            )
        )

        terminal_trade_api_disabled = bool(
            terminal_info.get(
                "tradeapi_disabled",
                False,
            )
        )

        trading_allowed = (
            verified
            and account_trade_allowed
            and account_trade_expert
            and terminal_trade_allowed
            and not terminal_trade_api_disabled
        )

        # ========================================================
        # SAVE CONNECTION STATE
        # ========================================================

        account.connection_status = (
            "connected"
            if verified
            else "verification_failed"
        )

        account.account_verified = int(
            verified
        )

        account.trading_allowed = int(
            trading_allowed
        )

        # CRITICAL:
        # Connection and verification do NOT authorize live trading.
        account.live_trading_authorized = 0

        # ========================================================
        # SAVE ACCOUNT FINANCIAL STATE
        # ========================================================

        balance = broker_info.get(
            "balance"
        )

        equity = broker_info.get(
            "equity"
        )

        free_margin = broker_info.get(
            "margin_free"
        )

        account.last_balance = (
            float(balance)
            if balance is not None
            else None
        )

        account.last_equity = (
            float(equity)
            if equity is not None
            else None
        )

        account.last_free_margin = (
            float(free_margin)
            if free_margin is not None
            else None
        )

        # ========================================================
        # VERIFICATION ERROR DETAILS
        # ========================================================

        if verified:
            account.last_error = None

        else:
            problems = []

            if not terminal_connected:
                problems.append(
                    "MT5 terminal is not connected."
                )

            if not login_matches:
                problems.append(
                    "MT5 account number does not match."
                )

            if not server_matches:
                problems.append(
                    "MT5 server does not match."
                )

            account.last_error = " ".join(
                problems
            )

        account.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(account)

        return {
            "status": (
                "connected_and_verified"
                if verified
                else "verification_failed"
            ),
            "account": _serialize(
                account
            ),
            "verification": {
                "terminal_connected": (
                    terminal_connected
                ),
                "account_number_matches": (
                    login_matches
                ),
                "server_matches": (
                    server_matches
                ),
                "account_verified": (
                    verified
                ),
                "account_trade_allowed": (
                    account_trade_allowed
                ),
                "account_trade_expert": (
                    account_trade_expert
                ),
                "terminal_trade_allowed": (
                    terminal_trade_allowed
                ),
                "terminal_tradeapi_disabled": (
                    terminal_trade_api_disabled
                ),
                "trading_allowed": (
                    trading_allowed
                ),
            },
            "live_authorization": False,
            "order_created": False,
        }

    except HTTPException:
        raise

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=(
                "MT5 account connection failed: "
                f"{exc}"
            ),
        ) from exc

    finally:
        db.close()


# ============================================================
# DISCONNECT MT5 ACCOUNT
# ============================================================

@router.post("/{account_id}/disconnect")
async def disconnect_broker_account(
    account_id: str,
):
    """
    Disconnect the MT5 terminal session.

    IMPORTANT:
    Disconnecting does NOT close broker positions.
    """

    db = SessionLocal()

    try:
        account = _get_account(
            db,
            account_id,
        )

        try:
            from .mt5_broker_adapter import (
                mt5_broker_adapter,
            )
        except ImportError:
            from mt5_broker_adapter import (
                mt5_broker_adapter,
            )

        disconnect_error = None

        try:
            await mt5_broker_adapter.disconnect()

        except Exception as exc:
            disconnect_error = str(exc)

        account.connection_status = (
            "disconnected"
        )

        account.account_verified = 0
        account.trading_allowed = 0

        # Disconnect always removes live authorization.
        account.live_trading_authorized = 0

        if disconnect_error:
            account.last_error = (
                disconnect_error
            )

        else:
            account.last_error = None

        account.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(account)

        return {
            "status": "disconnected",
            "account": _serialize(
                account
            ),
            "order_created": False,
        }

    finally:
        db.close()


# ============================================================
# DISABLE LIVE TRADING FOR ACCOUNT
# ============================================================

@router.post("/{account_id}/disable-live")
def disable_live_trading(
    account_id: str,
):
    db = SessionLocal()

    try:
        account = _get_account(
            db,
            account_id,
        )

        account.live_trading_authorized = 0
        account.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(account)

        return {
            "status": "live_disabled",
            "account": _serialize(
                account
            ),
        }

    finally:
        db.close()


# ============================================================
# DELETE ACCOUNT
# ============================================================

@router.delete("/{account_id}")
def delete_broker_account(
    account_id: str,
):
    db = SessionLocal()

    try:
        account = _get_account(
            db,
            account_id,
        )

        if account.selected:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Cannot delete the selected "
                    "broker account. Select another "
                    "account first."
                ),
            )

        db.delete(account)
        db.commit()

        return {
            "status": "deleted",
            "account_id": account_id,
        }

    except HTTPException:
        db.rollback()
        raise

    finally:
        db.close()
