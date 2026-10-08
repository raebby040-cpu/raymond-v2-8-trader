#!/usr/bin/env python3
"""Safely add the MT5 Bridge import and registration to backend/app/main.py."""

from pathlib import Path

MAIN_FILE = Path("backend/app/main.py")

IMPORT_BLOCK = """# ============================================================

MT5 BRIDGE INTEGRATION

============================================================

try:
from .mt5_bridge_integration import register_mt5_bridge
except ImportError:
from mt5_bridge_integration import register_mt5_bridge
"""

REGISTRATION_LINE = "register_mt5_bridge(app)"

def main() -> None:
if not MAIN_FILE.is_file():
raise SystemExit(f"ERROR: {MAIN_FILE} was not found.")

source = MAIN_FILE.read_text(encoding="utf-8")

if "from .mt5_bridge_integration import register_mt5_bridge" in source:
    print("SKIPPED: MT5 Bridge import already exists.")
    return

app_marker = "app = FastAPI("
app_start = source.find(app_marker)

if app_start < 0:
    raise SystemExit("ERROR: Could not find app = FastAPI(...) in main.py.")

# Find the end of the FastAPI constructor without assuming a fixed line number.
opening = source.find("(", app_start)
depth = 0
quote = None
escaped = False
app_end = None

for index in range(opening, len(source)):
    char = source[index]

    if quote:
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == quote:
            quote = None
        continue

    if char in ("'", '"'):
        quote = char
    elif char == "(":
        depth += 1
    elif char == ")":
        depth -= 1
        if depth == 0:
            app_end = index + 1
            break

if app_end is None:
    raise SystemExit("ERROR: Could not locate the end of app = FastAPI(...).")

# Add the import before the app declaration.
source = source[:app_start] + IMPORT_BLOCK + "\n\n" + source[app_start:]

# Recalculate the app constructor end after inserting the import.
app_start = source.find(app_marker)
opening = source.find("(", app_start)
depth = 0
quote = None
escaped = False
app_end = None

for index in range(opening, len(source)):
    char = source[index]

    if quote:
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == quote:
            quote = None
        continue

    if char in ("'", '"'):
        quote = char
    elif char == "(":
        depth += 1
    elif char == ")":
        depth -= 1
        if depth == 0:
            app_end = index + 1
            break

if app_end is None:
    raise SystemExit("ERROR: Could not locate the end of the FastAPI constructor.")

# Register the read-only router once, immediately after app creation.
source = (
    source[:app_end]
    + "\n\n# Register the read-only MT5 Bridge API.\n"
    + REGISTRATION_LINE
    + source[app_end:]
)

MAIN_FILE.write_text(source, encoding="utf-8")
print("SUCCESS: Added MT5 Bridge import and router registration to main.py.")

if name == "main":
main()
