"""
Historical market-data adapter for RAYMOND v2.8 backtesting.

Uses a public, read-only XAUUSD historical OHLC archive.
No broker connection and no order execution are involved.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any

import httpx


class HistoricalDataError(RuntimeError):
    """Raised when historical market data cannot be loaded safely."""


_BASE = (
    "https://raw.githubusercontent.com/"
    "ejtraderLabs/historical-data/main/XAUUSD"
)

_FILES = {
    "M15": "XAUUSDm15.csv",
    "M30": "XAUUSDm30.csv",
    "H1": "XAUUSDh1.csv",
    "H4": "XAUUSDh4.csv",
    "D1": "XAUUSDd1.csv",
}


def _normalise_price(value: str) -> float:
    price = float(value)

    # The source archive stores XAUUSD prices with
    # two implied decimal places, e.g. 154759 = 1547.59.
    if price >= 10000:
        return price / 100.0

    return price


def _timestamp(value: str) -> int:
    parsed = datetime.strptime(
        value.strip(),
        "%Y-%m-%d %H:%M:%S",
    )

    return int(
        parsed.replace(
            tzinfo=timezone.utc
        ).timestamp()
    )


async def get_xauusd_candles(
    *,
    timeframe: str = "H1",
    limit: int = 50_000,
) -> list[dict[str, Any]]:
    """
    Download historical XAUUSD candles.

    Returned candles use the same basic OHLC/time structure
    required by the RAYMOND backtest engine.
    """

    tf = timeframe.strip().upper()

    filename = _FILES.get(tf)

    if filename is None:
        raise HistoricalDataError(
            "Historical XAUUSD feed supports: "
            + ", ".join(_FILES)
        )

    if limit < 1:
        raise HistoricalDataError(
            "limit must be greater than zero."
        )

    url = f"{_BASE}/{filename}"

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                30.0,
                connect=10.0,
            ),
            headers={
                "User-Agent": (
                    "RAYMOND-v2.8/"
                    "historical-backtest"
                ),
                "Accept": "text/csv",
            },
        ) as client:

            response = await client.get(url)

            response.raise_for_status()

    except httpx.HTTPError as exc:
        raise HistoricalDataError(
            "Unable to download historical "
            f"XAUUSD data: {exc}"
        ) from exc

    try:
        reader = csv.DictReader(
            io.StringIO(response.text)
        )

        candles: list[dict[str, Any]] = []

        for row in reader:
            candles.append(
                {
                    "time": _timestamp(
                        row["Date"]
                    ),
                    "open": _normalise_price(
                        row["open"]
                    ),
                    "high": _normalise_price(
                        row["high"]
                    ),
                    "low": _normalise_price(
                        row["low"]
                    ),
                    "close": _normalise_price(
                        row["close"]
                    ),
                    "volume": float(
                        row.get(
                            "tick_volume"
                        )
                        or 0
                    ),
                }
            )

    except (
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise HistoricalDataError(
            "Historical XAUUSD data could not "
            f"be parsed: {exc}"
        ) from exc

    candles.sort(
        key=lambda candle: candle["time"]
    )

    if len(candles) < 51:
        raise HistoricalDataError(
            "Historical XAUUSD feed returned only "
            f"{len(candles)} candles."
        )

    return candles[-limit:]
