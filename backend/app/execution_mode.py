"""
RAYMOND v2.8 - Unified Execution Mode

DEMO and LIVE share the same execution architecture.

Safety:
- DEMO can only execute on an identified demo account.
- LIVE requires the existing independent live safety system.
- Unknown modes fail closed.
"""

from __future__ import annotations

from enum import Enum


class ExecutionMode(str, Enum):
    DEMO = "demo"
    LIVE = "live"


def normalize_execution_mode(
    value: str | ExecutionMode,
) -> ExecutionMode:
    if isinstance(
        value,
        ExecutionMode,
    ):
        return value

    normalized = str(
        value
    ).strip().lower()

    if normalized == ExecutionMode.DEMO.value:
        return ExecutionMode.DEMO

    if normalized == ExecutionMode.LIVE.value:
        return ExecutionMode.LIVE

    raise ValueError(
        "Execution mode must be 'demo' or 'live'."
    )


def is_demo(
    value: str | ExecutionMode,
) -> bool:
    return (
        normalize_execution_mode(value)
        is ExecutionMode.DEMO
    )


def is_live(
    value: str | ExecutionMode,
) -> bool:
    return (
        normalize_execution_mode(value)
        is ExecutionMode.LIVE
    )


__all__ = [
    "ExecutionMode",
    "normalize_execution_mode",
    "is_demo",
    "is_live",
]
