
"""
RAYMOND v2.8 - Database Migration Layer

Includes:
- Stage 16.2 persistent position state
- Stage 16.3 persistent trade thesis
- Stage 18 exact partial-close accounting
- Canonical trading state
- User ownership columns

Safety:
- Never drops tables.
- Never deletes existing rows.
- Adds only missing columns or tables.
- Existing historical ownership remains NULL.
- Safe to rerun when the database schema is unchanged.
"""

from sqlalchemy import inspect, text

try:
    from .database import Base, engine
except ImportError:
    from database import Base, engine


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


def get_table_columns(connection, table_name: str) -> set[str]:
    """Return existing column names, or an empty set if the table is absent."""
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
    """Add one missing column. Table and column names are internal constants."""
    if column_name in get_table_columns(connection, table_name):
        return False

    connection.execute(
        text(
            f"ALTER TABLE {table_name} "
            f"ADD COLUMN {column_name} {column_definition}"
        )
    )
    return True


def create_trade_id_index(connection) -> bool:
    """Create the existing unique linkage index if it is absent."""
    inspector = inspect(connection)

    if "positions" not in inspector.get_table_names():
        raise RuntimeError(
            "Cannot create the trade_id index: positions table is missing."
        )

    for index in inspector.get_indexes("positions"):
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


def migrate_stage_16_2() -> dict:
    added_columns = []
    skipped_columns = []
    created_indexes = []
    skipped_indexes = []

    with engine.begin() as connection:
        if "positions" not in inspect(connection).get_table_names():
            raise RuntimeError(
                "Stage 16.2 migration cannot run because "
                "the positions table does not exist."
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

            (added_columns if added else skipped_columns).append(
                column_name
            )

        try:
            created = create_trade_id_index(connection)
        except Exception as exc:
            raise RuntimeError(
                "Stage 16.2 could not create the unique trade_id index. "
                "Check for duplicate non-NULL trade_id values."
            ) from exc

        (
            created_indexes if created else skipped_indexes
        ).append("ix_positions_trade_id_unique")

    return {
        "migration": "stage_16_2",
        "status": "completed",
        "added_columns": added_columns,
        "skipped_existing_columns": skipped_columns,
        "created_indexes": created_indexes,
        "skipped_existing_indexes": skipped_indexes,
    }


def migrate_stage_16_3() -> dict:
    with engine.begin() as connection:
        if "positions" not in inspect(connection).get_table_names():
            raise RuntimeError(
                "Stage 16.3 migration cannot run because "
                "the positions table does not exist."
            )

        added = add_missing_column(
            connection,
            "positions",
            "trade_thesis",
            POSITION_COLUMNS["trade_thesis"],
        )

    return {
        "migration": "stage_16_3",
        "status": "completed",
        "added_columns": ["trade_thesis"] if added else [],
        "skipped_existing_columns": [] if added else ["trade_thesis"],
    }


def migrate_stage_18() -> dict:
    stage_18_columns = {
        name: POSITION_COLUMNS[name]
        for name in (
            "partial_close_price",
            "partial_close_quantity",
            "partial_close_pnl",
        )
    }
    added_columns = []
    skipped_columns = []

    with engine.begin() as connection:
        if "positions" not in inspect(connection).get_table_names():
            raise RuntimeError(
                "Stage 18 migration cannot run because "
                "the positions table does not exist."
            )

        for column_name, definition in stage_18_columns.items():
            added = add_missing_column(
                connection,
                "positions",
                column_name,
                definition,
            )
            (added_columns if added else skipped_columns).append(
                column_name
            )

    return {
        "migration": "stage_18",
        "status": "completed",
        "added_columns": added_columns,
        "skipped_existing_columns": skipped_columns,
    }


def migrate_canonical_trading_state() -> dict:
    """
    Create missing canonical state tables without altering existing tables.
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
        existing_tables = set(inspect(connection).get_table_names())

        for table in (
            CanonicalTradingPosition.__table__,
            TradingAccountSnapshot.__table__,
        ):
            if table.name not in existing_tables:
                table.create(bind=connection, checkfirst=True)
                created_tables.append(table.name)

    return {
        "migration": "canonical_trading_state",
        "status": "completed",
        "created_tables": created_tables,
        "existing_tables": [
            "canonical_trading_positions",
            "trading_account_snapshots",
        ],
    }


def migrate_user_ownership_columns() -> dict:
    """
    Add nullable ownership columns to existing trading tables.

    Existing rows remain NULL-owned. Do not assign them to a user unless
    a separate, verified reconciliation process establishes ownership.
    """
    target_tables = ("trades", "orders", "positions")
    added_columns = []
    skipped_columns = []
    skipped_tables = []

    with engine.begin() as connection:
        existing_tables = set(inspect(connection).get_table_names())

        for table_name in target_tables:
            if table_name not in existing_tables:
                skipped_tables.append(table_name)
                continue

            added = add_missing_column(
                connection,
                table_name,
                "owner_user_id",
                "VARCHAR(36)",
            )

            name = f"{table_name}.owner_user_id"
            (added_columns if added else skipped_columns).append(name)

    return {
        "migration": "user_ownership_columns",
        "status": "completed",
        "added_columns": added_columns,
        "skipped_existing_columns": skipped_columns,
        "skipped_missing_tables": skipped_tables,
    }


def run_database_migrations() -> dict:
    """Run required migrations in order."""
    results = [
        migrate_stage_16_2(),
        migrate_stage_16_3(),
        migrate_stage_18(),
        migrate_canonical_trading_state(),
        migrate_user_ownership_columns(),
    ]

    return {
        "status": "completed",
        "migrations": results,
    }


if __name__ == "__main__":
    result = run_database_migrations()

    print("RAYMOND v2.8 database migration completed.")
    print(f"Status: {result['status']}")

    for migration in result["migrations"]:
        print(f"\nMigration: {migration['migration']}")
        print(f"Status: {migration['status']}")

        for key, heading in (
            ("added_columns", "Added columns"),
            ("skipped_existing_columns", "Already existing columns"),
            ("created_indexes", "Created indexes"),
            ("skipped_existing_indexes", "Already existing indexes"),
            ("created_tables", "Created tables"),
            ("skipped_missing_tables", "Skipped missing tables"),
        ):
            values = migration.get(key, [])
            if values:
                print(f"{heading}:")
                for value in values:
                    print(f"  - {value}")
