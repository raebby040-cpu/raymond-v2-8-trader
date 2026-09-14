"""
RAYMOND v2.8 - Database Migration Layer

Provides explicit, idempotent database schema upgrades.

Stage 16.2
-----------
Persistent Position State and restart recovery.

Stage 16.3
-----------
Persistent Trade Thesis.

Safety
------
- Existing data is preserved.
- Existing columns are never overwritten.
- Missing columns are added individually.
- Migrations are idempotent.
- Migration failures are not silently ignored.
- Application startup fails closed when schema migration fails.
"""

from sqlalchemy import inspect, text

try:
    from .database import engine
    from .models import create_tables
except ImportError:
    from database import engine
    from models import create_tables


# -------------------------------------------------------------------
# POSITION COLUMNS
# -------------------------------------------------------------------

POSITION_COLUMNS = {
    # Stage 16.2
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

    # Stage 16.3
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
    Add a column only when it does not already exist.

    Returns:
        True  - column was added
        False - column already existed
    """

    existing_columns = get_table_columns(
        connection,
        table_name,
    )

    if column_name in existing_columns:
        return False

    connection.execute(
        text(
            f"ALTER TABLE {table_name} "
            f"ADD COLUMN {column_name} {column_definition}"
        )
    )

    return True


def create_trade_id_index(connection):
    """
    Create the trade_id index when trade_id exists.

    The operation is idempotent.
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
# STAGE 16.2 INTERNAL IMPLEMENTATION
# -------------------------------------------------------------------

def _migrate_stage_16_2(connection):
    """
    Internal Stage 16.2 migration implementation.

    Adds all persistent Position State columns required by
    Stage 16.2.

    The return format intentionally preserves the original
    migration API expected by the existing test suite.
    """

    if not inspect(connection).has_table("positions"):
        raise RuntimeError(
            "Stage 16.2 migration failed: "
            "'positions' table does not exist."
        )

    added_columns = []

    for column_name, column_definition in POSITION_COLUMNS.items():

        # Stage 16.3 is handled separately.
        if column_name == "trade_thesis":
            continue

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
        "status": "completed",
        "success": True,
        "added_columns": added_columns,
    }


# -------------------------------------------------------------------
# STAGE 16.2 PUBLIC API
# -------------------------------------------------------------------

def migrate_stage_16_2(connection=None):
    """
    Public Stage 16.2 migration.

    Supports both:

        migrate_stage_16_2()

    and:

        migrate_stage_16_2(connection)

    This preserves compatibility with the existing test suite.
    """

    if connection is not None:
        return _migrate_stage_16_2(
            connection
        )

    create_tables()

    with engine.begin() as migration_connection:
        return _migrate_stage_16_2(
            migration_connection
        )


# -------------------------------------------------------------------
# STAGE 16.3 INTERNAL IMPLEMENTATION
# -------------------------------------------------------------------

def _migrate_stage_16_3(connection):
    """
    Internal Stage 16.3 migration implementation.

    Adds persistent trade_thesis storage to the positions table.
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
        "status": "completed",
        "success": True,
        "added_columns": added_columns,
    }


# -------------------------------------------------------------------
# STAGE 16.3 PUBLIC API
# -------------------------------------------------------------------

def migrate_stage_16_3(connection=None):
    """
    Public Stage 16.3 migration.

    Supports both:

        migrate_stage_16_3()

    and:

        migrate_stage_16_3(connection)
    """

    if connection is not None:
        return _migrate_stage_16_3(
            connection
        )

    create_tables()

    with engine.begin() as migration_connection:
        return _migrate_stage_16_3(
            migration_connection
        )


# -------------------------------------------------------------------
# MAIN MIGRATION ENTRY POINT
# -------------------------------------------------------------------

def run_database_migrations():
    """
    Run all required database migrations in stage order.

    Stage 16.2 is preserved exactly as the compatibility
    foundation.

    Stage 16.3 then adds the persistent trade thesis column.

    Any migration failure raises an exception.
    """

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
        "status": "completed",
        "success": True,
        "migrations": results,
    }


# -------------------------------------------------------------------
# DIRECT EXECUTION
# -------------------------------------------------------------------

if __name__ == "__main__":
    result = run_database_migrations()
    print(result)
