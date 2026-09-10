"""
RAYMOND v2.8 - Demo / Paper Trading Engine

Step 10A:
- Safe paper-trading execution only.
- Tracks simulated trades.
- Calculates performance metrics.
- Enforces basic risk limits.
- Never places real broker orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4


class DemoTradingError(RuntimeError):
    """Raised when demo trading cannot continue safely."""


@dataclass
class DemoTrade:
    """A simulated paper trade."""

    trade_id: str
    symbol: str
    direction: str
    entry_price: float
    quantity: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    exit_price: Optional[float] = None
    pnl: float = 0.0
    status: str = "open"
    execution_type: str = "paper"
    opened_at: datetime = None
    closed_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if self.opened_at is None:
            self.opened_at = datetime.now(timezone.utc)


@dataclass(frozen=True)
class DemoPerformance:
    """Calculated demo-trading performance."""

    total_trades: int
    winning_trades: int
    losing_trades: int
    open_trades: int
    win_rate: float
    total_pnl: float
    gross_profit: float
    gross_loss: float
    profit_factor: float
    max_drawdown: float
    expectancy: float


class DemoTradingEngine:
    """
    Safe paper-trading engine.

    This engine deliberately has no broker-order functionality.
    It only simulates trades in memory.
    """

    def __init__(
        self,
        initial_balance: float = 10_000.0,
        max_open_trades: int = 3,
        max_daily_loss: float = 300.0,
    ) -> None:
        if initial_balance <= 0:
            raise DemoTradingError(
                "Initial balance must be greater than zero."
            )

        if max_open_trades <= 0:
            raise DemoTradingError(
                "max_open_trades must be greater than zero."
            )

        if max_daily_loss < 0:
            raise DemoTradingError(
                "max_daily_loss cannot be negative."
            )

        self.initial_balance = float(initial_balance)
        self.max_open_trades = int(max_open_trades)
        self.max_daily_loss = float(max_daily_loss)

        self._trades: Dict[str, DemoTrade] = {}

    @staticmethod
    def _validate_direction(direction: str) -> str:
        normalized = direction.lower().strip()

        if normalized not in {"buy", "sell"}:
            raise DemoTradingError(
                "Direction must be 'buy' or 'sell'."
            )

        return normalized

    @staticmethod
    def _validate_price(
        price: float,
        name: str,
    ) -> float:
        try:
            value = float(price)
        except (TypeError, ValueError) as exc:
            raise DemoTradingError(
                f"{name} must be numeric."
            ) from exc

        if value <= 0:
            raise DemoTradingError(
                f"{name} must be greater than zero."
            )

        return value

    @staticmethod
    def _validate_quantity(quantity: float) -> float:
        try:
            value = float(quantity)
        except (TypeError, ValueError) as exc:
            raise DemoTradingError(
                "Quantity must be numeric."
            ) from exc

        if value <= 0:
            raise DemoTradingError(
                "Quantity must be greater than zero."
            )

        return value

    @property
    def trades(self) -> List[DemoTrade]:
        """Return a copy of all simulated trades."""

        return list(self._trades.values())

    @property
    def open_trades(self) -> List[DemoTrade]:
        """Return currently open simulated trades."""

        return [
            trade
            for trade in self._trades.values()
            if trade.status == "open"
        ]

    def daily_closed_pnl(self) -> float:
        """
        Return today's closed-trade P&L.

        Uses UTC to keep the demo engine deterministic.
        """

        today = datetime.now(timezone.utc).date()

        total = 0.0

        for trade in self._trades.values():
            if trade.status != "closed":
                continue

            if trade.closed_at is None:
                continue

            closed_date = trade.closed_at.astimezone(
                timezone.utc
            ).date()

            if closed_date == today:
                total += trade.pnl

        return total

    def can_open_trade(self) -> bool:
        """Return whether another demo trade may be opened."""

        if len(self.open_trades) >= self.max_open_trades:
            return False

        if self.daily_closed_pnl() <= -self.max_daily_loss:
            return False

        return True

    def open_trade(
        self,
        *,
        symbol: str,
        direction: str,
        entry_price: float,
        quantity: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        trade_id: Optional[str] = None,
    ) -> DemoTrade:
        """
        Open a simulated paper trade.

        No broker, MT5, Exness, or live-order API is called.

        ``trade_id`` may be supplied by the journal/integration layer.
        If omitted, a unique demo ID is generated automatically.
        """

        if not symbol or not symbol.strip():
            raise DemoTradingError(
                "Symbol is required."
            )

        if not self.can_open_trade():
            raise DemoTradingError(
                "Demo trading risk limits prevent opening another trade."
            )

        normalized_direction = self._validate_direction(
            direction
        )

        entry = self._validate_price(
            entry_price,
            "Entry price",
        )

        qty = self._validate_quantity(quantity)

        sl = None
        if stop_loss is not None:
            sl = self._validate_price(
                stop_loss,
                "Stop-loss price",
            )

        tp = None
        if take_profit is not None:
            tp = self._validate_price(
                take_profit,
                "Take-profit price",
            )

        if normalized_direction == "buy":
            if sl is not None and sl >= entry:
                raise DemoTradingError(
                    "Buy stop-loss must be below entry price."
                )

            if tp is not None and tp <= entry:
                raise DemoTradingError(
                    "Buy take-profit must be above entry price."
                )

        if normalized_direction == "sell":
            if sl is not None and sl <= entry:
                raise DemoTradingError(
                    "Sell stop-loss must be above entry price."
                )

            if tp is not None and tp >= entry:
                raise DemoTradingError(
                    "Sell take-profit must be below entry price."
                )

        normalized_trade_id = (
            trade_id.strip()
            if trade_id is not None
            else f"demo-{uuid4().hex}"
        )

        if not normalized_trade_id:
            raise DemoTradingError(
                "Trade ID cannot be empty."
            )

        if normalized_trade_id in self._trades:
            raise DemoTradingError(
                "Demo trade ID already exists."
            )

        trade = DemoTrade(
            trade_id=normalized_trade_id,
            symbol=symbol.strip().upper(),
            direction=normalized_direction,
            entry_price=entry,
            quantity=qty,
            stop_loss=sl,
            take_profit=tp,
            execution_type="paper",
        )

        self._trades[trade.trade_id] = trade

        return trade

    def close_trade(
        self,
        trade_id: str,
        exit_price: float,
    ) -> DemoTrade:
        """Close a simulated trade and calculate realized P&L."""

        trade = self._trades.get(trade_id)

        if trade is None:
            raise DemoTradingError(
                "Demo trade was not found."
            )

        if trade.status != "open":
            raise DemoTradingError(
                "Demo trade is already closed."
            )

        exit_value = self._validate_price(
            exit_price,
            "Exit price",
        )

        if trade.direction == "buy":
            trade.pnl = (
                exit_value - trade.entry_price
            ) * trade.quantity
        else:
            trade.pnl = (
                trade.entry_price - exit_value
            ) * trade.quantity

        trade.exit_price = exit_value
        trade.status = "closed"
        trade.closed_at = datetime.now(
            timezone.utc
        )

        return trade

    def cancel_trade(
        self,
        trade_id: str,
    ) -> DemoTrade:
        """
        Cancel an open simulated trade.

        Cancellation produces no P&L.
        """

        trade = self._trades.get(trade_id)

        if trade is None:
            raise DemoTradingError(
                "Demo trade was not found."
            )

        if trade.status != "open":
            raise DemoTradingError(
                "Only open demo trades can be cancelled."
            )

        trade.status = "cancelled"
        trade.closed_at = datetime.now(
            timezone.utc
        )

        return trade

    def performance(self) -> DemoPerformance:
        """Calculate demo-trading performance metrics."""

        closed_trades = [
            trade
            for trade in self._trades.values()
            if trade.status == "closed"
        ]

        open_count = len(self.open_trades)

        total_trades = len(closed_trades)

        winning = [
            trade
            for trade in closed_trades
            if trade.pnl > 0
        ]

        losing = [
            trade
            for trade in closed_trades
            if trade.pnl < 0
        ]

        winning_trades = len(winning)
        losing_trades = len(losing)

        total_pnl = sum(
            trade.pnl
            for trade in closed_trades
        )

        gross_profit = sum(
            trade.pnl
            for trade in winning
        )

        gross_loss = abs(
            sum(
                trade.pnl
                for trade in losing
            )
        )

        if total_trades > 0:
            win_rate = (
                winning_trades
                / total_trades
                * 100.0
            )
            expectancy = (
                total_pnl
                / total_trades
            )
        else:
            win_rate = 0.0
            expectancy = 0.0

        if gross_loss > 0:
            profit_factor = (
                gross_profit
                / gross_loss
            )
        elif gross_profit > 0:
            profit_factor = float("inf")
        else:
            profit_factor = 0.0

        balance = self.initial_balance
        peak_balance = self.initial_balance
        max_drawdown = 0.0

        for trade in sorted(
            closed_trades,
            key=lambda item: item.closed_at
            or datetime.min.replace(
                tzinfo=timezone.utc
            ),
        ):
            balance += trade.pnl

            if balance > peak_balance:
                peak_balance = balance

            drawdown = peak_balance - balance

            if drawdown > max_drawdown:
                max_drawdown = drawdown

        return DemoPerformance(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            open_trades=open_count,
            win_rate=win_rate,
            total_pnl=total_pnl,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown,
            expectancy=expectancy,
        )

    def reset(self) -> None:
        """Clear all simulated trades."""

        self._trades.clear()

    def status(self) -> dict:
        """
        Return a safe read-only status snapshot.

        Live trading is explicitly reported as disabled.
        """

        performance = self.performance()

        return {
            "mode": "demo",
            "execution_type": "paper",
            "live_trading_enabled": False,
            "real_orders_allowed": False,
            "open_trades": performance.open_trades,
            "total_trades": performance.total_trades,
            "winning_trades": performance.winning_trades,
            "losing_trades": performance.losing_trades,
            "win_rate": performance.win_rate,
            "total_pnl": performance.total_pnl,
            "gross_profit": performance.gross_profit,
            "gross_loss": performance.gross_loss,
            "profit_factor": performance.profit_factor,
            "max_drawdown": performance.max_drawdown,
            "expectancy": performance.expectancy,
            "daily_closed_pnl": self.daily_closed_pnl(),
        }
