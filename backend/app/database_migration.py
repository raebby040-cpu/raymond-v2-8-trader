"""
RAYMOND v2.8 - Database Migration Layer

Stage 16.2
Persistent Position State

Stage 16.3
Persistent Trade Thesis

Stage 18
Exact Partial-Close Accounting

Batch 1
Canonical Trading State

This module performs small, idempotent schema upgrades.

IMPORTANT:
- Never drops existing tables.
- Never deletes existing rows.
- Safe to run more than once.
- Adds only missing columns/tables.
- Preserves all existing trading data.
"""

from sqlalchemy import inspect, text

try:
    from .database import Base, engine
except ImportError:
    from database import Base, engine


# ============================================================
# EXISTING POSITION COLUMNS
# ============================================================

POSITION_COLUMNS = {
    "trade_id": "VARCHAR",
    "original_quantity": "FLOAT",
    "initial_stop_loss": "FLOAT",
    "take_profit_1": "FLOAT",
    "take_profit_2": "FLOAT",
    "risk_1r": "FLOAT",
    "current_price": "FLOAT",
    "current_stop_loss": "FLOAT",
    "remaining_quantity": "FLOAT",
    "stop_loss": "FLOAT",
    "take_profit": "FLOAT",
    "pnl": "FLOAT",
    "pnl_percent": "FLOAT",
    "regime": "VARCHAR",
    "setup": "VARCHAR",
    "technical_score": "FLOAT",
    "confluence": "FLOAT",
    "confidence": "FLOAT",
    "trade_thesis": "VARCHAR",
    "break_even_applied": "INTEGER DEFAULT 0",
    "partial_close_applied": "INTEGER DEFAULT 0",
    "trailing_active": "INTEGER DEFAULT 0",
    "management_status": "VARCHAR DEFAULT 'open'",
    "last_management_action": "VARCHAR",
    "last_management_time": "DATETIME",
    "max_drawdown": "FLOAT DEFAULT 0",
    "max_profit": "FLOAT DEFAULT 0",
    "partial_close_price": "FLOAT",
    "partial_close_quantity": "FLOAT",
    "partial_close_pnl": "FLOAT",
}


# ============================================================
# HELPERS
# ============================================================

def get_table_columns(
    connection,
    table_name: str,
) -> set[str]:
    inspector = inspect(connection)

    if table_name not in inspector.get_table_names():
        return set()

    return {
        column["name"]
        for column in inspector.get_columns(
            table_name
        )
    }


