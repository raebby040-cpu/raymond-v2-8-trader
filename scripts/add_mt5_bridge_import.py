
#!/usr/bin/env python3
"""Safely register the read-only MT5 Bridge in backend/app/main.py."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_FILE = ROOT / "backend" / "app" / "main.py"
HELPER_FILE = ROOT / "backend" / "app" / "mt5_bridge_integration.py"

IMPORT_BLOCK = """# ============================================================
# MT5 BRIDGE INTEGRATION
# ============================================================

try:
    from .mt5_bridge_integration import register_mt5_bridge
except ImportError:
    from mt5_bridge_integration import register_mt5_bridge
"""


def find_app_assignment(tree: ast.Module) -> ast.Assign:
    """Find the module-level app = FastAPI(...) assignment."""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue

        if not any(
            isinstance(target, ast.Name) and target.id == "app"
            for target in node.targets
        ):
            continue

        if (
            isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "FastAPI"
        ):
            return node

    raise SystemExit("ERROR: app = FastAPI(...) was not found.")


def has_import(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == "mt5_bridge_integration"
        and any(alias.name == "register_mt5_bridge" for alias in node.names)
        for node in ast.walk(tree)
    )


def has_registration(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "register_mt5_bridge"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "app"
        for node in ast.walk(tree)
    )


def main() -> None:
    if not MAIN_FILE.is_file():
        raise SystemExit(f"ERROR: Missing file: {MAIN_FILE}")

    if not HELPER_FILE.is_file():
        raise SystemExit(f"ERROR: Missing helper: {HELPER_FILE}")

    original = MAIN_FILE.read_text(encoding="utf-8")

    try:
        tree = ast.parse(original, filename=str(MAIN_FILE))
    except SyntaxError as exc:
        raise SystemExit(f"ERROR: main.py has a syntax error: {exc}") from exc

    updated = original
    changed = False

    # Add the import if it is missing.
    if not has_import(tree):
        app_assignment = find_app_assignment(tree)
        lines = updated.splitlines(keepends=True)
        lines.insert(app_assignment.lineno - 1, IMPORT_BLOCK + "\n")
        updated = "".join(lines)
        changed = True

    # Reparse before finding the registration insertion point.
    tree = ast.parse(updated, filename=str(MAIN_FILE))

    # Register immediately after app = FastAPI(...) if missing.
    if not has_registration(tree):
        app_assignment = find_app_assignment(tree)
        lines = updated.splitlines(keepends=True)
        lines.insert(
            app_assignment.end_lineno,
            "\n# Register the read-only MT5 Bridge API.\n"
            "register_mt5_bridge(app)\n",
        )
        updated = "".join(lines)
        changed = True

    # Never write an invalid result.
    final_tree = ast.parse(updated, filename=str(MAIN_FILE))

    if not has_import(final_tree):
        raise SystemExit("ERROR: Import validation failed.")
    if not has_registration(final_tree):
        raise SystemExit("ERROR: Registration validation failed.")

    if not changed:
        print("OK: Import and registration already exist; nothing changed.")
        return

    MAIN_FILE.write_text(updated, encoding="utf-8")
    print("SUCCESS: Updated backend/app/main.py.")
    print("SUCCESS: Python syntax and both integration checks passed.")
    print("Safety: This registers read-only endpoints only.")


if __name__ == "__main__":
    main()
