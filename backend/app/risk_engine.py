"""
RAYMOND v2.8 Risk Engine

Step 4B:
- Broker-neutral risk configuration
- Broker/instrument-aware position sizing
- MT5 symbol specification support
- Risk/reward validation
- No trade execution
"""

from dataclasses import dataclass
from typing import Optional


class RiskEngineError(ValueError):
    """Raised when a risk calculation or validation fails."""


@dataclass
class RiskConfig:
    """
    Global trading-risk limits.

    Percentages are expressed as normal percentages:
    1.0 = 1% of account equity.
    """

    risk_per_trade_percent: float = 1.0
    max_daily_loss_percent: float = 3.0
    max_open_positions: int = 3
    max_total_exposure_percent: float = 5.0
    require_stop_loss: bool = True
    min_risk_reward: float = 1.5

    def validate(self) -> None:
        if not 0 < self.risk_per_trade_percent <= 100:
            raise RiskEngineError(
                "risk_per_trade_percent must be between 0 and 100"
            )

        if not 0 < self.max_daily_loss_percent <= 100:
            raise RiskEngineError(
                "max_daily_loss_percent must be between 0 and 100"
            )

        if self.max_open_positions < 1:
            raise RiskEngineError(
                "max_open_positions must be at least 1"
            )

        if not 0 < self.max_total_exposure_percent <= 100:
            raise RiskEngineError(
                "max_total_exposure_percent must be between 0 and 100"
            )

        if self.min_risk_reward <= 0:
            raise RiskEngineError(
                "min_risk_reward must be greater than 0"
            )


@dataclass
class SymbolSpecification:
    """
    Broker-provided trading specification.

    Values originate from MT5 symbol_info().
    """

    symbol: str
    digits: int
    point: float

    tick_size: float
    tick_value: float
    tick_value_profit: float
    tick_value_loss: float

    contract_size: float

    volume_min: float
    volume_max: float
    volume_step: float
    volume_limit: float

    trade_mode: int
    trade_execution_mode: int
    trade_stops_level: int
    trade_freeze_level: int

    currency_base: str
    currency_profit: str
    currency_margin: str

    spread: int
    spread_float: bool

    def validate(self) -> None:
        if not self.symbol:
            raise RiskEngineError(
                "symbol is required"
            )

        if self.digits < 0:
            raise RiskEngineError(
                "digits cannot be negative"
            )

        if self.point <= 0:
            raise RiskEngineError(
                "point must be greater than zero"
            )

        if self.tick_size <= 0:
            raise RiskEngineError(
                "tick_size must be greater than zero"
            )

        if self.tick_value <= 0:
            raise RiskEngineError(
                "tick_value must be greater than zero"
            )

        if self.tick_value_profit <= 0:
            raise RiskEngineError(
                "tick_value_profit must be greater than zero"
            )

        if self.tick_value_loss <= 0:
            raise RiskEngineError(
                "tick_value_loss must be greater than zero"
            )

        if self.volume_min <= 0:
            raise RiskEngineError(
                "volume_min must be greater than zero"
            )

        if self.volume_max < self.volume_min:
            raise RiskEngineError(
                "volume_max cannot be less than volume_min"
            )

        if self.volume_step <= 0:
            raise RiskEngineError(
                "volume_step must be greater than zero"
            )