def add_missing_column(
    connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> bool:
    existing_columns = get_table_columns(
        connection,
        table_name,
    )

    if column_name in existing_columns:
        return False

    sql = (
        f"ALTER TABLE {table_name} "
        f"ADD COLUMN {column_name} "
        f"{column_definition}"
    )

    connection.execute(text(sql))

    return True


def create_trade_id_index(
    connection,
) -> bool:
    inspector = inspect(connection)

    existing_indexes = inspector.get_indexes(
        "positions"
    )

    for index in existing_indexes:
        if index.get(
            "name"
        ) == "ix_positions_trade_id_unique":
            return False

    connection.execute(
        text(
            """
            CREATE UNIQUE INDEX ix_positions_trade_id_unique
            ON positions (trade_id)
            """
        )
    )

    return True


# ============================================================
# STAGE 16.2
# ============================================================

def migrate_stage_16_2() -> dict:
    added_columns = []
    skipped_columns = []
    created_indexes = []
    skipped_indexes = []

    with engine.begin() as connection:
        inspector = inspect(connection)

        if "positions" not in inspector.get_table_names():
            raise RuntimeError(
                "Stage 16.2 migration cannot run because "
                "the 'positions' table does not exist."
            )

        for column_name, column_definition in POSITION_COLUMNS.items():

            if column_name == "trade_thesis":
                continue

            if column_name in {
                "partial_close_price",
                "partial_close_quantity",
                "partial_close_pnl",
            }:
                continue

            added = add_missing_column(
                connection,
                "positions",
                column_name,
                column_definition,
            )

            if added:
                added_columns.append(column_name)
            else:
                skipped_columns.append(column_name)

        try:
            created = create_trade_id_index(
                connection
            )

            if created:
                created_indexes.append(
                    "ix_positions_trade_id_unique"
                )
            else:
                skipped_indexes.append(
                    "ix_positions_trade_id_unique"
                )

        except Exception as exc:
            raise RuntimeError(
                "Stage 16.2 could not create the unique "
                "trade_id index. Existing duplicate non-NULL "
                "trade_id values may be present."
            ) from exc

    return {
        "migration": "stage_16_2",
        "status": "completed",
        "added_columns": added_columns,
        "skipped_existing_columns": skipped_columns,
        "created_indexes": created_indexes,
        "skipped_existing_indexes": skipped_indexes,
    }


# ============================================================
# STAGE 16.3
# ============================================================

def migrate_stage_16_3() -> dict:
    added_columns = []
    skipped_columns = []

    with engine.begin() as connection:
        inspector = inspect(connection)

        if "positions" not in inspector.get_table_names():
            raise RuntimeError(
                "Stage 16.3 migration cannot run because "
                "the 'positions' table does not exist."
            )

        added = add_missing_column(
            connection,
            "positions",
            "trade_thesis",
            POSITION_COLUMNS["trade_thesis"],
        )

        if added:
            added_columns.append(
                "trade_thesis"
            )
        else:
            skipped_columns.append(
                "trade_thesis"
            )

    return {
        "migration": "stage_16_3",
        "status": "completed",
        "added_columns": added_columns,
        "skipped_existing_columns": skipped_columns,
    }


# ============================================================
# STAGE 18
# ============================================================

def migrate_stage_18() -> dict:
    added_columns = []
    skipped_columns = []

    stage_18_columns = {
        "partial_close_price": POSITION_COLUMNS[
            "partial_close_price"
        ],
        "partial_close_quantity": POSITION_COLUMNS[
            "partial_close_quantity"
        ],
        "partial_close_pnl": POSITION_COLUMNS[
            "partial_close_pnl"
        ],
    }

    with engine.begin() as connection:
        inspector = inspect(connection)

        if "positions" not in inspector.get_table_names():
            raise RuntimeError(
                "Stage 18 migration cannot run because "
                "the 'positions' table does not exist."
            )

        for column_name, column_definition in (
            stage_18_columns.items()
        ):
            added = add_missing_column(
                connection,
                "positions",
                column_name,
                column_definition,
            )

            if added:
                added_columns.append(
                    column_name
                )
            else:
                skipped_columns.append(
                    column_name
                )

    return {
        "migration": "stage_18",
        "status": "completed",
        "added_columns": added_columns,
        "skipped_existing_columns": skipped_columns,
    }


# ============================================================
# BATCH 1 - CANONICAL TRADING STATE
# ============================================================

def migrate_canonical_trading_state() -> dict:
    """
    Create the canonical trading-state tables.

    The model definitions live in canonical_state.py.

    create_all() is deliberately used here because this migration
    only creates missing tables and never alters or deletes the
    existing tables.

    Future additive columns can receive their own migration.
    """

    try:
        from .canonical_state import (
            CanonicalTradingPosition,
            TradingAccountSnapshot,
        )
    except ImportError:
        from canonical_state import (
            CanonicalTradingPosition,
            TradingAccountSnapshot,
        )

    created_tables = []

    with engine.begin() as connection:
        inspector = inspect(connection)
        existing_tables = set(
            inspector.get_table_names()
        )

        target_tables = [
            CanonicalTradingPosition.__table__,
            TradingAccountSnapshot.__table__,
        ]

        for table in target_tables:
            if table.name not in existing_tables:
                table.create(
                    bind=connection,
                    checkfirst=True,
                )
                created_tables.append(
                    table.name
                )

    return {
        "migration": "canonical_trading_state",
        "status": "completed",
        "created_tables": created_tables,
        "existing_tables": [
            "canonical_trading_positions",
            "trading_account_snapshots",
        ],
    }


# ============================================================
# STARTUP
# ============================================================

def run_database_migrations() -> dict:
    """
    Run every currently required migration.

    Order:

        Stage 16.2
        Stage 16.3
        Stage 18
        Canonical Trading State
    """

    stage_16_2_result = migrate_stage_16_2()

    stage_16_3_result = migrate_stage_16_3()

    stage_18_result = migrate_stage_18()

    canonical_result = (
        migrate_canonical_trading_state()
    )

    return {
        "status": "completed",
        "migrations": [
            stage_16_2_result,
            stage_16_3_result,
            stage_18_result,
            canonical_result,
        ],
    }


# ============================================================
# COMMAND LINE
# ============================================================

if __name__ == "__main__":
    result = run_database_migrations()

    print(
        "RAYMOND v2.8 database migration completed."
    )

    print(
        f"Status: {result['status']}"
    )

    for migration in result["migrations"]:
        print(
            f"Migration: {migration['migration']}"
        )

        print(
            f"Status: {migration['status']}"
        )

        if migration.get("added_columns"):
            print("Added columns:")

            for column_name in migration[
                "added_columns"
            ]:
                print(
                    f"  + {column_name}"
                )

        if migration.get(
            "skipped_existing_columns"
        ):
            print(
                "Already existing columns:"
            )

            for column_name in migration[
                "skipped_existing_columns"
            ]:
                print(
                    f"  = {column_name}"
                )

        if migration.get("created_indexes"):
            print("Created indexes:")

            for index_name in migration[
                "created_indexes"
            ]:
                print(
                    f"  + {index_name}"
                )

        if migration.get(
            "skipped_existing_indexes"
        ):
            print(
                "Already existing indexes:"
            )

            for index_name in migration[
                "skipped_existing_indexes"
            ]:
                print(
                    f"  = {index_name}"
                )

        if migration.get("created_tables"):
            print("Created tables:")

            for table_name in migration[
                "created_tables"
            ]:
                print(
                    f"  + {table_name}"
)
