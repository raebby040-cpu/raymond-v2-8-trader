import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(
    0,
    str(ROOT),
)

from scripts.research.run_intrabar_september_replay import (
    candle_event,
    valid_position,
)


def test_direction_validation():
    assert valid_position(
        "BUY",
        100,
        99,
        101,
    )

    assert valid_position(
        "SELL",
        100,
        101,
        99,
    )

    assert not valid_position(
        "BUY",
        100,
        101,
        102,
    )

    assert not valid_position(
        "SELL",
        100,
        99,
        98,
    )


def test_conservative_same_candle_rule():
    row = pd.Series(
        {
            "high": 105.0,
            "low": 95.0,
        }
    )

    assert candle_event(
        "BUY",
        row,
        99.0,
        101.0,
    ) == "STOP_LOSS"


def test_tp_detection_for_buy_and_sell():
    buy = pd.Series(
        {
            "high": 102.0,
            "low": 100.5,
        }
    )

    sell = pd.Series(
        {
            "high": 99.5,
            "low": 98.0,
        }
    )

    assert candle_event(
        "BUY",
        buy,
        99.0,
        101.0,
    ) == "TAKE_PROFIT"

    assert candle_event(
        "SELL",
        sell,
        101.0,
        99.0,
    ) == "TAKE_PROFIT"
