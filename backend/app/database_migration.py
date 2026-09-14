"""
RAYMOND v2.8 - Database Migration Layer

Purpose
-------
Provides explicit, idempotent database schema upgrades for the
RAYMOND trading system.

Stage 16.2
----------
Adds persistent Position state required for restart recovery.

Stage 16.3
----------
Adds persistent trade thesis storage to the Position table.

Safety
------
- Existing data is preserved.
- Existing columns are never overwritten.
- Missing columns are added individually.
- Migrations are idempotent.
- Migration failures are not silently ignored.
- Application startup should fail if the required schema cannot
  be upgraded successfully.
"""

from sqlalchemy import inspect, text

try:
    from .database import engine
    from .models import create_tables
except ImportError:
    from database import engine
    from models import create_tables


# -------------------------------------------------------------------
# POSITION SCHEMA
# -------------------------------------------------------------------

POSITION_COLUMNS = {
    # Stage 16.2 - persistent position identity
    "trade_id": "VARCHAR",

    # Original trade state
    "original_quantity": "FLOAT",
    "initial_stop_loss": "FLOAT",
    "take_profit_1": "FLOAT",
    "take_profit_2": "FLOAT",
    "risk_1r": "FLOAT",

    # Live position state
    "current_price": "FLOAT",
    "current_stop_loss": "FLOAT",
    "remaining_quantity": "FLOAT",
    "stop_loss": "FLOAT",
    "take_profit": "FLOAT",
    "pnl": "FLOAT",
    "pnl_percent": "FLOAT",

    # Entry thesis context
    "regime": "VARCHAR",
    "setup": "VARCHAR",
    "technical_score": "FLOAT",
    "confluence": "FLOAT",
    "confidence": "FLOAT",

    # Stage 16.3 - persistent trade thesis
    "trade_thesis": "VARCHAR",

    # Management state
    "break_even_applied": "INTEGER DEFAULT 0",
    "partial_close_applied": "INTEGER DEFAULT 0",
    "trailing_active": "INTEGER DEFAULT 0",
    "management_status": "VARCHAR DEFAULT 'open'",
    "last_management_action": "VARCHAR",
    "last_management_time": "DATETIME",

    # Performance tracking
    "max_drawdown": "FLOAT DEFAULT 0",
    "max_profit": "FLOAT DEFAULT 0",
}


# -------------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------------

def get_table_columns(connection, table_name):
    """
    Return the existing column names for a database table.
    """
    inspector = inspect(connection)

    if not inspector.has_table(table_name):
        return set()

    return {
        column["name"]
        for column in inspector.get_columns(table_name)
    }


def add_missing_column(
    connection,
    table_name,
    column_name,
    column_definition,
):
    """
    Add one database column if it does not already exist.

    Returns
    -------
    bool
        True when a column was added.
        False when it already existed.
    """

    existing_columns = get_table_columns(
        connection,
        table_name,
    )

    if column_name in existing_columns:
        return False

    statement = text(
        f"ALTER TABLE {table_name} "
        f"ADD COLUMN {column_name} {column_definition}"
    )

    connection.execute(statement)

    return True


def create_trade_id_index(connection):
    """
    Create the trade_id index when possible.

    The index is created only when trade_id exists.

    SQLite and PostgreSQL both support CREATE INDEX IF NOT EXISTS,
    which makes this operation safe to run repeatedly.
    """

    existing_columns = get_table_columns(
        connection,
        "positions",
    )

    if "trade_id" not in existing_columns:
        return False

    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS "
            "ix_positions_trade_id "
            "ON positions (trade_id)"
        )
    )

    return True


# -------------------------------------------------------------------
# STAGE 16.2
# -------------------------------------------------------------------

def migrate_stage_16_2(connection):
    """
    Upgrade the positions table for Stage 16.2.

    Stage 16.2 establishes persistent Position state so that
    open paper positions can survive application/database session
    restarts.

    The migration is intentionally additive.
    """

    if not inspect(connection).has_table("positions"):
        raise RuntimeError(
            "Stage 16.2 migration failed: "
            "'positions' table does not exist."
        )

    added_columns = []

    stage_16_2_columns = {
        name: definition
        for name, definition in POSITION_COLUMNS.items()
        if name != "trade_thesis"
    }

    for column_name, column_definition in stage_16_2_columns.items():
        if add_missing_column(
            connection,
            "positions",
            column_name,
            column_definition,
        ):
            added_columns.append(column_name)

    create_trade_id_index(connection)

    return {
        "stage": "16.2",
        "table": "positions",
        "added_columns": added_columns,
        "success": True,
    }


# -------------------------------------------------------------------
# STAGE 16.3
# -------------------------------------------------------------------

def migrate_stage_16_3(connection):
    """
    Upgrade the positions table for Stage 16.3.

    Stage 16.3 adds persistent trade thesis storage.

    The thesis belongs to the Position because the thesis is part
    of the original decision context that should remain available
    after a restart.

    This migration is additive and idempotent.
    """

    if not inspect(connection).has_table("positions"):
        raise RuntimeError(
            "Stage 16.3 migration failed: "
            "'positions' table does not exist."
        )

    added_columns = []

    if add_missing_column(
        connection,
        "positions",
        "trade_thesis",
        POSITION_COLUMNS["trade_thesis"],
    ):
        added_columns.append("trade_thesis")

    return {
        "stage": "16.3",
        "table": "positions",
        "added_columns": added_columns,
        "success": True,
    }


# -------------------------------------------------------------------
# MAIN MIGRATION ENTRY POINT
# -------------------------------------------------------------------

def run_database_migrations():
    """
    Run all required RAYMOND database migrations.

    Migrations are executed in stage order.

    A failure raises an exception so that application startup can
    fail closed rather than running against an incomplete schema.
    """

    # Ensure ORM-created tables exist before applying additive
    # schema migrations.
    create_tables()

    results = []

    with engine.begin() as connection:

        # -----------------------------------------------------------
        # Stage 16.2
        # -----------------------------------------------------------

        stage_16_2_result = migrate_stage_16_2(
            connection
        )

        results.append(
            stage_16_2_result
        )

        # -----------------------------------------------------------
        # Stage 16.3
        # -----------------------------------------------------------

        stage_16_3_result = migrate_stage_16_3(
            connection
        )

        results.append(
            stage_16_3_result
        )

    return {
        "success": True,
        "migrations": results,
    }


# -------------------------------------------------------------------
# DIRECT EXECUTION
# -------------------------------------------------------------------

if __name__ == "__main__":
    result = run_database_migrations()
    print(result)
