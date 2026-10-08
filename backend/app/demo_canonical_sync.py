"""
RAYMOND v2.8 - DEMO Canonical State Synchronization

Batch 2.

Synchronizes verified MT5 DEMO broker reality into Raymond's
persistent canonical trading state.

Flow:

    MT5 DEMO
       |
       v
    canonical_state.py
       |
       v
    PostgreSQL
       |
       v
    Flutter

Important:

- DEMO only.
- Never enables LIVE.
- Never sends orders.
- Never modifies broker positions.
- MT5 remains authoritative for actual broker state.
- PostgreSQL remains authoritative for Raymond application state.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

try:
    from .canonical_state import (
        TradingStateRepository,
    )
    from .database import SessionLocal
except ImportError:
    from canonical_state import (
        TradingStateRepository,
    )
    from database import SessionLocal


class DemoCanonicalSyncError(RuntimeError):
    """Raised when DEMO canonical synchronization fails safely."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int_or_none(
    value: Any,
) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _position_side(
    position: Any,
) -> str:
    position_type = getattr(
        position,
        "type",
        None,
    )

    buy_type = getattr(
        mt5,
        "POSITION_TYPE_BUY",
        0,
    )

    return (
        "buy"
        if position_type == buy_type
        else "sell"
    )


def _position_ticket(
    position: Any,
) -> str | None:
    ticket = getattr(
        position,
        "ticket",
        None,
    )

    if ticket is None:
        return None

    return str(ticket)


def _broker_server(
    account_info: dict[str, Any],
) -> str | None:
    server = account_info.get("server")

    if server is None:
        return None

    return str(server)


def _broker_name(
    account_info: dict[str, Any],
) -> str:
    """
    MT5 itself does not always expose a clean broker name.

    Use the explicit broker field when available, otherwise
    identify the source as MT5 DEMO.
    """

    broker = account_info.get(
        "company"
    )

    if broker:
        return str(broker)

    return "MT5"


def _platform_name() -> str:
    return "MT5"


def _position_comment(
    position: Any,
) -> str | None:
    comment = getattr(
        position,
        "comment",
        None,
    )

    if comment is None:
        return None

    return str(comment)


def _position_magic(
    position: Any,
) -> int | None:
    return _as_int_or_none(
        getattr(
            position,
            "magic",
            None,
        )
    )


def _position_signal_id(
    position: Any,
) -> str | None:
    """
    Raymond DEMO execution embeds the signal identity into
    the broker comment.

    Do not manufacture a fake strategy signal when the broker
    does not contain one.
    """

    comment = _position_comment(
        position
    )

    if not comment:
        return None

    if comment.startswith(
        "RAYMOND-"
    ):
        return comment

    return None


def _find_open_canonical_position(
    repository: TradingStateRepository,
    *,
    ticket: str,
):
    return repository.get_position_by_ticket(
        mode="demo",
        broker_position_ticket=ticket,
    )


