#!/usr/bin/env python3
"""
RAYMOND V2.8 — Safe position ownership patch.

Adds optional owner_user_id support to PositionRepository.create().
Does not change the trading strategy, risk rules, or broker execution.

Run from the backend directory:
    python ../scripts/patch_user_position_ownership.py

The script is idempotent and creates a backup before modifying the file.
"""

from __future__ import annotations

import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


def find_repository_root() -> Path:
    candidates = [
        Path.cwd(),
        Path(__file__).resolve().parent.parent,
    ]

    for candidate in candidates:
        if (
            candidate / "backend" / "app" / "position_repository.py"
        ).exists():
            return candidate

        if (
            candidate / "app" / "position_repository.py"
        ).exists():
            return candidate.parent

    raise FileNotFoundError(
        "Cannot find backend/app/position_repository.py. "
        "Run this script from the repository root."
    )


def main() -> int:
    root = find_repository_root()
    target = root / "backend" / "app" / "position_repository.py"

    if not target.exists():
        print(f"ERROR: File not found: {target}")
        return 1

    source = target.read_text(encoding="utf-8")

    signature_old = (
        '        management_status: str = "open",\n'
        "    ) -> Position:"
    )
    signature_new = (
        '        management_status: str = "open",\n'
        "        owner_user_id: Optional[str] = None,\n"
        "    ) -> Position:"
    )

    position_old = (
        "        position = Position(\n"
        "            position_id=position_id,\n"
        "            trade_id=trade_id,"
    )
    position_new = (
        "        position = Position(\n"
        "            position_id=position_id,\n"
        "            trade_id=trade_id,\n"
        "            owner_user_id=owner_user_id,"
    )

    signature_done = "owner_user_id: Optional[str] = None" in source
    assignment_done = "owner_user_id=owner_user_id" in source

    if signature_done and assignment_done:
        print("Already patched; no changes made.")
        return 0

    if signature_done != assignment_done:
        print(
            "ERROR: Partial patch detected. No changes made. "
            "Inspect position_repository.py before proceeding."
        )
        return 1

    if signature_old not in source:
        print(
            "ERROR: Expected create() signature not found. "
            "No changes made; source may have changed."
        )
        return 1

    if position_old not in source:
        print(
            "ERROR: Expected Position constructor not found. "
            "No changes made; source may have changed."
        )
        return 1

    updated = source.replace(signature_old, signature_new, 1)
    updated = updated.replace(position_old, position_new, 1)

    if (
        "owner_user_id: Optional[str] = None" not in updated
        or "owner_user_id=owner_user_id" not in updated
    ):
        print("ERROR: Validation failed; no changes written.")
        return 1

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = target.with_name(
        f"{target.name}.backup-{timestamp}"
    )
    shutil.copy2(target, backup)
    target.write_text(updated, encoding="utf-8")

    print("SUCCESS: Position ownership support added.")
    print(f"Updated: {target}")
    print(f"Backup:  {backup}")
    print(
        "IMPORTANT: Existing callers still need to pass the "
        "authenticated user's ID. Multi-user account isolation "
        "is not complete until creation, risk, P&L, management, "
        "and API paths are all user-scoped."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
