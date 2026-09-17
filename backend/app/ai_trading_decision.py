"""

RAYMOND v2.8 - AI Trading Decision Engine

STEP 13 - MULTI-LAYER AI BRAIN

Layers:

1. Market Regime

2. Setup Detection

3. Momentum / Confluence

4. Market Pressure

5. Direction

6. Confidence

7. WAIT Filter

8. Risk-aware Paper Proposal

SAFETY:

- Never places broker orders.

- Never modifies broker positions.

- Never closes broker positions.

- Never contacts MT5.

- Never contacts Exness.

- Never bypasses the Risk Engine.

- Never bypasses the Emergency Stop.

- Never enables live trading.

The AI only produces a recommendation.

Execution remains paper-only.

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

    """Conservative configuration for the AI brain."""

    buy_score_threshold: int = 65

    sell_score_threshold: int = 35

    minimum_confidence: float = 60.0

    max_confidence: float = 95.0

    require_stop_loss: bool = True

    minimum_risk_reward: float = 1.5

    minimum_confluence: int = 60

    strong_confluence: int = 75

    def validate(self) -> None:

        if not 0 <= self.buy_score_threshold <= 100:

            raise AIDecisionError(

                "buy_score_threshold must be between 0 and 100"

            )

        if not 0 <= self.sell_score_threshold <= 100:

            raise AIDecisionError(

                "sell_score_threshold must be between 0 and 100"

            )

        if self.sell_score_threshold >= self.buy_score_threshold:

            raise AIDecisionError(

                "sell_score_threshold must be below "

                "buy_score_threshold"

            )

        if not 0 <= self.minimum_confidence <= 100:

            raise AIDecisionError(

                "minimum_confidence must be between 0 and 100"

            )

        if not 0 < self.max_confidence <= 100:

            raise AIDecisionError(

                "max_confidence must be between 0 and 100"

            )

        if self.minimum_confidence > self.max_confidence:

            raise AIDecisionError(

                "minimum_confidence cannot exceed max_confidence"

            )

        if self.minimum_risk_reward <= 0:

            raise AIDecisionError(

                "minimum_risk_reward must be greater than 0"

            )

        if not 0 <= self.minimum_confluence <= 100:

            raise AIDecisionError(

                "minimum_confluence must be between 0 and 100"

            )

        if not 0 <= self.strong_confluence <= 100:

            raise AIDecisionError(

                "strong_confluence must be between 0 and 100"

            )

@dataclass(frozen=True)

class TechnicalContext:

    """Technical information supplied to the AI brain."""

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

    volatility: Optional[str] = None

    previous_close: Optional[float] = None

    # ------------------------------------------------------------

    # MARKET PRESSURE

    # ------------------------------------------------------------

    #

    # Score:

    #   +100 = strongest observed buy-side pressure

    #   -100 = strongest observed sell-side pressure

    #

    # This is advisory/confluence information.

    # It does NOT replace the established signal/trend/score logic.

    #

    market_pressure_score: Optional[int] = None

    market_pressure_label: str = "UNAVAILABLE"

    market_pressure_available: bool = False

    def validate(self) -> None:

        if not self.symbol.strip():

            raise AIDecisionError("symbol is required")

        if not self.timeframe.strip():

            raise AIDecisionError("timeframe is required")

        if self.close <= 0:

            raise AIDecisionError(

                "close must be greater than zero"

            )

        if not 0 <= self.score <= 100:

            raise AIDecisionError(

                "score must be between 0 and 100"

            )

        if self.candles_used < 1:

            raise AIDecisionError(

                "candles_used must be at least 1"

            )

        if self.trend not in {

            "Bullish",

            "Bearish",

            "Neutral",

        }:

            raise AIDecisionError(

                "trend must be Bullish, Bearish, or Neutral"

            )

        if self.signal not in {

            "BUY",

            "SELL",

            "WAIT",

        }:

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

            "previous_close": self.previous_close,

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

            if not 0 <= self.rsi14 <= 100:

                raise AIDecisionError(

                    "rsi14 must be between 0 and 100"

                )

        if self.atr14 is not None:

            if self.atr14 < 0:

                raise AIDecisionError(

                    "atr14 cannot be negative"

                )

        if self.previous_close is not None:

            if self.previous_close <= 0:

                raise AIDecisionError(

                    "previous_close must be greater than zero"

                )

        # --------------------------------------------------------

        # MARKET PRESSURE VALIDATION

        # --------------------------------------------------------

        if (

            self.market_pressure_score is not None

            and not -100 <= self.market_pressure_score <= 100

        ):

            raise AIDecisionError(

                "market_pressure_score must be between -100 and 100"

            )

        if self.market_pressure_label not in {

            "BUY_PRESSURE",

            "SELL_PRESSURE",

            "NEUTRAL",

            "UNAVAILABLE",

        }:

            raise AIDecisionError(

                "Invalid market_pressure_label"

            )

@dataclass(frozen=True)

class AITradeProposal:

    """Risk-aware paper trade proposal."""

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

    """Complete AI brain decision."""

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

    market_regime: str = "uncertain"

    setup: str = "no_setup"

    confluence_score: int = 0

    # Market-pressure output

    market_pressure_score: Optional[int] = None

    market_pressure_label: str = "UNAVAILABLE"

    market_pressure_available: bool = False

class AITradingDecisionEngine:

    """Conservative multi-layer paper-only AI decision engine."""

    def __init__(

        self,

        config: Optional[AIDecisionConfig] = None,

    ) -> None:

        self.config = config or AIDecisionConfig()

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

    def _market_regime(

        self,

        context: TechnicalContext,

    ) -> str:

        """Determine the broad market regime."""

        if (

            context.ema20 is None

            or context.ema50 is None

        ):

            return "uncertain"

        if context.ema20 > context.ema50:

            if context.trend == "Bullish":

                return "trending_up"

            return "bullish_transition"

        if context.ema20 < context.ema50:

            if context.trend == "Bearish":

                return "trending_down"

            return "bearish_transition"

        return "ranging"

    def _setup_type(

        self,

        context: TechnicalContext,

        regime: str,

    ) -> str:

        """Classify the current trading setup."""

        if context.signal == "WAIT":

            return "no_setup"

        if (

            context.signal == "BUY"

            and context.trend == "Bullish"

        ):

            if regime == "trending_up":

                return "bullish_continuation"

            if regime == "bullish_transition":

                return "bullish_transition"

        if (

            context.signal == "SELL"

            and context.trend == "Bearish"

        ):

            if regime == "trending_down":

                return "bearish_continuation"

            if regime == "bearish_transition":

                return "bearish_transition"

        if context.signal == "BUY":

            return "bullish_setup"

        if context.signal == "SELL":

            return "bearish_setup"

        return "no_setup"

    def _confluence_score(

        self,

        context: TechnicalContext,

    ) -> int:

        """

        Calculate technical confluence.

        Existing Raymond technical logic:

        - Technical score: 40

        - EMA alignment: 20

        - RSI: 15

        - MACD: 15

        - Trend/signal agreement: 10

        Market pressure:

        - Additional advisory weight: 10

        Market pressure NEVER replaces the established

        directional signal.

        """

        points = 0.0

        possible = 0.0

        # --------------------------------------------------------

        # 1. TECHNICAL SCORE - 40%

        # --------------------------------------------------------

        points += context.score * 0.40

        possible += 40.0

        # --------------------------------------------------------

        # 2. EMA ALIGNMENT - 20%

        # --------------------------------------------------------

        if (

            context.ema20 is not None

            and context.ema50 is not None

        ):

            possible += 20.0

            if context.signal == "BUY":

                if context.ema20 > context.ema50:

                    points += 20.0

            elif context.signal == "SELL":

                if context.ema20 < context.ema50:

                    points += 20.0

        # --------------------------------------------------------

        # 3. RSI - 15%

        # --------------------------------------------------------

        if context.rsi14 is not None:

            possible += 15.0

            if context.signal == "BUY":

                if 50 <= context.rsi14 <= 70:

                    points += 15.0

                elif 45 <= context.rsi14 < 50:

                    points += 7.0

            elif context.signal == "SELL":

                if 30 <= context.rsi14 <= 50:

                    points += 15.0

                elif 50 < context.rsi14 <= 55:

                    points += 7.0

        # --------------------------------------------------------

        # 4. MACD - 15%

        # --------------------------------------------------------

        if (

            context.macd is not None

            and context.macd_signal is not None

            and context.macd_histogram is not None

        ):

            possible += 15.0

            if context.signal == "BUY":

                if (

                    context.macd > context.macd_signal

                    and context.macd_histogram > 0

                ):

                    points += 15.0

                elif context.macd_histogram > 0:

                    points += 7.0

            elif context.signal == "SELL":

                if (

                    context.macd < context.macd_signal

                    and context.macd_histogram < 0

                ):

                    points += 15.0

                elif context.macd_histogram < 0:

                    points += 7.0

        # --------------------------------------------------------

        # 5. TREND / SIGNAL AGREEMENT - 10%

        # --------------------------------------------------------

        possible += 10.0

        if (

            context.signal == "BUY"

            and context.trend == "Bullish"

        ):

            points += 10.0

        elif (

            context.signal == "SELL"

            and context.trend == "Bearish"

        ):

            points += 10.0

        # --------------------------------------------------------

        # 6. MARKET PRESSURE - ADVISORY 10%

        # --------------------------------------------------------

        #

        # This is deliberately added after the existing strategy.

        #

        # Positive pressure supports BUY.

        # Negative pressure supports SELL.

        #

        # It does NOT independently create a BUY or SELL.

        # --------------------------------------------------------

        if (

            context.market_pressure_available

            and context.market_pressure_score is not None

        ):

            possible += 10.0

            pressure = context.market_pressure_score

            if context.signal == "BUY":

                if pressure >= 50:

                    points += 10.0

                elif pressure >= 25:

                    points += 7.0

                elif pressure > 0:

                    points += 3.0

            elif context.signal == "SELL":

                if pressure <= -50:

                    points += 10.0

                elif pressure <= -25:

                    points += 7.0

                elif pressure < 0:

                    points += 3.0

        if possible <= 0:

            return 0

        return int(

            self._clamp(

                (points / possible) * 100.0,

                0.0,

                100.0,

            )

        )

    def _determine_direction(

        self,

        context: TechnicalContext,

        confluence: int,

    ) -> AIDirection:

        """

        Determine BUY, SELL, or WAIT.

        Existing Raymond signal/trend/score logic remains

        the primary directional authority.

        Market pressure is advisory only.

        Risk Engine and safety controls remain mandatory.

        """

        if context.signal == "WAIT":

            return AIDirection.WAIT

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

    def _base_confidence(

        self,

        context: TechnicalContext,

        confluence: int,

    ) -> float:

        """Calculate decision strength, not probability."""

        distance_from_neutral = abs(

            context.score - 50

        )

        confidence = (

            45.0

            + distance_from_neutral * 0.55

        )

        confidence += (

            confluence - 50

        ) * 0.20

        if context.trend in {

            "Bullish",

            "Bearish",

        }:

            confidence += 5.0

        if (

            context.signal in {

                "BUY",

                "SELL",

            }

            and context.trend != "Neutral"

        ):

            confidence += 5.0

        if context.signal == "WAIT":

            confidence -= 10.0

        if context.rsi14 is not None:

            if (

                context.signal == "BUY"

                and context.rsi14 > 75

            ):

                confidence -= 10.0

            elif (

                context.signal == "SELL"

                and context.rsi14 < 25

            ):

                confidence -= 10.0

        return self._clamp(

            confidence,

            0.0,

            self.config.max_confidence,

        )

    def _wait_reason(

        self,

        context: TechnicalContext,

        regime: str,

        setup: str,

        confluence: int,

        confidence: float,

    ) -> str:

        """Explain why the AI chose WAIT."""

        reasons = []

        if context.signal == "WAIT":

            reasons.append(

                "the technical signal is WAIT"

            )

        if context.trend == "Neutral":

            reasons.append(

                "the market trend is neutral"

            )

        if confidence < self.config.minimum_confidence:

            reasons.append(

                "AI confidence is below "

                "the minimum threshold"

            )

        if setup == "no_setup":

            reasons.append(

                "no valid trading setup was detected"

            )

        if confluence < self.config.minimum_confluence:

            reasons.append(

                "technical confluence is below "

                "the minimum threshold"

            )

        if (

            context.atr14 is None

            and context.signal in {"BUY", "SELL"}

        ):

            reasons.append(

                "ATR is unavailable for risk placement"

            )

        if not reasons:

            reasons.append(

                "directional conditions are not "

                "sufficiently aligned"

            )

        return "WAIT: " + "; ".join(reasons) + "."

    def _build_proposal(

        self,

        context: TechnicalContext,

        direction: AIDirection,

        confidence: float,

    ) -> tuple[

        Optional[AITradeProposal],

        Optional[str],

    ]:

        """

        Build a paper-only proposal.

        ATR is used for the initial stop distance.

        Minimum RR determines the target distance.

        """

        if context.atr14 is None:

            return (

                None,

                "WAIT: ATR is unavailable for risk placement.",

            )

        if context.atr14 <= 0:

            return (

                None,

                "WAIT: ATR must be greater than zero.",

            )

        entry = context.close

        if direction == AIDirection.BUY:

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

        elif direction == AIDirection.SELL:

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

        else:

            return (

                None,

                "WAIT: no trade direction available.",

            )

        if self.config.require_stop_loss:

            if stop_loss <= 0:

                return (

                    None,

                    "WAIT: calculated stop-loss is invalid.",

                )

        try:

            risk_reward = self._risk_reward(

                direction=direction,

                entry=entry,

                stop_loss=stop_loss,

                take_profit=take_profit,

            )

        except AIDecisionError as exc:

            return (

                None,

                f"WAIT: {exc}.",

            )

        if (

            risk_reward

            < self.config.minimum_risk_reward

        ):

            return (

                None,

                "WAIT: calculated risk/reward "

                "is below the minimum.",

            )

        pressure_text = ""

        if (

            context.market_pressure_available

            and context.market_pressure_score

            is not None

        ):

            pressure_text = (

                "; market pressure="

                f"{context.market_pressure_label}"

                f" ({context.market_pressure_score})"

            )

        proposal = AITradeProposal(

            direction=direction,

            symbol=context.symbol,

            entry_price=entry,

            stop_loss=stop_loss,

            take_profit=take_profit,

            risk_reward=risk_reward,

            confidence=confidence,

            reason=(

                f"{direction.name} setup confirmed by "

                f"technical confluence"

                f"{pressure_text}."

            ),

            execution_type="paper",

            read_only=True,

            broker_order_required=False,

            risk_engine_required=True,

        )

        return proposal, None

    def evaluate(

        self,

        context: TechnicalContext,

    ) -> AIDecision:

        """Evaluate the technical context."""

        context.validate()

        regime = self._market_regime(

            context

        )

        setup = self._setup_type(

            context,

            regime,

        )

        confluence = self._confluence_score(

            context

        )

        confidence = self._base_confidence(

            context,

            confluence,

        )

        direction = self._determine_direction(

            context,

            confluence,

        )

        pressure_fields = {

            "market_pressure_score":

                context.market_pressure_score,

            "market_pressure_label":

                context.market_pressure_label,

            "market_pressure_available":

                context.market_pressure_available,

        }

        # --------------------------------------------------------

        # WAIT: direction not confirmed

        # --------------------------------------------------------

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

                reasoning=self._wait_reason(

                    context,

                    regime,

                    setup,

                    confluence,

                    confidence,

                ),

                market_regime=regime,

                setup=setup,

                confluence_score=confluence,

                **pressure_fields,

            )

        # --------------------------------------------------------

        # WAIT: confidence too low

        # --------------------------------------------------------

        if (

            confidence

            < self.config.minimum_confidence

        ):

            return AIDecision(

                direction=AIDirection.WAIT,

                symbol=context.symbol,

                timeframe=context.timeframe,

                confidence=confidence,

                technical_score=context.score,

                trend=context.trend,

                signal=context.signal,

                proposal=None,

                reasoning=self._wait_reason(

                    context,

                    regime,

                    setup,

                    confluence,

                    confidence,

                ),

                market_regime=regime,

                setup=setup,

                confluence_score=confluence,

                **pressure_fields,

            )

        # --------------------------------------------------------

        # BUILD PAPER PROPOSAL

        # --------------------------------------------------------

        proposal, proposal_error = (

            self._build_proposal(

                context,

                direction,

                confidence,

            )

        )

        if proposal is None:

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

                    proposal_error

                    or self._wait_reason(

                        context,

                        regime,

                        setup,

                        confluence,

                        confidence,

                    )

                ),

                market_regime=regime,

                setup=setup,

                confluence_score=confluence,

                **pressure_fields,

            )

        # --------------------------------------------------------

        # FINAL PAPER DECISION

        # --------------------------------------------------------

        reasoning = (

            f"{direction.name}: "

            f"regime={regime}; "

            f"setup={setup}; "

            f"confluence={confluence}/100."

        )

        return AIDecision(

            direction=direction,

            symbol=context.symbol,

            timeframe=context.timeframe,

            confidence=confidence,

            technical_score=context.score,

            trend=context.trend,

            signal=context.signal,

            proposal=proposal,

            reasoning=reasoning,

            execution_type="paper",

            read_only=True,

            broker_order_required=False,

            risk_engine_required=True,

            market_regime=regime,

            setup=setup,

            confluence_score=confluence,

            **pressure_fields,

        )

def ai_decision_to_dict(

    decision: AIDecision,

) -> dict:

    """Serialize an AI decision safely."""

    proposal = None

    if decision.proposal is not None:

        p = decision.proposal

        proposal = {

            "direction": p.direction.value,

            "symbol": p.symbol,

            "entry_price": p.entry_price,

            "stop_loss": p.stop_loss,

            "take_profit": p.take_profit,

            "risk_reward": p.risk_reward,

            "confidence": p.confidence,

            "reason": p.reason,

            "execution_type": p.execution_type,

            "read_only": p.read_only,

            "broker_order_required":

                p.broker_order_required,

            "risk_engine_required":

                p.risk_engine_required,

        }

    return {

        "direction": decision.direction.value,

        "symbol": decision.symbol,

        "timeframe": decision.timeframe,

        "confidence": decision.confidence,

        "technical_score": decision.technical_score,

        "trend": decision.trend,

        "signal": decision.signal,

        "proposal": proposal,

        "reasoning": decision.reasoning,

        "execution_type": decision.execution_type,

        "read_only": decision.read_only,

        "broker_order_required":

            decision.broker_order_required,

        "risk_engine_required":

            decision.risk_engine_required,

        "market_regime":

            decision.market_regime,

        "setup":

            decision.setup,

        "confluence_score":

            decision.confluence_score,

        # --------------------------------------------------------

        # MARKET PRESSURE OUTPUT

        # --------------------------------------------------------

        "market_pressure_score":

            decision.market_pressure_score,

        "market_pressure_label":

            decision.market_pressure_label,

        "market_pressure_available":

            decision.market_pressure_available,

    }