class RiskEngine:
    """
    Broker-neutral risk calculator.

    This class does not communicate with MT5 and does not
    place, modify, or close trades.
    """

    def __init__(
        self,
        config: Optional[RiskConfig] = None,
    ):
        self.config = config or RiskConfig()
        self.config.validate()

    def risk_amount(
        self,
        equity: float,
    ) -> float:
        """Return the maximum money risk for one trade."""

        if equity <= 0:
            raise RiskEngineError(
                "equity must be greater than zero"
            )

        return equity * (
            self.config.risk_per_trade_percent / 100
        )

    def daily_loss_limit(
        self,
        equity: float,
    ) -> float:
        """Return the maximum permitted daily loss."""

        if equity <= 0:
            raise RiskEngineError(
                "equity must be greater than zero"
            )

        return equity * (
            self.config.max_daily_loss_percent / 100
        )

    def calculate_position_size(
        self,
        equity: float,
        entry_price: float,
        stop_loss_price: float,
        risk_per_unit: float,
        volume_step: float = 0.01,
        min_volume: float = 0.01,
        max_volume: Optional[float] = None,
    ) -> float:
        """
        Calculate position size from monetary risk.

        risk_per_unit is the money lost for one volume unit
        when price moves from entry to the stop-loss.
        """

        if equity <= 0:
            raise RiskEngineError(
                "equity must be greater than zero"
            )

        if entry_price <= 0:
            raise RiskEngineError(
                "entry_price must be greater than zero"
            )

        if stop_loss_price <= 0:
            raise RiskEngineError(
                "stop_loss_price must be greater than zero"
            )

        if risk_per_unit <= 0:
            raise RiskEngineError(
                "risk_per_unit must be greater than zero"
            )

        if volume_step <= 0:
            raise RiskEngineError(
                "volume_step must be greater than zero"
            )

        if min_volume <= 0:
            raise RiskEngineError(
                "min_volume must be greater than zero"
            )

        stop_distance = abs(
            entry_price - stop_loss_price
        )

        if stop_distance == 0:
            raise RiskEngineError(
                "stop_loss_price must differ from entry_price"
            )

        risk_budget = self.risk_amount(equity)

        raw_volume = risk_budget / risk_per_unit

        volume_steps = int(
            raw_volume / volume_step
        )

        volume = volume_steps * volume_step

        if volume < min_volume:
            return 0.0

        if max_volume is not None:
            if max_volume <= 0:
                raise RiskEngineError(
                    "max_volume must be greater than zero"
                )

            volume = min(volume, max_volume)

        return round(volume, 8)

    def calculate_position_size_from_symbol(
        self,
        equity: float,
        entry_price: float,
        stop_loss_price: float,
        specification: SymbolSpecification,
    ) -> float:
        """
        Calculate position size using actual broker symbol data.

        The broker's tick size and tick value determine how much
        one volume unit loses for a given price movement.
        """

        specification.validate()

        stop_distance = abs(
            entry_price - stop_loss_price
        )

        if stop_distance == 0:
            raise RiskEngineError(
                "stop_loss_price must differ from entry_price"
            )

        # Use the losing-side tick value for conservative sizing.
        loss_per_volume = (
            stop_distance
            / specification.tick_size
        ) * specification.tick_value_loss

        return self.calculate_position_size(
            equity=equity,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            risk_per_unit=loss_per_volume,
            volume_step=specification.volume_step,
            min_volume=specification.volume_min,
            max_volume=specification.volume_max,
        )

    def validate_stop_loss(
        self,
        entry_price: float,
        stop_loss_price: Optional[float],
    ) -> None:
        """Require a valid stop loss when configured."""

        if not self.config.require_stop_loss:
            return

        if stop_loss_price is None:
            raise RiskEngineError(
                "stop loss is required"
            )

        if stop_loss_price <= 0:
            raise RiskEngineError(
                "stop loss must be greater than zero"
            )

        if entry_price <= 0:
            raise RiskEngineError(
                "entry price must be greater than zero"
            )

        if stop_loss_price == entry_price:
            raise RiskEngineError(
                "stop loss cannot equal entry price"
            )

    def validate_risk_reward(
        self,
        entry_price: float,
        stop_loss_price: float,
        take_profit_price: float,
    ) -> float:
        """Return risk/reward ratio and enforce minimum."""

        risk = abs(
            entry_price - stop_loss_price
        )

        reward = abs(
            take_profit_price - entry_price
        )

        if risk == 0:
            raise RiskEngineError(
                "stop loss distance must be greater than zero"
            )

        if reward == 0:
            raise RiskEngineError(
                "take profit distance must be greater than zero"
            )

        ratio = reward / risk

        if ratio < self.config.min_risk_reward:
            raise RiskEngineError(
                "risk/reward ratio is below the configured minimum"
            )

        return round(ratio, 8)
