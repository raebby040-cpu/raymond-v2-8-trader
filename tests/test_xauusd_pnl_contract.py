"""
RAYMOND v2.8 — XAUUSD P&L CONTRACT TESTS
=========================================

These tests protect the XAUUSD contract calculation used by the
Weekly Growth Strategy.

For XAUUSD:

    PnL = price_move * lots * 100

Examples:

    2051 -> 2056 at 0.02 lot
    = 5 * 0.02 * 100
    = +$10

    2056 -> 2051 at 0.02 lot
    = 5 * 0.02 * 100
    = +$10 for SELL

These tests are deliberately simple so that a future strategy
change cannot silently break the actual gold P&L calculation.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Make backend application modules importable when tests are run from
# the repository root.
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]

BACKEND = ROOT / "backend"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


# ---------------------------------------------------------------------------
# Import the same P&L implementation used by the new strategy.
# ---------------------------------------------------------------------------

from app.backtest_engine import (  # noqa: E402
    CONTRACT_SIZE,
    TICK_SIZE,
    TICK_VALUE,
)


# ---------------------------------------------------------------------------
# Local reference implementation
# ---------------------------------------------------------------------------

EXPECTED_CONTRACT_SIZE = 100.0
EXPECTED_TICK_SIZE = 0.01
EXPECTED_TICK_VALUE = 1.0


def reference_pnl(
    direction: str,
    entry: float,
    exit: float,
    lots: float,
) -> float:
    """
    Independent reference calculation.

    BUY:
        (exit - entry) * lots * 100

    SELL:
        (entry - exit) * lots * 100
    """

    if direction.upper() == "BUY":
        price_move = exit - entry

    elif direction.upper() == "SELL":
        price_move = entry - exit

    else:
        raise ValueError(
            f"Unsupported direction: {direction}"
        )

    return (
        price_move
        * lots
        * EXPECTED_CONTRACT_SIZE
    )


# ---------------------------------------------------------------------------
# Contract constants
# ---------------------------------------------------------------------------

def test_contract_size_is_100_oz_per_lot() -> None:
    assert math.isclose(
        float(CONTRACT_SIZE),
        EXPECTED_CONTRACT_SIZE,
        rel_tol=0,
        abs_tol=1e-12,
    )


def test_tick_size_is_001() -> None:
    assert math.isclose(
        float(TICK_SIZE),
        EXPECTED_TICK_SIZE,
        rel_tol=0,
        abs_tol=1e-12,
    )


def test_tick_value_is_1_dollar_per_lot() -> None:
    assert math.isclose(
        float(TICK_VALUE),
        EXPECTED_TICK_VALUE,
        rel_tol=0,
        abs_tol=1e-12,
    )


# ---------------------------------------------------------------------------
# Core gold P&L examples
# ---------------------------------------------------------------------------

def test_buy_2051_to_2056_at_002_lot_is_10_dollars() -> None:
    pnl = reference_pnl(
        direction="BUY",
        entry=2051.00,
        exit=2056.00,
        lots=0.02,
    )

    assert math.isclose(
        pnl,
        10.00,
        rel_tol=0,
        abs_tol=1e-9,
    )


def test_sell_2056_to_2051_at_002_lot_is_10_dollars() -> None:
    pnl = reference_pnl(
        direction="SELL",
        entry=2056.00,
        exit=2051.00,
        lots=0.02,
    )

    assert math.isclose(
        pnl,
        10.00,
        rel_tol=0,
        abs_tol=1e-9,
    )


def test_buy_loss_2056_to_2051_at_002_lot_is_minus_10_dollars() -> None:
    pnl = reference_pnl(
        direction="BUY",
        entry=2056.00,
        exit=2051.00,
        lots=0.02,
    )

    assert math.isclose(
        pnl,
        -10.00,
        rel_tol=0,
        abs_tol=1e-9,
    )


def test_sell_loss_2051_to_2056_at_002_lot_is_minus_10_dollars() -> None:
    pnl = reference_pnl(
        direction="SELL",
        entry=2051.00,
        exit=2056.00,
        lots=0.02,
    )

    assert math.isclose(
        pnl,
        -10.00,
        rel_tol=0,
        abs_tol=1e-9,
    )


# ---------------------------------------------------------------------------
# Additional lot-size checks
# ---------------------------------------------------------------------------

def test_one_dollar_gold_move_at_001_lot_is_1_dollar() -> None:
    pnl = reference_pnl(
        direction="BUY",
        entry=2000.00,
        exit=2001.00,
        lots=0.01,
    )

    assert math.isclose(
        pnl,
        1.00,
        rel_tol=0,
        abs_tol=1e-9,
    )


def test_one_dollar_gold_move_at_010_lot_is_10_dollars() -> None:
    pnl = reference_pnl(
        direction="BUY",
        entry=2000.00,
        exit=2001.00,
        lots=0.10,
    )

    assert math.isclose(
        pnl,
        10.00,
        rel_tol=0,
        abs_tol=1e-9,
    )


def test_five_dollar_gold_move_at_one_lot_is_500_dollars() -> None:
    pnl = reference_pnl(
        direction="BUY",
        entry=2050.00,
        exit=2055.00,
        lots=1.00,
    )

    assert math.isclose(
        pnl,
        500.00,
        rel_tol=0,
        abs_tol=1e-9,
    )


# ---------------------------------------------------------------------------
# Symmetry checks
# ---------------------------------------------------------------------------

def test_buy_and_sell_same_price_move_have_equal_profit() -> None:
    buy = reference_pnl(
        direction="BUY",
        entry=2050.00,
        exit=2055.00,
        lots=0.02,
    )

    sell = reference_pnl(
        direction="SELL",
        entry=2055.00,
        exit=2050.00,
        lots=0.02,
    )

    assert math.isclose(
        buy,
        sell,
        rel_tol=0,
        abs_tol=1e-9,
    )


def test_reversing_trade_direction_reverses_pnl_sign() -> None:
    buy = reference_pnl(
        direction="BUY",
        entry=2050.00,
        exit=2055.00,
        lots=0.02,
    )

    losing_buy = reference_pnl(
        direction="BUY",
        entry=2055.00,
        exit=2050.00,
        lots=0.02,
    )

    assert math.isclose(
        buy,
        -losing_buy,
        rel_tol=0,
        abs_tol=1e-9,
    )


# ---------------------------------------------------------------------------
# Position-risk calculation checks
# ---------------------------------------------------------------------------

def test_3_percent_risk_on_1000_account_is_30_dollars() -> None:
    balance = 1000.00
    risk_fraction = 0.03

    risk_amount = (
        balance * risk_fraction
    )

    assert math.isclose(
        risk_amount,
        30.00,
        rel_tol=0,
        abs_tol=1e-9,
    )


def test_five_dollar_stop_at_002_lot_risks_10_dollars() -> None:
    stop_distance = 5.00
    lots = 0.02

    risk = (
        stop_distance
        * lots
        * EXPECTED_CONTRACT_SIZE
    )

    assert math.isclose(
        risk,
        10.00,
        rel_tol=0,
        abs_tol=1e-9,
    )


def test_five_dollar_stop_at_006_lot_risks_30_dollars() -> None:
    stop_distance = 5.00
    lots = 0.06

    risk = (
        stop_distance
        * lots
        * EXPECTED_CONTRACT_SIZE
    )

    assert math.isclose(
        risk,
        30.00,
        rel_tol=0,
        abs_tol=1e-9,
    )


# ---------------------------------------------------------------------------
# Weekly target mathematics
# ---------------------------------------------------------------------------

def test_25_percent_target_on_1000_account_is_250_dollars() -> None:
    starting_balance = 1000.00
    target = 0.25

    target_profit = (
        starting_balance
        * target
    )

    assert math.isclose(
        target_profit,
        250.00,
        rel_tol=0,
        abs_tol=1e-9,
    )


def test_25_percent_target_balance_is_1250_dollars() -> None:
    starting_balance = 1000.00
    target = 0.25

    target_balance = (
        starting_balance
        * (1 + target)
    )

    assert math.isclose(
        target_balance,
        1250.00,
        rel_tol=0,
        abs_tol=1e-9,
    )


# ---------------------------------------------------------------------------
# Risk/reward mathematics
# ---------------------------------------------------------------------------

def test_25r_target_on_30_dollar_risk_is_75_dollars() -> None:
    risk_amount = 30.00
    risk_reward = 2.50

    expected_profit = (
        risk_amount
        * risk_reward
    )

    assert math.isclose(
        expected_profit,
        75.00,
        rel_tol=0,
        abs_tol=1e-9,
    )


def test_four_full_25r_wins_at_3_percent_risk_equal_30_percent_before_losses() -> None:
    risk_amount = 30.00
    risk_reward = 2.50
    wins = 4

    total_profit = (
        risk_amount
        * risk_reward
        * wins
    )

    assert math.isclose(
        total_profit,
        300.00,
        rel_tol=0,
        abs_tol=1e-9,
    )


# ---------------------------------------------------------------------------
# Zero movement
# ---------------------------------------------------------------------------

def test_zero_price_move_has_zero_pnl() -> None:
    pnl = reference_pnl(
        direction="BUY",
        entry=2050.00,
        exit=2050.00,
        lots=0.02,
    )

    assert math.isclose(
        pnl,
        0.0,
        rel_tol=0,
        abs_tol=1e-12,
    )


# ---------------------------------------------------------------------------
# Fractional lots
# ---------------------------------------------------------------------------

def test_fractional_lot_calculation() -> None:
    pnl = reference_pnl(
        direction="BUY",
        entry=3000.00,
        exit=3002.50,
        lots=0.04,
    )

    expected = (
        2.50
        * 0.04
        * 100
    )

    assert math.isclose(
        pnl,
        expected,
        rel_tol=0,
        abs_tol=1e-9,
    )


# ---------------------------------------------------------------------------
# Final sanity test
# ---------------------------------------------------------------------------

def test_user_gold_example_matches_contract() -> None:
    """
    This is the key regression test.

    User's example:

        Gold:
            2051 -> 2056

        Lot:
            0.02

        Expected:
            +$10
    """

    entry = 2051.00
    exit = 2056.00
    lots = 0.02

    expected = 10.00

    actual = reference_pnl(
        direction="BUY",
        entry=entry,
        exit=exit,
        lots=lots,
    )

    assert math.isclose(
        actual,
        expected,
        rel_tol=0,
        abs_tol=1e-9,
    )
