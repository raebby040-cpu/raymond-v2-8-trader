#!/usr/bin/env python3
"""
RAYMOND V2.8 — User Authentication Wiring Helper

Adds the user_auth router import and registration to backend/app/main.py.
Creates a backup before modifying the file.
Does not modify trading strategy, broker execution, or risk settings.
"""

from __future__ import annotations

import ast
import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path


IMPORT_BLOCK = '''# ============================================================
# USER AUTHENTICATION
# ============================================================

try:
    from .user_auth import router as user_auth_router
except ImportError:
    from user_auth import router as user_auth_router
'''

ROUTER_BLOCK = '''app.include_router(
    user_auth_router,
    tags=["User Authentication"],
)
'''


def parse_python(source: str, description: str) -> ast.Module:
    """Validate Python syntax and return its AST."""
    try:
        return ast.parse(source, filename=description)
    except SyntaxError as exc:
        raise RuntimeError(
            f"Python syntax validation failed in {description}: {exc}"
        ) from exc


def is_app_assignment(node: ast.stmt) -> bool:
    """Return True for a top-level assignment creating app."""
    if isinstance(node, ast.Assign):
        return any(
            isinstance(target, ast.Name) and target.id == "app"
            for target in node.targets
        )

    if isinstance(node, ast.AnnAssign):
        return (
            isinstance(node.target, ast.Name)
            and node.target.id == "app"
        )

    return False


def has_auth_import(tree: ast.Module) -> bool:
    """Check whether user_auth.router is imported as user_auth_router."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.endswith("user_auth"):
                for alias in node.names:
                    if (
                        alias.name == "router"
                        and alias.asname == "user_auth_router"
                    ):
                        return True
    return False


def is_auth_router_registration(node: ast.stmt) -> bool:
    """Identify app.include_router(user_auth_router, ...)."""
    if not isinstance(node, ast.Expr):
        return False

    call = node.value
    if not isinstance(call, ast.Call):
        return False

    func = call.func
    if not (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "app"
        and func.attr == "include_router"
    ):
        return False

    return bool(
        call.args
        and isinstance(call.args[0], ast.Name)
        and call.args[0].id == "user_auth_router"
    )


def is_demo_router_registration(node: ast.stmt) -> bool:
    """Find the demo router registration, when present."""
    if not isinstance(node, ast.Expr):
        return False

    call = node.value
    if not isinstance(call, ast.Call):
        return False

    func = call.func
    if not (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "app"
        and func.attr == "include_router"
    ):
        return False

    return bool(
        call.args
        and isinstance(call.args[0], ast.Name)
        and call.args[0].id == "demo_trading_router"
    )


def wire_authentication(target: Path) -> None:
    """Safely add the authentication import and router registration."""
    target = target.resolve()

    if not target.is_file():
        raise FileNotFoundError(
            f"Could not find main.py: {target}\n"
            "Pass the path to your backend/app/main.py file."
        )

    original = target.read_text(encoding="utf-8")
    tree = parse_python(original, str(target))

    if not any(is_app_assignment(node) for node in tree.body):
        raise RuntimeError(
            "Could not find a top-level app assignment in main.py. "
            "No changes were made."
        )

    import_exists = has_auth_import(tree)
    registration_exists = any(
        is_auth_router_registration(node) for node in tree.body
    )

    if import_exists and registration_exists:
        print(
            "SUCCESS: Authentication import and router registration "
            "already exist; no changes made."
        )
        return

    lines = original.splitlines(keepends=True)

    # Add the import immediately before the top-level app assignment.
    if not import_exists:
        app_line = next(
            node.lineno
            for node in tree.body
            if is_app_assignment(node)
        )

        lines.insert(app_line - 1, IMPORT_BLOCK + "\n")
        updated = "".join(lines)

        # Re-parse after insertion and before any file is written.
        tree = parse_python(updated, str(target))
        lines = updated.splitlines(keepends=True)
    else:
        updated = original

    # Register the router before demo_trading_router when possible.
    if not registration_exists:
        demo_line = next(
            (
                node.lineno
                for node in tree.body
                if is_demo_router_registration(node)
            ),
            None,
        )

        if demo_line is None:
            first_router_line = next(
                (
                    node.lineno
                    for node in tree.body
                    if isinstance(node, ast.Expr)
                    and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Attribute)
                    and isinstance(node.value.func.value, ast.Name)
                    and node.value.func.value.id == "app"
                    and node.value.func.attr == "include_router"
                ),
                None,
            )
            insertion_line = first_router_line
        else:
            insertion_line = demo_line

        if insertion_line is None:
            raise RuntimeError(
                "Could not find a router registration point in main.py. "
                "No changes were made."
            )

        lines = updated.splitlines(keepends=True)
        lines.insert(insertion_line - 1, ROUTER_BLOCK + "\n")
        updated = "".join(lines)

    # Final syntax check before modifying the real file.
    parse_python(updated, str(target))

    if updated == original:
        print("No changes were necessary.")
        return

    # Create a unique backup before writing.
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = target.with_name(
        f"{target.name}.backup_{timestamp}"
    )
    shutil.copy2(target, backup)

    try:
        target.write_text(updated, encoding="utf-8")
        # Confirm the saved file is valid Python.
        parse_python(target.read_text(encoding="utf-8"), str(target))
    except Exception:
        # Best-effort restoration if writing or validation fails.
        shutil.copy2(backup, target)
        raise

    print(f"Target: {target}")
    print(f"Backup: {backup}")
    print("SUCCESS: User-authentication router wiring added.")
    print(
        "Safety: Trading logic, broker execution, and risk settings "
        "were not intentionally changed."
    )
    print(
        "IMPORTANT: Router registration alone does not secure other "
        "user-owned endpoints or enforce account ownership."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Wire user authentication into backend/app/main.py"
    )
    parser.add_argument(
        "main_py",
        nargs="?",
        default="backend/app/main.py",
        help="Path to main.py (default: backend/app/main.py)",
    )
    args = parser.parse_args()

    try:
        wire_authentication(Path(args.main_py))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("No intended changes were made.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
