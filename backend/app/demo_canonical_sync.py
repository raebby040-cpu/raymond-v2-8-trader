"""
RAYMOND v2.8 - DEMO Canonical State Synchronization

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
    from .canonical_state import TradingStateRepository
    from .database import SessionLocal
except ImportError:
    from canonical_state import TradingStateRepository
    from database import SessionLocal


class DemoCanonicalSyncError(RuntimeError):
    """Raised when DEMO canonical synchronization fails safely."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _account_to_dict(account: Any) -> dict[str, Any]:
    """
    Normalize MT5 account_info() into a plain dictionary.

    The real MetaTrader5 API may return a namedtuple-like object
    exposing _asdict(), while tests/mocks may return dictionaries
    or SimpleNamespace objects.

    Supporting all three keeps the synchronization boundary robust
    without changing broker behavior.
    """

    if account is None:
        return {}

    if isinstance(account, dict):
        return dict(account)

    asdict = getattr(account, "_asdict", None)

    if callable(asdict):
        try:
            value = asdict()

            if isinstance(value, dict):
                return dict(value)
        except Exception:
            pass

    values = getattr(account, "__dict__", None)

    if isinstance(values, dict):
        return dict(values)

    fields = (
        "login",
        "trade_mode",
        "balance",
        "equity",
        "margin",
        "margin_free",
        "currency",
        "server",
        "company",
    )

    result: dict[str, Any] = {}

    for field in fields:
        try:
            result[field] = getattr(
                account,
                field,
            )
        except AttributeError:
            continue

    return result


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
    broker_api: Any = None,
) -> str:
    position_type = getattr(
        position,
        "type",
        None,
    )

    api = broker_api if broker_api is not None else mt5

    buy_type = getattr(
        api,
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
    server = account_info.get(
        "server"
    )

    if server is None:
        return None

    return str(server)


def _broker_name(
    account_info: dict[str, Any],
) -> str:
    """
    MT5 itself does not always expose a clean broker name.

    Use the explicit broker/company field when available,
    otherwise identify the source as MT5.
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


def _validate_demo_account(
    *,
    account_data: dict[str, Any],
    broker_api: Any,
) -> None:
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


def synchronize_demo_positions(
    *,
    mt5_module: Any = None,
) -> dict[str, Any]:
    """
    Synchronize all currently open MT5 DEMO positions.

    This function is deliberately synchronous because the MetaTrader5
    Python API is synchronous.

    It never sends or modifies broker orders.
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

    account_data = _account_to_dict(
        account
    )

    if not account_data:
        raise DemoCanonicalSyncError(
            "Unable to normalize MT5 account information."
        )

    _validate_demo_account(
        account_data=account_data,
        broker_api=broker_api,
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

        broker_account_id = _as_int_or_none(
            account_number
        )

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
                position,
                broker_api,
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
                )
            )

            take_profit = _as_float(
                getattr(
                    position,
                    "tp",
                    0.0,
                )
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
            "account_number": account_number,
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

    normalized_account = _account_to_dict(
        account_info
    )

    if not normalized_account:
        raise DemoCanonicalSyncError(
            "Unable to normalize DEMO account information."
        )

    _validate_demo_account(
        account_data=normalized_account,
        broker_api=broker_api,
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
        position,
        broker_api,
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

    account_number = normalized_account.get(
        "login"
    )

    broker_account_id = _as_int_or_none(
        account_number
    )

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
                    normalized_account
                ),
                platform=_platform_name(),
                server=_broker_server(
                    normalized_account
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