def synchronize_demo_positions(
    *,
    mt5_module: Any = None,
) -> dict[str, Any]:
    """
    Synchronize all currently open MT5 DEMO positions.

    This function is deliberately synchronous because the MetaTrader5
    Python API is synchronous.
    """

    broker_api = (
        mt5_module
        if mt5_module is not None
        else mt5
    )

    if broker_api is None:
        raise DemoCanonicalSyncError(
            "MetaTrader5 Python package is unavailable."
        )

    account = broker_api.account_info()

    if account is None:
        raise DemoCanonicalSyncError(
            "Unable to read MT5 DEMO account information."
        )

    account_data = account._asdict()

    trade_mode = account_data.get(
        "trade_mode"
    )

    demo_mode = getattr(
        broker_api,
        "ACCOUNT_TRADE_MODE_DEMO",
        0,
    )

    if trade_mode != demo_mode:
        raise DemoCanonicalSyncError(
            "Canonical DEMO synchronization blocked: "
            "connected MT5 account is not DEMO."
        )

    broker_positions = (
        broker_api.positions_get()
        or ()
    )

    with SessionLocal() as db:
        repository = TradingStateRepository(
            db
        )

        created = 0
        updated = 0
        skipped = 0

        synced_tickets: set[str] = set()

        broker_name = _broker_name(
            account_data
        )

        server = _broker_server(
            account_data
        )

        account_number = account_data.get(
            "login"
        )

        broker_account_id = None

        try:
            if account_number is not None:
                broker_account_id = int(
                    account_number
                )
        except (TypeError, ValueError):
            broker_account_id = None

        for position in broker_positions:
            ticket = _position_ticket(
                position
            )

            if not ticket:
                skipped += 1
                continue

            synced_tickets.add(ticket)

            symbol = str(
                getattr(
                    position,
                    "symbol",
                    "",
                )
            ).strip()

            if not symbol:
                skipped += 1
                continue

            side = _position_side(
                position
            )

            volume = _as_float(
                getattr(
                    position,
                    "volume",
                    0.0,
                )
            )

            entry_price = _as_float(
                getattr(
                    position,
                    "price_open",
                    0.0,
                )
            )

            current_price = _as_float(
                getattr(
                    position,
                    "price_current",
                    0.0,
                )
            )

            stop_loss = _as_float(
                getattr(
                    position,
                    "sl",
                    0.0,
                ),
                default=0.0,
            )

            take_profit = _as_float(
                getattr(
                    position,
                    "tp",
                    0.0,
                ),
                default=0.0,
            )

            if (
                volume <= 0
                or entry_price <= 0
                or current_price <= 0
            ):
                skipped += 1
                continue

            existing = (
                _find_open_canonical_position(
                    repository,
                    ticket=ticket,
                )
            )

            if existing is None:
                repository.create_position(
                    mode="demo",
                    symbol=symbol,
                    side=side,
                    volume=volume,
                    entry_price=entry_price,
                    stop_loss=(
                        stop_loss
                        if stop_loss > 0
                        else None
                    ),
                    take_profit=(
                        take_profit
                        if take_profit > 0
                        else None
                    ),
                    broker_account_id=(
                        broker_account_id
                    ),
                    broker=broker_name,
                    platform=_platform_name(),
                    server=server,
                    broker_position_ticket=ticket,
                    strategy_signal_id=(
                        _position_signal_id(
                            position
                        )
                    ),
                    magic=_position_magic(
                        position
                    ),
                    comment=_position_comment(
                        position
                    ),
                )

                # Fetch the newly created canonical row so that
                # the market state is immediately current.
                created_position = (
                    repository.get_position_by_ticket(
                        mode="demo",
                        broker_position_ticket=ticket,
                    )
                )

                if created_position is not None:
                    repository.update_market(
                        created_position,
                        current_price=current_price,
                        broker_sync=True,
                    )

                    repository.update_management(
                        created_position,
                        reconciliation_status="synchronized",
                        protection_status="observed",
                    )

                created += 1

            else:
                repository.update_market(
                    existing,
                    current_price=current_price,
                    broker_sync=True,
                )

                repository.update_management(
                    existing,
                    stop_loss=(
                        stop_loss
                        if stop_loss > 0
                        else None
                    ),
                    take_profit=(
                        take_profit
                        if take_profit > 0
                        else None
                    ),
                    reconciliation_status="synchronized",
                    protection_status="observed",
                )

                updated += 1

        # ----------------------------------------------------------
        # ACCOUNT SNAPSHOT
        # ----------------------------------------------------------

        balance = _as_float(
            account_data.get(
                "balance"
            )
        )

        equity = _as_float(
            account_data.get(
                "equity"
            ),
            default=balance,
        )

        floating_pnl = (
            equity - balance
        )

        margin = _as_float(
            account_data.get(
                "margin"
            )
        )

        free_margin = _as_float(
            account_data.get(
                "margin_free"
            ),
            default=(
                equity - margin
            ),
        )

        repository.upsert_account_snapshot(
            mode="demo",
            balance=balance,
            equity=equity,
            floating_pnl=floating_pnl,
            realized_pnl=0.0,
            available_balance=free_margin,
            margin=margin,
            free_margin=free_margin,
            open_positions=len(
                broker_positions
            ),
            broker_account_id=(
                broker_account_id
            ),
            broker=broker_name,
            server=server,
            currency=str(
                account_data.get(
                    "currency",
                    "USD",
                )
            ),
        )

        return {
            "status": "ok",
            "mode": "demo",
            "source": "mt5",
            "canonical_state": True,
            "account_number": (
                account_number
            ),
            "balance": balance,
            "equity": equity,
            "floating_pnl": floating_pnl,
            "open_positions": len(
                broker_positions
            ),
            "created_positions": created,
            "updated_positions": updated,
            "skipped_positions": skipped,
            "synced_tickets": sorted(
                synced_tickets
            ),
            "timestamp": _utc_now().isoformat(),
        }


