"""
RAYMOND v2.8 - Database Migration Layer

Stage 16.2
Persistent Position State

Stage 16.3
Persistent Trade Thesis

Stage 18
Exact Partial-Close Accounting

This module performs small, idempotent schema upgrades for the
existing SQLAlchemy database.

IMPORTANT:
- Never drops existing tables.
- Never deletes existing rows.
- Safe to run more than once.
- Adds only missing columns/indexes.
- Preserves the original Stage 16.2 migration contract.
"""

from sqlalchemy import inspect, text

try:
    from .database import engine
except ImportError:
    from database import engine


# ============================================================
# POSITION COLUMNS
# ============================================================

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

    # Stage 18 - exact partial-close accounting
    "partial_close_price": "FLOAT",
    "partial_close_quantity": "FLOAT",
    "partial_close_pnl": "FLOAT",
}


# ============================================================
# HELPERS
# ============================================================

def get_table_columns(connection, table_name: str) -> set[str]:
    """
    Return the existing column names for a table.
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
    Add one column if it does not already exist.

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
    Create the original Stage 16.2 unique trade_id index.

    The exact index name is part of the existing Stage 16.2
    contract and must not be changed.

    Multiple NULL trade_id values remain allowed by SQLite and
    PostgreSQL unique-index semantics.

    Returns:
        True  -> index was created
        False -> index already existed
    """

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
# STAGE 16.2 MIGRATION
# ============================================================

def migrate_stage_16_2() -> dict:
    """
    Apply the Stage 16.2 persistent-position schema upgrade.

    IMPORTANT:
    This public function intentionally keeps the original
    zero-argument signature.

    The migration is idempotent.

    Running it once:
        adds missing columns and the unique trade_id index.

    Running it again:
        detects that they already exist and does nothing.
    """

    added_columns = []
    skipped_columns = []
    created_indexes = []
    skipped_indexes = []

    with engine.begin() as connection:
        inspector = inspect(connection)

        table_names = inspector.get_table_names()

        # ----------------------------------------------------
        # POSITION TABLE MUST EXIST
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

            # Stage 16.3 is deliberately handled separately.
            if column_name == "trade_thesis":
                continue

            # Stage 18 is handled separately so that the
            # migration has its own explicit audit trail.
            if column_name in {
                "partial_close_price",
                "partial_close_quantity",
                "partial_close_pnl",
            }:
                continue

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
        # TRADE ID UNIQUE INDEX
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

    return {
        "migration": "stage_16_2",
        "status": "completed",
        "added_columns": added_columns,
        "skipped_existing_columns": skipped_columns,
        "created_indexes": created_indexes,
        "skipped_existing_indexes": skipped_indexes,
    }


# ============================================================
# STAGE 16.3 MIGRATION
# ============================================================

def migrate_stage_16_3() -> dict:
    """
    Apply the Stage 16.3 persistent trade-thesis schema upgrade.

    This migration adds exactly one new column:

        positions.trade_thesis

    The migration is idempotent.
    """

    added_columns = []
    skipped_columns = []

    with engine.begin() as connection:
        inspector = inspect(connection)

        table_names = inspector.get_table_names()

        # ----------------------------------------------------
        # POSITION TABLE MUST EXIST
        # ----------------------------------------------------

        if "positions" not in table_names:
            raise RuntimeError(
                "Stage 16.3 migration cannot run because the "
                "'positions' table does not exist."
            )

        # ----------------------------------------------------
        # ADD TRADE THESIS
        # ----------------------------------------------------

        added = add_missing_column(
            connection=connection,
            table_name="positions",
            column_name="trade_thesis",
            column_definition=POSITION_COLUMNS[
                "trade_thesis"
            ],
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
# STAGE 18 MIGRATION
# ============================================================

def migrate_stage_18() -> dict:
    """
    Apply the Stage 18 exact partial-close accounting schema.

    Adds three optional fields to the existing positions table:

        positions.partial_close_price
        positions.partial_close_quantity
        positions.partial_close_pnl

    These fields allow future partial closes to preserve the
    exact execution price, quantity closed, and realized P/L.

    IMPORTANT:
    This migration does NOT attempt to reconstruct historical
    partial-close values. Existing historical rows remain
    untouched and NULL in these fields when exact information
    was never persisted.

    The migration is idempotent.
    """

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

        table_names = inspector.get_table_names()

        # ----------------------------------------------------
        # POSITION TABLE MUST EXIST
        # ----------------------------------------------------

        if "positions" not in table_names:
            raise RuntimeError(
                "Stage 18 migration cannot run because the "
                "'positions' table does not exist."
            )

        # ----------------------------------------------------
        # ADD PARTIAL-CLOSE ACCOUNTING COLUMNS
        # ----------------------------------------------------

        for column_name, column_definition in stage_18_columns.items():

            added = add_missing_column(
                connection=connection,
                table_name="positions",
                column_name=column_name,
                column_definition=column_definition,
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
# STARTUP HELPER
# ============================================================

def run_database_migrations() -> dict:
    """
    Run all currently required database migrations.

    Order:

        Stage 16.2
        Stage 16.3
        Stage 18

    Each migration remains independently idempotent.
    """

    stage_16_2_result = migrate_stage_16_2()

    stage_16_3_result = migrate_stage_16_3()

    stage_18_result = migrate_stage_18()

    return {
        "status": "completed",
        "migrations": [
            stage_16_2_result,
            stage_16_3_result,
            stage_18_result,
        ],
    }


# ============================================================
# COMMAND-LINE EXECUTION
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

        if migration.get(
            "added_columns"
        ):
            print("Added columns:")

            for column in migration[
                "added_columns"
            ]:
                print(
                    f"  + {column}"
                )

        if migration.get(
            "skipped_existing_columns"
        ):
            print("Already existing columns:")

            for column in migration[
                "skipped_existing_columns"
            ]:
                print(
                    f"  = {column}"
                )

        if migration.get(
            "created_indexes"
        ):
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
            print("Already existing indexes:")

            for index_name in migration[
                "skipped_existing_indexes"
            ]:
                print(
                    f"  = {index_name}"
                )
