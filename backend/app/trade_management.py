"""
RAYMOND v2.8 - Trade Management

STEP 7:
- Break-even management
- Trailing-stop calculation
- Partial-close calculation
- Broker-neutral trade-management decisions
- Paper/simulation safe
- Does NOT send orders to MT5
- Does NOT modify live positions
"""

from dataclasses import dataclass
from typing import Optional


class TradeManagementError(ValueError):
    """Raised when a trade-management calculation is invalid."""


@dataclass(frozen=True)
class TradeManagementConfig:
    """Trade-management settings."""

    break_even_enabled: bool = True
    break_even_trigger_r: float = 1.0
    break_even_offset: float = 0.0

    trailing_enabled: bool = True
    trailing_distance: float = 0.0

    partial_close_enabled: bool = True
    partial_close_percent: float = 50.0

    def validate(self) -> None:
        if self.break_even_trigger_r <= 0:
            raise TradeManagementError(
                "break_even_trigger_r must be greater than zero"
            )

        if self.break_even_offset < 0:
            raise TradeManagementError(
                "break_even_offset cannot be negative"
            )

        if self.trailing_distance < 0:
            raise TradeManagementError(
                "trailing_distance cannot be negative"
            )

        if not 0 < self.partial_close_percent <= 100:
            raise TradeManagementError(
                "partial_close_percent must be between 0 and 100"
            )


@dataclass(frozen=True)
class BreakEvenResult:
    """Break-even calculation result."""

    triggered: bool
    new_stop_loss: Optional[float]
    reason: str


@dataclass(frozen=True)
class TrailingStopResult:
    """Trailing-stop calculation result."""

    triggered: bool
    new_stop_loss: Optional[float]
    reason: str


@dataclass(frozen=True)
class PartialCloseResult:
    """Partial-close calculation result."""

    triggered: bool
    close_volume: float
    remaining_volume: float
    reason: str