def synchronize_demo_position(
    *,
    position: Any,
    account_info: dict[str, Any],
    mt5_module: Any = None,
) -> dict[str, Any]:
    """
    Synchronize one verified DEMO position.

    Useful immediately after order verification.
    """

    broker_api = (
        mt5_module
        if mt5_module is not None
        else mt5
    )

    if broker_api is None:
        raise DemoCanonicalSyncError(
            "MetaTrader5 Python package is unavailable."
        )

    trade_mode = account_info.get(
        "trade_mode"
    )

    demo_mode = getattr(
        broker_api,
        "ACCOUNT_TRADE_MODE_DEMO",
        0,
    )

    if trade_mode != demo_mode:
        raise DemoCanonicalSyncError(
            "Single-position synchronization requires a DEMO account."
        )

    ticket = _position_ticket(
        position
    )

    if not ticket:
        raise DemoCanonicalSyncError(
            "Verified DEMO position has no broker ticket."
        )

    symbol = str(
        getattr(
            position,
            "symbol",
            "",
        )
    ).strip()

    side = _position_side(
        position
    )

    volume = _as_float(
        getattr(
            position,
            "volume",
            0.0,
        )
    )

    entry_price = _as_float(
        getattr(
            position,
            "price_open",
            0.0,
        )
    )

    current_price = _as_float(
        getattr(
            position,
            "price_current",
            0.0,
        )
    )

    if (
        not symbol
        or volume <= 0
        or entry_price <= 0
        or current_price <= 0
    ):
        raise DemoCanonicalSyncError(
            "Verified DEMO position contains invalid "
            "symbol, volume or price."
        )

    stop_loss = _as_float(
        getattr(
            position,
            "sl",
            0.0,
        )
    )

    take_profit = _as_float(
        getattr(
            position,
            "tp",
            0.0,
        )
    )

    account_number = account_info.get(
        "login"
    )

    try:
        broker_account_id = (
            int(account_number)
            if account_number is not None
            else None
        )
    except (TypeError, ValueError):
        broker_account_id = None

    with SessionLocal() as db:
        repository = TradingStateRepository(
            db
        )

        existing = repository.get_position_by_ticket(
            mode="demo",
            broker_position_ticket=ticket,
        )

        if existing is None:
            existing = repository.create_position(
                mode="demo",
                symbol=symbol,
                side=side,
                volume=volume,
                entry_price=entry_price,
                stop_loss=(
                    stop_loss
                    if stop_loss > 0
                    else None
                ),
                take_profit=(
                    take_profit
                    if take_profit > 0
                    else None
                ),
                broker_account_id=(
                    broker_account_id
                ),
                broker=_broker_name(
                    account_info
                ),
                platform=_platform_name(),
                server=_broker_server(
                    account_info
                ),
                broker_position_ticket=ticket,
                strategy_signal_id=(
                    _position_signal_id(
                        position
                    )
                ),
                magic=_position_magic(
                    position
                ),
                comment=_position_comment(
                    position
                ),
            )

        repository.update_market(
            existing,
            current_price=current_price,
            broker_sync=True,
        )

        repository.update_management(
            existing,
            stop_loss=(
                stop_loss
                if stop_loss > 0
                else None
            ),
            take_profit=(
                take_profit
                if take_profit > 0
                else None
            ),
            reconciliation_status="synchronized",
            protection_status="observed",
        )

        return {
            "status": "ok",
            "mode": "demo",
            "canonical_id": existing.canonical_id,
            "broker_position_ticket": ticket,
            "symbol": symbol,
            "side": side,
            "volume": volume,
            "entry_price": entry_price,
            "current_price": current_price,
            "unrealized_pnl": float(
                existing.unrealized_pnl or 0.0
            ),
            "total_pnl": float(
                existing.total_pnl or 0.0
            ),
        }


__all__ = [
    "DemoCanonicalSyncError",
    "synchronize_demo_positions",
    "synchronize_demo_position",
      ]
