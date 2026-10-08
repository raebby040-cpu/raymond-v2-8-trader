"""
RAYMOND v2.8 - Broker Account Management

STEP 17.1

Provides:
- Multiple broker-account records
- MT5 account configuration
- Masked account numbers
- Selected/active account
- Connection status
- Account verification state
- Trading permission state
- Explicit live-trading authorization state

SECURITY:
- Raw broker passwords are NEVER returned by API responses.
- This module stores only a credential reference.
- The credential reference should point to a secure secret store
  or encrypted credential record.
- Account metadata and secrets are deliberately separated.
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
        "created_at": account.created_at.isoformat()
        if account.created_at
        else None,
        "updated_at": account.updated_at.isoformat()
        if account.updated_at
        else None,
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
                == payload.account_number
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
            account_number=payload.account_number.strip(),
            credential_ref=payload.credential_ref.strip(),
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

        if payload.credential_ref is not None:
            account.credential_ref = (
                payload.credential_ref.strip()
            )

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
            "account": _serialize(account),
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
