"""
RAYMOND v2.8 - Lifecycle-Aware Paper Position Market Loop

Stage 17.4.3
Integrates automatic TP/SL lifecycle processing into the existing
30-second public-market paper-position loop.

SAFETY
------
Paper only. No broker, MT5, Exness, or live execution is possible.
"""

from __future__ import annotations

from typing import Any, Optional

try:
    from .paper_position_lifecycle import PaperPositionLifecycle
    from .paper_position_market_loop import (
        PaperPositionMarketLoop,
        PaperPositionMarketLoopConfig,
        PaperPositionMarketLoopResult,
        PriceProvider,
        _utc,
        _validate_price,
    )
except ImportError:
    from paper_position_lifecycle import PaperPositionLifecycle
    from paper_position_market_loop import (
        PaperPositionMarketLoop,
        PaperPositionMarketLoopConfig,
        PaperPositionMarketLoopResult,
        PriceProvider,
        _utc,
        _validate_price,
    )


class LifecycleAwarePaperPositionMarketLoop(PaperPositionMarketLoop):
    """
    Existing paper-position management loop plus automatic TP/SL closure.

    Lifecycle processing happens first. Positions closed by SL/TP are
    therefore removed from the set of open positions before the advanced
    management engine evaluates break-even, trailing, or partial-close
    actions.
    """

    def __init__(
        self,
        db,
        price_provider: PriceProvider,
        config: Optional[PaperPositionMarketLoopConfig] = None,
        manager=None,
        lifecycle: Optional[PaperPositionLifecycle] = None,
    ) -> None:
        super().__init__(
            db=db,
            price_provider=price_provider,
            config=config,
            manager=manager,
        )

        self.lifecycle = (
            lifecycle
            if lifecycle is not None
            else PaperPositionLifecycle(db)
        )

    def evaluate_price(
        self,
        current_price: float,
    ) -> PaperPositionMarketLoopResult:
        price = _validate_price(current_price)

        try:
            # --------------------------------------------------------
            # STAGE 17.4
            # FIRST: detect automatic SL/TP closure.
            # --------------------------------------------------------

            lifecycle_results = self.lifecycle.evaluate_symbol(
                self.config.symbol,
                price,
            )

            # --------------------------------------------------------
            # STAGE 17.1
            # SECOND: manage positions that are still open.
            # --------------------------------------------------------

            management_results = self.manager.evaluate_symbol(
                self.config.symbol,
                price,
            )

            serialized_results: list[dict[str, Any]] = []

            for result in lifecycle_results:
                payload = result.to_dict()
                payload["phase"] = "lifecycle"
                serialized_results.append(payload)

            for result in management_results:
                payload = result.to_dict()
                payload["phase"] = "management"
                serialized_results.append(payload)

            result = PaperPositionMarketLoopResult(
                symbol=self.config.symbol,
                current_price=price,
                count=len(serialized_results),
                results=tuple(serialized_results),
                timestamp=_utc(),
            )

            self._last_result = result
            self._last_error = None

            return result

        except Exception as exc:
            self._last_error = str(exc)

            raise


__all__ = [
    "LifecycleAwarePaperPositionMarketLoop",
]