class TradeManager:
    """
    Calculates safe trade-management actions.

    This class only calculates decisions.
    It never sends, modifies, or closes broker orders.
    """

    def __init__(
        self,
        config: Optional[TradeManagementConfig] = None,
    ) -> None:
        self.config = config or TradeManagementConfig()
        self.config.validate()

    @staticmethod
    def _validate_side(side: str) -> str:
        normalized = str(side).upper()

        if normalized not in {"BUY", "SELL"}:
            raise TradeManagementError(
                "side must be BUY or SELL"
            )

        return normalized

    @staticmethod
    def _validate_price(
        name: str,
        value: float,
    ) -> None:
        if value <= 0:
            raise TradeManagementError(
                f"{name} must be greater than zero"
            )

    def calculate_break_even(
        self,
        *,
        side: str,
        entry_price: float,
        current_price: float,
        original_stop_loss: float,
    ) -> BreakEvenResult:
        """
        Move the stop to break-even after the configured R-multiple
        has been reached.

        The calculation never worsens the existing stop.
        """

        side = self._validate_side(side)

        self._validate_price(
            "entry_price",
            entry_price,
        )
        self._validate_price(
            "current_price",
            current_price,
        )
        self._validate_price(
            "original_stop_loss",
            original_stop_loss,
        )

        if not self.config.break_even_enabled:
            return BreakEvenResult(
                triggered=False,
                new_stop_loss=None,
                reason="Break-even is disabled.",
            )

        if side == "BUY":
            initial_risk = (
                entry_price - original_stop_loss
            )

            if initial_risk <= 0:
                raise TradeManagementError(
                    "BUY stop-loss must be below entry price"
                )

            profit_distance = (
                current_price - entry_price
            )

            if profit_distance <= 0:
                return BreakEvenResult(
                    triggered=False,
                    new_stop_loss=None,
                    reason="Trade is not in profit.",
                )

            current_r = (
                profit_distance / initial_risk
            )

            if current_r < self.config.break_even_trigger_r:
                return BreakEvenResult(
                    triggered=False,
                    new_stop_loss=None,
                    reason="Break-even trigger has not been reached.",
                )

            new_stop = (
                entry_price
                + self.config.break_even_offset
            )

            if new_stop <= original_stop_loss:
                return BreakEvenResult(
                    triggered=False,
                    new_stop_loss=None,
                    reason="Break-even would not improve the stop.",
                )

        else:
            initial_risk = (
                original_stop_loss - entry_price
            )

            if initial_risk <= 0:
                raise TradeManagementError(
                    "SELL stop-loss must be above entry price"
                )

            profit_distance = (
                entry_price - current_price
            )

            if profit_distance <= 0:
                return BreakEvenResult(
                    triggered=False,
                    new_stop_loss=None,
                    reason="Trade is not in profit.",
                )

            current_r = (
                profit_distance / initial_risk
            )

            if current_r < self.config.break_even_trigger_r:
                return BreakEvenResult(
                    triggered=False,
                    new_stop_loss=None,
                    reason="Break-even trigger has not been reached.",
                )

            new_stop = (
                entry_price
                - self.config.break_even_offset
            )

            if new_stop >= original_stop_loss:
                return BreakEvenResult(
                    triggered=False,
                    new_stop_loss=None,
                    reason="Break-even would not improve the stop.",
                )

        return BreakEvenResult(
            triggered=True,
            new_stop_loss=new_stop,
            reason="Break-even trigger reached.",
        )

    def calculate_trailing_stop(
        self,
        *,
        side: str,
        current_price: float,
        current_stop_loss: float,
    ) -> TrailingStopResult:
        """
        Calculate a trailing stop from the current market price.

        The result can only tighten the stop:
        - BUY stop moves upward.
        - SELL stop moves downward.
        """

        side = self._validate_side(side)

        self._validate_price(
            "current_price",
            current_price,
        )
        self._validate_price(
            "current_stop_loss",
            current_stop_loss,
        )

        if not self.config.trailing_enabled:
            return TrailingStopResult(
                triggered=False,
                new_stop_loss=None,
                reason="Trailing stop is disabled.",
            )

        if self.config.trailing_distance <= 0:
            return TrailingStopResult(
                triggered=False,
                new_stop_loss=None,
                reason="Trailing distance is not configured.",
            )

        if side == "BUY":
            new_stop = (
                current_price
                - self.config.trailing_distance
            )

            if new_stop <= current_stop_loss:
                return TrailingStopResult(
                    triggered=False,
                    new_stop_loss=None,
                    reason="Trailing stop would not improve the stop.",
                )

        else:
            new_stop = (
                current_price
                + self.config.trailing_distance
            )

            if new_stop >= current_stop_loss:
                return TrailingStopResult(
                    triggered=False,
                    new_stop_loss=None,
                    reason="Trailing stop would not improve the stop.",
                )

        return TrailingStopResult(
            triggered=True,
            new_stop_loss=new_stop,
            reason="Trailing stop can tighten the position.",
        )

    def calculate_partial_close(
        self,
        *,
        current_volume: float,
    ) -> PartialCloseResult:
        """
        Calculate the volume to close for a partial exit.

        No broker operation is performed.
        """

        if current_volume <= 0:
            raise TradeManagementError(
                "current_volume must be greater than zero"
            )

        if not self.config.partial_close_enabled:
            return PartialCloseResult(
                triggered=False,
                close_volume=0.0,
                remaining_volume=current_volume,
                reason="Partial close is disabled.",
            )

        close_volume = (
            current_volume
            * self.config.partial_close_percent
            / 100.0
        )

        remaining_volume = (
            current_volume - close_volume
        )

        if remaining_volume < 0:
            raise TradeManagementError(
                "Partial close calculation exceeded position volume"
            )

        return PartialCloseResult(
            triggered=True,
            close_volume=close_volume,
            remaining_volume=remaining_volume,
            reason="Partial close volume calculated.",
        )
