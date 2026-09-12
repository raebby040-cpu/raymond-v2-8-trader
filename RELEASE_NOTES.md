RAYMOND v2.8 — Release Notes

Release

Version: 2.8
Release Type: Major project integration/release
Deployment: Render
Branch: "main"

Safety Status

Live Trading: DISABLED
Real Broker Execution: NOT IMPLEMENTED
Paper Trading: SUPPORTED
Demo Trading: SUPPORTED

---

1. Release Overview

RAYMOND v2.8 brings together the backend, Flutter application, market-data integration, strategy engine, risk-management components, paper-trading workflow, database/journal functionality, testing, and deployment configuration.

The current release is intended for:

- development
- testing
- market-data monitoring
- strategy analysis
- paper trading
- demo trading
- deployment validation

It is not approved for real-money live trading.

---

2. Backend

The FastAPI backend provides the core RAYMOND services.

Major areas include:

- health monitoring
- market data
- technical indicators
- strategy analysis
- AI decisions
- risk validation
- paper trading
- demo trading
- journal/history
- administration
- database integration
- backtesting

Production entrypoint:

online_main:app

---

3. Online Market Data API

The release includes a broker-independent read-only market-data bridge.

Public API:

/api/online/*

Endpoints include:

GET /api/online/status
GET /api/online/price
GET /api/online/candlesticks
GET /api/online/indicators
GET /api/online/analysis

The online bridge is intended to keep the mobile application supplied with market information when direct MT5 access is unavailable.

It does not provide live broker execution.

---

4. Flutter Integration

The Flutter application uses the production backend:

https://raymond-v2-8-trader.onrender.com

Public market-data requests use:

/api/online/price
/api/online/candlesticks
/api/online/indicators
/api/online/status
/api/online/analysis

Trading, strategy, risk, journal, and administrative requests remain separate API functions.

---

5. MT5 Integration

The project retains MT5-backed market-data functionality for the internal trading architecture.

Internal routes may use:

/api/market/*

These should not be confused with the public/mobile market-data API.

The public Flutter market-data contract is:

/api/online/*

---

6. Strategy and Analysis

RAYMOND includes technical-analysis and AI decision functionality.

The analysis pipeline can use information such as:

- price
- candlesticks
- EMA
- RSI
- ATR
- MACD
- momentum
- strategy signals
- risk information

AI analysis is not equivalent to broker execution.

A generated BUY or SELL decision must not be interpreted as an instruction to place a real-money broker order.

---

7. Risk Management

Risk-management functionality remains part of the trading pipeline.

Risk validation may consider factors such as:

- position size
- stop-loss distance
- risk percentage
- risk/reward
- account constraints
- open-position limits

Risk controls must not be bypassed by API, Flutter, strategy, or broker-integration changes.

---

8. Paper and Demo Trading

The release supports non-live trading workflows.

These environments are intended for:

- strategy validation
- UI testing
- API testing
- risk testing
- trade lifecycle testing
- system integration testing

Paper/demo results must not be presented as evidence of real broker execution readiness.

---

9. Database and Journal

The project contains persistent data components for areas including:

- trades
- positions
- strategy decisions
- risk events
- journal entries
- account information
- backtest results

The exact production database configuration must be verified before treating the system as production-grade persistent infrastructure.

---

10. Deployment

RAYMOND v2.8 is deployed on Render using Docker.

Production configuration:

Service: raymond-v2-8-trader
Branch: main
Runtime: Docker
Dockerfile: ./Dockerfile
Health Check: /health
Auto Deploy: enabled
Instances: 1
Region: Singapore

Production startup uses:

online_main:app

---

11. Health Check

Production health endpoint:

/health

Example:

curl https://raymond-v2-8-trader.onrender.com/health

The health response must continue to indicate that live trading is disabled.

---

12. Safety Controls

The required production setting is:

LIVE_TRADING_ENABLED=false

The release must not:

- send real-money orders
- enable live broker execution
- bypass risk validation
- modify real broker positions
- close real broker positions
- expose broker credentials
- treat paper trades as real executions

---

13. Real Broker Execution

Real broker execution is not included as a completed production capability in this release.

Before any future live-trading release, the system must implement and validate:

Order Submission
       ↓
Broker Acknowledgement
       ↓
Fill / Rejection
       ↓
Position Reconciliation
       ↓
Execution Audit

It must also handle:

- network failures
- broker disconnects
- timeouts
- rejected orders
- partial fills where applicable
- slippage
- duplicate requests
- stale market data
- inconsistent broker state
- emergency stop

---

14. Testing

The repository contains automated tests and CI configuration.

Testing should cover:

- API
- strategy
- risk
- market data
- paper trading
- database
- execution lifecycle
- failure recovery
- security
- Flutter integration

Coverage and test-count claims should only be published after verification against the current commit.

---

15. Known Limitations

Current limitations include:

Live execution

Real-money broker execution is not implemented.

Market-data dependency

The public online market-data bridge depends on its upstream market-data provider.

MT5 availability

Direct MT5 functionality depends on MT5 connectivity and the deployment environment.

Production hardening

Authentication, authorization, monitoring, recovery, and other production controls require continued validation.

Test depth

Existing tests provide a foundation, but additional integration and failure-path tests are required before live trading approval.

---

16. Upgrade Guidance

When upgrading RAYMOND:

1. Back up important data.
2. Verify the target commit.
3. Run automated tests.
4. Deploy with live trading disabled.
5. Verify "/health".
6. Verify "/api/online/status".
7. Verify market-data endpoints.
8. Verify Flutter connectivity.
9. Review Render logs.
10. Validate paper/demo trading.
11. Confirm no real broker orders were generated.

---

17. Rollback

If a release causes a critical problem:

1. Keep live trading disabled.
2. Identify the last known-good commit.
3. Redeploy that version.
4. Verify "/health".
5. Verify "/api/online/status".
6. Verify Flutter connectivity.
7. Review logs.
8. Re-test critical paper/demo workflows.

Do not enable live trading as part of troubleshooting.

---

18. Future Release Priorities

Future releases should focus on:

1. Complete broker execution implementation
2. Order lifecycle reconciliation
3. Failure recovery
4. Broker disconnect handling
5. Stronger automated integration tests
6. Authentication and authorization
7. Rate limiting
8. Monitoring and alerting
9. Database backup/recovery
10. Security hardening
11. Production load testing
12. Formal live-trading approval process

---

19. Release Classification

RAYMOND v2.8 should currently be classified as:

DEPLOYED
+
PAPER/DEMO TRADING
+
PRODUCTION VALIDATION
+
LIVE TRADING DISABLED

It should not currently be classified as:

REAL-MONEY LIVE TRADING READY

---

20. Final Safety Statement

Until the complete broker execution lifecycle and production safety review are finished:

LIVE_TRADING_ENABLED=false

must remain unchanged.

RAYMOND v2.8 is a deployed trading-system foundation with supported market-data, analysis, paper-trading, demo-trading, mobile, backend, and deployment capabilities.

Real-money broker execution remains a future engineering stage.
