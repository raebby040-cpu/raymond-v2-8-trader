"""
RAYMOND v2.8 - AI Trading Decision Engine

STEP 13:

- Interprets technical-indicator results.
- Produces BUY / SELL / WAIT decisions.
- Produces a conservative confidence score.
- Produces risk-aware trade proposals.
- Never places broker orders.
- Never modifies positions.
- Never bypasses the risk engine.
- Never contacts MT5.
- Paper/read-only decision support only.

IMPORTANT:

This module is intentionally deterministic.

It provides an AI-style decision layer without allowing
an external model to directly control execution.

The final authority remains the Risk Engine and safety gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class AIDecisionError(ValueError):
    """Raised when AI decision input is invalid or unsafe."""


class AIDirection(str, Enum):
    """Allowed AI trading directions."""

    BUY = "buy"
    SELL = "sell"
    WAIT = "wait"


@dataclass(frozen=True)
class AIDecisionConfig:
    """
    Configuration for the AI decision layer.

    The AI layer is deliberately conservative.

    It does not decide whether a trade is ultimately
    allowed to execute. That remains the responsibility
    of the Risk Engine.
    """

    buy_score_threshold: int = 65
    sell_score_threshold: int = 35

    minimum_confidence: float = 60.0

    max_confidence: float = 95.0

    require_stop_loss: bool = True

    minimum_risk_reward: float = 1.5

    def validate(self) -> None:
        if not (
            0 <= self.buy_score_threshold <= 100
        ):
            raise AIDecisionError(
                "buy_score_threshold must be between 0 and 100"
            )

        if not (
            0 <= self.sell_score_threshold <= 100
        ):
            raise AIDecisionError(
                "sell_score_threshold must be between 0 and 100"
            )

        if (
            self.sell_score_threshold
            >= self.buy_score_threshold
        ):
            raise AIDecisionError(
                "sell_score_threshold must be below "
                "buy_score_threshold"
            )

        if not (
            0 <= self.minimum_confidence <= 100
        ):
            raise AIDecisionError(
                "minimum_confidence must be between 0 and 100"
            )

        if not (
            0 < self.max_confidence <= 100
        ):
            raise AIDecisionError(
                "max_confidence must be between 0 and 100"
            )

        if (
            self.minimum_confidence
            > self.max_confidence
        ):
            raise AIDecisionError(
                "minimum_confidence cannot exceed max_confidence"
            )

        if self.minimum_risk_reward <= 0:
            raise AIDecisionError(
                "minimum_risk_reward must be greater than 0"
            )


@dataclass(frozen=True)
class TechnicalContext:
    """
    Technical information supplied to the AI decision layer.

    This is intentionally independent of MT5.

    The values can come from the existing technical
    indicator engine or from tests/backtesting.
    """

    symbol: str
    timeframe: str

    close: float

    ema20: Optional[float]
    ema50: Optional[float]

    rsi14: Optional[float]
    atr14: Optional[float]

    macd: Optional[float]
    macd_signal: Optional[float]
    macd_histogram: Optional[float]

    trend: str
    score: int
    signal: str

    candles_used: int

    def validate(self) -> None:
        if not self.symbol.strip():
            raise AIDecisionError(
                "symbol is required"
            )

        if not self.timeframe.strip():
            raise AIDecisionError(
                "timeframe is required"
            )

        if self.close <= 0:
            raise AIDecisionError(
                "close must be greater than zero"
            )

        if not (
            0 <= self.score <= 100
        ):
            raise AIDecisionError(
                "score must be between 0 and 100"
            )

        if self.candles_used < 1:
            raise AIDecisionError(
                "candles_used must be at least 1"
            )

        valid_trends = {
            "Bullish",
            "Bearish",
            "Neutral",
        }

        if self.trend not in valid_trends:
            raise AIDecisionError(
                "trend must be Bullish, Bearish, or Neutral"
            )

        valid_signals = {
            "BUY",
            "SELL",
            "WAIT",
        }

        if self.signal not in valid_signals:
            raise AIDecisionError(
                "signal must be BUY, SELL, or WAIT"
            )

        numeric_fields = {
            "ema20": self.ema20,
            "ema50": self.ema50,
            "rsi14": self.rsi14,
            "atr14": self.atr14,
            "macd": self.macd,
            "macd_signal": self.macd_signal,
            "macd_histogram": self.macd_histogram,
        }

        for name, value in numeric_fields.items():
            if value is None:
                continue

            if value != value:
                raise AIDecisionError(
                    f"{name} cannot be NaN"
                )

            if value in (
                float("inf"),
                float("-inf"),
            ):
                raise AIDecisionError(
                    f"{name} must be finite"
                )

        if self.rsi14 is not None:
            if not (
                0 <= self.rsi14 <= 100
            ):
                raise AIDecisionError(
                    "rsi14 must be between 0 and 100"
                )

        if self.atr14 is not None:
            if self.atr14 < 0:
                raise AIDecisionError(
                    "atr14 cannot be negative"
                )


@dataclass(frozen=True)
class AITradeProposal:
    """
    Risk-aware paper trade proposal.

    This is a proposal only.

    It is NOT an executable broker order.
    """

    direction: AIDirection

    symbol: str

    entry_price: float

    stop_loss: Optional[float]

    take_profit: Optional[float]

    risk_reward: Optional[float]

    confidence: float

    reason: str

    execution_type: str = "paper"

    read_only: bool = True

    broker_order_required: bool = False

    risk_engine_required: bool = True


@dataclass(frozen=True)
class AIDecision:
    """Complete AI decision result."""

    direction: AIDirection

    symbol: str

    timeframe: str

    confidence: float

    technical_score: int

    trend: str

    signal: str

    proposal: Optional[AITradeProposal]

    reasoning: str

    execution_type: str = "paper"

    read_only: bool = True

    broker_order_required: bool = False

    risk_engine_required: bool = True


class AITradingDecisionEngine:
    """
    Conservative AI-style trading decision engine.

    Responsibilities:
    - interpret technical context
    - calculate decision confidence
    - produce trade proposals
    - explain why the decision was made

    Explicitly NOT responsible for:
    - placing orders
    - modifying orders
    - closing positions
    - calling MT5
    - calling Exness
    - overriding the risk engine
    - overriding the emergency stop
    """

    def __init__(
        self,
        config: Optional[AIDecisionConfig] = None,
    ) -> None:
        self.config = (
            config or AIDecisionConfig()
        )

        self.config.validate()

    @staticmethod
    def _clamp(
        value: float,
        minimum: float,
        maximum: float,
    ) -> float:
        return max(
            minimum,
            min(maximum, value),
        )

    @staticmethod
    def _risk_reward(
        *,
        direction: AIDirection,
        entry: float,
        stop_loss: float,
        take_profit: float,
    ) -> float:
        if direction == AIDirection.BUY:
            risk = entry - stop_loss
            reward = take_profit - entry
        elif direction == AIDirection.SELL:
            risk = stop_loss - entry
            reward = entry - take_profit
        else:
            raise AIDecisionError(
                "WAIT does not have a risk/reward calculation"
            )

        if risk <= 0:
            raise AIDecisionError(
                "stop_loss must create positive risk"
            )

        if reward <= 0:
            raise AIDecisionError(
                "take_profit must create positive reward"
            )

        return reward / risk

    def _base_confidence(
        self,
        context: TechnicalContext,
    ) -> float:
        """
        Convert technical strength into conservative confidence.

        The confidence value is NOT a probability.

        It is a decision-strength score.
        """

        distance_from_neutral = abs(
            context.score - 50
        )

        confidence = (
            50.0
            + distance_from_neutral
        )

        if context.trend == "Bullish":
            confidence += 5.0

        elif context.trend == "Bearish":
            confidence += 5.0

        if context.signal == "WAIT":
            confidence -= 5.0

        return self._clamp(
            confidence,
            0.0,
            self.config.max_confidence,
        )

    def _determine_direction(
        self,
        context: TechnicalContext,
    ) -> AIDirection:
        """
        Determine direction conservatively.

        Technical signal and trend must agree.

        Otherwise the engine returns WAIT.
        """

        if (
            context.signal == "BUY"
            and context.trend == "Bullish"
            and context.score
            >= self.config.buy_score_threshold
        ):
            return AIDirection.BUY

        if (
            context.signal == "SELL"
            and context.trend == "Bearish"
            and context.score
            <= self.config.sell_score_threshold
        ):
            return AIDirection.SELL

        return AIDirection.WAIT

    def _build_buy_proposal(
        self,
        context: TechnicalContext,
        confidence: float,
    ) -> AITradeProposal:
        if context.atr14 is None:
            raise AIDecisionError(
                "ATR is required for a BUY proposal"
            )

        if context.atr14 <= 0:
            raise AIDecisionError(
                "ATR must be greater than zero"
            )

        entry = context.close

        # Conservative ATR-based structure.
        stop_loss = (
            entry
            - context.atr14
        )

        take_profit = (
            entry
            + (
                context.atr14
                * self.config.minimum_risk_reward
            )
        )

        risk_reward = self._risk_reward(
            direction=AIDirection.BUY,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        return AITradeProposal(
            direction=AIDirection.BUY,
            symbol=context.symbol,
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward=risk_reward,
            confidence=confidence,
            reason=(
                "Bullish technical alignment passed "
                "the AI decision threshold."
            ),
        )

    def _build_sell_proposal(
        self,
        context: TechnicalContext,
        confidence: float,
    ) -> AITradeProposal:
        if context.atr14 is None:
            raise AIDecisionError(
                "ATR is required for a SELL proposal"
            )

        if context.atr14 <= 0:
            raise AIDecisionError(
                "ATR must be greater than zero"
            )

        entry = context.close

        stop_loss = (
            entry
            + context.atr14
        )

        take_profit = (
            entry
            - (
                context.atr14
                * self.config.minimum_risk_reward
            )
        )

        risk_reward = self._risk_reward(
            direction=AIDirection.SELL,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        return AITradeProposal(
            direction=AIDirection.SELL,
            symbol=context.symbol,
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward=risk_reward,
            confidence=confidence,
            reason=(
                "Bearish technical alignment passed "
                "the AI decision threshold."
            ),
        )

    def evaluate(
        self,
        context: TechnicalContext,
    ) -> AIDecision:
        """
        Evaluate technical context.

        The result is always read-only.

        No broker or MT5 calls occur.
        """

        context.validate()

        direction = self._determine_direction(
            context
        )

        confidence = self._base_confidence(
            context
        )

        if (
            confidence
            < self.config.minimum_confidence
        ):
            direction = AIDirection.WAIT

        # ----------------------------------------------------
        # WAIT
        # ----------------------------------------------------

        if direction == AIDirection.WAIT:
            return AIDecision(
                direction=AIDirection.WAIT,
                symbol=context.symbol,
                timeframe=context.timeframe,
                confidence=confidence,
                technical_score=context.score,
                trend=context.trend,
                signal=context.signal,
                proposal=None,
                reasoning=(
                    "Technical evidence is not strong "
                    "or aligned enough for a trade proposal."
                ),
            )

        # ----------------------------------------------------
        # BUY
        # ----------------------------------------------------

        if direction == AIDirection.BUY:
            try:
                proposal = self._build_buy_proposal(
                    context,
                    confidence,
                )
            except AIDecisionError as exc:
                return AIDecision(
                    direction=AIDirection.WAIT,
                    symbol=context.symbol,
                    timeframe=context.timeframe,
                    confidence=confidence,
                    technical_score=context.score,
                    trend=context.trend,
                    signal=context.signal,
                    proposal=None,
                    reasoning=(
                        "BUY proposal rejected by "
                        f"AI safety validation: {exc}"
                    ),
                )

            return AIDecision(
                direction=AIDirection.BUY,
                symbol=context.symbol,
                timeframe=context.timeframe,
                confidence=confidence,
                technical_score=context.score,
                trend=context.trend,
                signal=context.signal,
                proposal=proposal,
                reasoning=(
                    "BUY proposal created. "
                    "Risk Engine approval is still required "
                    "before any execution."
                ),
            )

        # ----------------------------------------------------
        # SELL
        # ----------------------------------------------------

        if direction == AIDirection.SELL:
            try:
                proposal = self._build_sell_proposal(
                    context,
                    confidence,
                )
            except AIDecisionError as exc:
                return AIDecision(
                    direction=AIDirection.WAIT,
                    symbol=context.symbol,
                    timeframe=context.timeframe,
                    confidence=confidence,
                    technical_score=context.score,
                    trend=context.trend,
                    signal=context.signal,
                    proposal=None,
                    reasoning=(
                        "SELL proposal rejected by "
                        f"AI safety validation: {exc}"
                    ),
                )

            return AIDecision(
                direction=AIDirection.SELL,
                symbol=context.symbol,
                timeframe=context.timeframe,
                confidence=confidence,
                technical_score=context.score,
                trend=context.trend,
                signal=context.signal,
                proposal=proposal,
                reasoning=(
                    "SELL proposal created. "
                    "Risk Engine approval is still required "
                    "before any execution."
                ),
            )

        raise AIDecisionError(
            "Unexpected AI direction"
        )


def ai_decision_to_dict(
    decision: AIDecision,
) -> dict:
    """Serialize an AI decision safely."""

    proposal = decision.proposal

    proposal_data = None

    if proposal is not None:
        proposal_data = {
            "direction": (
                proposal.direction.value
            ),
            "symbol": proposal.symbol,
            "entry_price": proposal.entry_price,
            "stop_loss": proposal.stop_loss,
            "take_profit": proposal.take_profit,
            "risk_reward": proposal.risk_reward,
            "confidence": proposal.confidence,
            "reason": proposal.reason,
            "execution_type": (
                proposal.execution_type
            ),
            "read_only": proposal.read_only,
            "broker_order_required": (
                proposal.broker_order_required
            ),
            "risk_engine_required": (
                proposal.risk_engine_required
            ),
        }

    return {
        "direction": decision.direction.value,
        "symbol": decision.symbol,
        "timeframe": decision.timeframe,
        "confidence": decision.confidence,
        "technical_score": (
            decision.technical_score
        ),
        "trend": decision.trend,
        "signal": decision.signal,
        "proposal": proposal_data,
        "reasoning": decision.reasoning,
        "execution_type": (
            decision.execution_type
        ),
        "read_only": decision.read_only,
        "broker_order_required": (
            decision.broker_order_required
        ),
        "risk_engine_required": (
            decision.risk_engine_required
        ),
  }
