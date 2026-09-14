"""
RAYMOND v2.8 - Database Schema Migrations

Stage 16.2
Persistent Position State

This module performs small, idempotent schema upgrades for the
existing SQLAlchemy database.

IMPORTANT:
- Never drops existing tables.
- Never deletes existing rows.
- Safe to run more than once.
- Adds only missing columns/indexes required by Stage 16.2.
"""

from sqlalchemy import inspect, text

try:
    from .database import engine
except ImportError:
    from database import engine


# ============================================================
# STAGE 16.2 - REQUIRED POSITION COLUMNS
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
    "break_even_applied": "INTEGER DEFAULT 0",
    "partial_close_applied": "INTEGER DEFAULT 0",
    "trailing_active": "INTEGER DEFAULT 0",
    "management_status": "VARCHAR DEFAULT 'open'",
    "last_management_action": "VARCHAR",
    "last_management_time": "DATETIME",
    "max_drawdown": "FLOAT DEFAULT 0",
    "max_profit": "FLOAT DEFAULT 0",
}


# ============================================================
# HELPERS
# ============================================================

def get_table_columns(connection, table_name: str) -> set[str]:
    """
    Return the existing column names for a database table.

    If the table does not exist, return an empty set.
    """

    inspector = inspect(connection)

    if table_name not in inspector.get_table_names():
        return set()

    return {
        column["name"]
        for column in inspector.get_columns(table_name)
    }


def add_missing_column(
    connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> bool:
    """
    Add a column only when it does not already exist.

    Returns:
        True  -> column was added
        False -> column already existed
    """

    existing_columns = get_table_columns(
        connection,
        table_name,
    )

    if column_name in existing_columns:
        return False

    sql = (
        f"ALTER TABLE {table_name} "
        f"ADD COLUMN {column_name} {column_definition}"
    )

    connection.execute(text(sql))

    return True


def create_trade_id_index(connection) -> bool:
    """
    Create the unique trade_id index required by Stage 16.2.

    The index prevents the same paper execution order from
    creating duplicate persistent positions.

    Returns:
        True  -> index was created
        False -> index already existed
    """

    inspector = inspect(connection)

    existing_indexes = inspector.get_indexes(
        "positions"
    )

    for index in existing_indexes:
        if index.get("name") == "ix_positions_trade_id_unique":
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
# STAGE 16.2 MIGRATION
# ============================================================

def migrate_stage_16_2() -> dict:
    """
    Apply the Stage 16.2 persistent-position schema upgrade.

    This migration is intentionally idempotent:
    running it multiple times produces the same final schema.

    It never:
    - drops tables
    - deletes rows
    - overwrites existing column data
    """

    added_columns = []
    skipped_columns = []

    created_indexes = []
    skipped_indexes = []

    with engine.begin() as connection:
        inspector = inspect(connection)

        table_names = inspector.get_table_names()

        # ----------------------------------------------------
        # POSITIONS TABLE MUST EXIST
        # ----------------------------------------------------

        if "positions" not in table_names:
            raise RuntimeError(
                "Stage 16.2 migration cannot run because the "
                "'positions' table does not exist. "
                "Create the SQLAlchemy tables before running "
                "the migration."
            )

        # ----------------------------------------------------
        # ADD MISSING POSITION COLUMNS
        # ----------------------------------------------------

        for column_name, column_definition in POSITION_COLUMNS.items():

            added = add_missing_column(
                connection=connection,
                table_name="positions",
                column_name=column_name,
                column_definition=column_definition,
            )

            if added:
                added_columns.append(column_name)
            else:
                skipped_columns.append(column_name)

        # ----------------------------------------------------
        # UNIQUE TRADE ID INDEX
        # ----------------------------------------------------

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
                "trade_id values may be present in the "
                "positions table."
            ) from exc

    # --------------------------------------------------------
    # MIGRATION RESULT
    # --------------------------------------------------------

    return {
        "migration": "stage_16_2",
        "status": "completed",
        "added_columns": added_columns,
        "skipped_existing_columns": skipped_columns,
        "created_indexes": created_indexes,
        "skipped_existing_indexes": skipped_indexes,
    }


# ============================================================
# PUBLIC MIGRATION ENTRY POINT
# ============================================================

def run_database_migrations() -> dict:
    """
    Run all currently registered database migrations.

    Stage 16.2 is currently the active migration.
    """

    return migrate_stage_16_2()


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":

    result = run_database_migrations()

    print(
        "RAYMOND v2.8 database migration completed."
    )

    print(
        f"Migration: {result['migration']}"
    )

    print(
        f"Status: {result['status']}"
    )

    if result["added_columns"]:

        print("Added columns:")

        for column_name in result["added_columns"]:
            print(
                f"  + {column_name}"
            )

    else:

        print(
            "No new columns were required."
        )

    if result["created_indexes"]:

        print("Created indexes:")

        for index_name in result["created_indexes"]:
            print(
                f"  + {index_name}"
            )

    else:

        print(
            "No new indexes were required."
        )
