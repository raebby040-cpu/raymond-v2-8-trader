#!/usr/bin/env python3
"""
RAYMOND v2.8 - Apply Stage 19 persistent paper-account fix.

Run from the repository root:

    python apply_stage19_main_fix.py

This script:
1. Reads backend/app/main.py.
2. Adds the persistent paper-account/risk imports.
3. Replaces the in-memory paper-risk/equity helpers with persistent versions.
4. Refuses to modify the file if the expected old blocks are not found exactly.
5. Creates backend/app/main.py.stage19-backup before changing anything.
"""

from pathlib import Path
import shutil

MAIN = Path("backend/app/main.py")
BACKUP = Path("backend/app/main.py.stage19-backup")

if not MAIN.exists():
    raise SystemExit("ERROR: backend/app/main.py was not found. Run this from the repository root.")

text = MAIN.read_text(encoding="utf-8")

IMPORT_OLD = """    from .position_repository import PositionRepository
except ImportError:
    from database import SessionLocal
    from database_migration import run_database_migrations
    from demo_trading import DemoTrade
    from journal import TradeJournal
    from position_repository import PositionRepository"""

IMPORT_NEW = """    from .position_repository import PositionRepository
    from .persistent_paper_account import get_persistent_paper_equity
    from .persistent_paper_risk import build_persistent_paper_risk_state
except ImportError:
    from database import SessionLocal
    from database_migration import run_database_migrations
    from demo_trading import DemoTrade
    from journal import TradeJournal
    from position_repository import PositionRepository
    from persistent_paper_account import get_persistent_paper_equity
    from persistent_paper_risk import build_persistent_paper_risk_state"""

if IMPORT_OLD not in text:
    raise SystemExit("ERROR: Expected database import block was not found. No changes were made.")

RISK_START = "def build_paper_risk_state() -> PaperRiskState:"
RISK_END = "\n\n# ============================================================\n# MT5 SYMBOL SPECIFICATION"

start = text.find(RISK_START)
end = text.find(RISK_END, start)

if start < 0 or end < 0:
    raise SystemExit("ERROR: Expected paper risk/equity block was not found. No changes were made.")

new_risk_block = """def build_paper_risk_state() -> PaperRiskState:
    \"\"\"
    Build the authoritative paper risk state from persisted
    positions and closed-position P&L.

    The in-memory DemoTradingEngine is deliberately excluded
    from risk enforcement so Render restarts cannot reset the
    persistent risk limits.
    \"\"\"
    try:
        return build_persistent_paper_risk_state()
    except TradingPipelineServiceError:
        raise
    except Exception as exc:
        raise TradingPipelineServiceError(
            f"Unable to build persistent paper risk state: {exc}"
        ) from exc


def get_paper_equity() -> float:
    \"\"\"
    Return the authoritative persistent paper equity.

    Stage 19 removes the in-memory demo-account balance from
    the production paper-trading equity source of truth.
    \"\"\"
    try:
        return get_persistent_paper_equity()
    except Exception as exc:
        raise TradingPipelineServiceError(
            f"Unable to determine persistent paper equity: {exc}"
        ) from exc
"""

updated = text.replace(IMPORT_OLD, IMPORT_NEW, 1)
updated = updated[:start] + new_risk_block + updated[end:]

if updated == text:
    raise SystemExit("ERROR: No changes were produced. No file was modified.")

if BACKUP.exists():
    BACKUP.unlink()

shutil.copy2(MAIN, BACKUP)
MAIN.write_text(updated, encoding="utf-8")

print("SUCCESS")
print(f"Updated: {MAIN}")
print(f"Backup:  {BACKUP}")
print("Stage 19 now uses persistent paper account equity and persistent paper risk state.")
