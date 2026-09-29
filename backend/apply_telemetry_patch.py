"""
RAYMOND v2.8 - Apply Automatic Entry Telemetry Patch

Safely patches backend/online_main.py to:
1. Import TelemetryAutomaticEntryWorker.
2. Register the automatic-entry telemetry router.
3. Use the telemetry worker for Stage 17.6.

This script does not change:
- AI strategy
- Risk Engine
- Paper execution rules
- Broker execution
- Live trading permissions
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent
MAIN_FILE = ROOT / "online_main.py"


IMPORT_MARKER = (
    "from app.automatic_entry_telemetry import "
    "TelemetryAutomaticEntryWorker, "
    "router as automatic_entry_telemetry_router"
)

IMPORT_LINE = IMPORT_MARKER + "\n"


def fail(message: str) -> None:
    raise SystemExit(f"PATCH STOPPED: {message}")


def main() -> None:
    if not MAIN_FILE.exists():
        fail(f"Could not find {MAIN_FILE}")

    content = MAIN_FILE.read_text(encoding="utf-8")

    original = content

    # ---------------------------------------------------------
    # 1. Add telemetry import.
    # ---------------------------------------------------------
    if IMPORT_MARKER not in content:
        worker_import = (
            "from app.automatic_entry_worker import AutomaticEntryWorker"
        )

        if worker_import in content:
            content = content.replace(
                worker_import,
                worker_import + "\n" + IMPORT_LINE.rstrip(),
                1,
            )
        else:
            fail(
                "Expected AutomaticEntryWorker import was not found. "
                "No changes were made."
            )

    # ---------------------------------------------------------
    # 2. Register telemetry router.
    # ---------------------------------------------------------
    router_include = (
        "app.include_router(automatic_entry_telemetry_router)"
    )

    if router_include not in content:
        # Put the router immediately after FastAPI app creation.
        app_creation = "app = FastAPI("

        position = content.find(app_creation)

        if position == -1:
            fail(
                "Could not find FastAPI app creation. "
                "No changes were made."
            )

        # Find the end of the FastAPI constructor.
        depth = 0
        end_position = None

        for index in range(position, len(content)):
            char = content[index]

            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1

                if depth == 0:
                    end_position = index + 1
                    break

        if end_position is None:
            fail(
                "Could not safely locate the end of FastAPI "
                "app creation. No changes were made."
            )

        content = (
            content[:end_position]
            + "\n\n"
            + router_include
            + "\n"
            + content[end_position:]
        )

    # ---------------------------------------------------------
    # 3. Replace Stage 17.6 worker construction.
    # ---------------------------------------------------------
    # Only replace the constructor call, not the import.
    worker_constructor = "AutomaticEntryWorker("

    telemetry_constructor = "TelemetryAutomaticEntryWorker("

    occurrences = content.count(worker_constructor)

    # The import itself contains the class name but not "(".
    if telemetry_constructor not in content:
        if occurrences == 0:
            fail(
                "Could not find AutomaticEntryWorker construction. "
                "No changes were made."
            )

        content = content.replace(
            worker_constructor,
            telemetry_constructor,
            1,
        )

    # ---------------------------------------------------------
    # Safety verification.
    # ---------------------------------------------------------
    required = [
        IMPORT_MARKER,
        router_include,
        telemetry_constructor,
    ]

    for marker in required:
        if marker not in content:
            fail(
                f"Verification failed for: {marker}. "
                "No changes were written."
            )

    if content == original:
        print("Telemetry patch is already applied.")
        return

    # ---------------------------------------------------------
    # Write only after every verification passed.
    # ---------------------------------------------------------
    MAIN_FILE.write_text(
        content,
        encoding="utf-8",
    )

    print("RAYMOND telemetry patch applied successfully.")
    print(f"Updated: {MAIN_FILE}")
    print("")
    print("Changes:")
    print("1. Telemetry worker import added.")
    print("2. Telemetry router registered.")
    print("3. Stage 17.6 uses the telemetry worker.")
    print("")
    print("Safety:")
    print("- Paper trading only.")
    print("- Broker orders remain disabled.")
    print("- Live trading remains disabled.")
    print("- Risk Engine remains authoritative.")


if __name__ == "__main__":
    main()
