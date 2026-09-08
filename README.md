# RAYMOND v2.8 — XAUUSD Trader (Trader)

RAYMOND v2.8 is a market-analysis and paper-trading system focused on XAUUSD (gold). It includes a Flutter Android dashboard, a FastAPI backend, broker adapters (MT5 / Exness), strategy + AI decision layer, risk management, persistent journaling, backtesting, and execution verification.

IMPORTANT: Live trading is deliberately locked by default. See "Safety & Live Trading" below.

Status
- Frontend: Flutter dashboard (Android) — present (partial)
- Backend: FastAPI — (link or repo name)
- Adapters: MT5 / Exness — (link or repo name)
- Tests & CI: (status badge / link)
- Live trading: disabled by default (safety gating enforced)

Key Features
- Live XAUUSD price & candlestick charts
- Indicators: EMA20/EMA50, RSI, ATR
- Strategy + AI decision layer and risk management
- Broker adapters: MT5 / Exness (execution + verification)
- Paper trading, position protection, emergency stop/close
- Persistent journal and trade-history
- Backtesting, walk-forward testing, Monte Carlo analysis
- API authentication and execution verification

Architecture
- Frontend: Flutter app (android) — UI, visualization, settings
- Backend: FastAPI — market data ingestion, strategy execution, risk, execution gateway, journal
- Adapters: broker-specific connectors (MT5 / Exness)
- DB: persistent trade journal + metadata
- CI: GitHub Actions (analyze, test, coverage, SCA)

Quickstart (developer)
1. Clone repos
   - Frontend: git clone <repo>/RAYMOND-V2.8
   - Backend: git clone <repo>/raymond-backend (replace with actual backend repo)
   - Adapters: git clone <repo>/raymond-adapters (if separate)
2. Flutter app (frontend)
   - Ensure Flutter SDK installed: https://flutter.dev/docs/get-started/install
   - cd flutter_app
   - Create pubspec.yaml if missing: `flutter pub get`
   - Run: `flutter run -d android` (or `flutter build apk`)
3. Backend (FastAPI)
   - Python 3.11+ recommended
   - Create venv: `python -m venv .venv && source .venv/bin/activate`
   - Install: `pip install -r requirements.txt` (or `pip install fastapi uvicorn ...`)
   - Run locally: `uvicorn app.main:app --reload --port 8000`

Configuration
- Environment variables (examples)
  - RAYMOND_ENV=development|staging|production
  - LIVE_TRADING_ENABLED=false  # MUST be false by default
  - DATABASE_URL=postgres://...
  - MT5_LOGIN, MT5_PASSWORD, EXNESS_TOKEN — do NOT commit keys to repo
- Store secrets in GitHub Secrets or a secret manager. The code enforces that live-execution endpoints reject requests unless LIVE_TRADING_ENABLED==true AND the deploy environment is approved.

Safety & Live Trading (critical)
- Live trading is locked by default. To enable:
  1. Environment flag: LIVE_TRADING_ENABLED=true (only in production and after approvals)
  2. Manual deployment approval in CI/CD (required)
  3. Team sign-off + documented runbook
- Emergency stop: /api/admin/emergency-stop (requires admin auth). This toggles an atomic server-side flag preventing any new executions.

Testing & CI
- Run unit tests:
  - Frontend: `flutter test`
  - Backend: `pytest`
- CI: GitHub Actions should run `flutter analyze`, `flutter test`, `pytest`, and dependency SCA (safety/snyk or `pip-audit`/`pub outdated`).
- Execution verification tests: mocked adapter tests validate trading lifecycle (place -> fill -> journal -> reconcile)

Backtesting & Analysis
- Backtest config and dataset lives in the backtests folder (link).
- Walk-forward and Monte Carlo are run by the analysis pipeline; results stored under /artifacts/backtests/

Contributing
- Fork, create a branch per issue/feature, add tests, open PR.
- All PRs must include passing CI and code review approvals.
- No secrets/API tokens in PRs — CI will fail if secrets are detected.

Release & Deployment
- Release candidates are built and smoke-tested in staging.
- Canary rollout (10% traffic) followed by health-gated promotion.
- Manual approval required to enable LIVE_TRADING_ENABLED=true.

Troubleshooting
- If market data is stale, check market feed health and the "stale-market" alert metric.
- If orders fail, check adapter logs and execution-verification traces.

Contact / Maintainers
- Maintainer: @raebby040-cpu
- For emergencies: contact on-call and follow runbook: docs/RUNBOOK.md

License
- Add license file (e.g., MIT) or specify commercial terms.

Changelog
- See CHANGELOG.md for release notes and upgrade instructions.
