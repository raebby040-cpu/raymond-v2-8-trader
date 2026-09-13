RAYMOND v2.8 — Build Status

Current Release Status

Release: RAYMOND v2.8
Trading mode: SAFE PAPER / READ-ONLY
Live trading: DISABLED
Real broker order execution: NOT IMPLEMENTED
Production host: Render
Production entrypoint: "backend/online_main.py" → "online_main:app"

---

1. Production Architecture

The current production flow is:

MT5 Market Data
      ↓
Technical Indicators
      ↓
Step 13 — AI Trading Decision
      ↓
Step 14 — Deterministic Risk Engine
      ↓
Safety / Emergency Stop
      ↓
Paper Execution Gateway
      ↓
Paper Position / Journal / Dashboard

AI may recommend a trade, but it cannot directly execute a broker order.

Deterministic risk and safety controls remain the final authority.

---

2. Market Data

Production online market API

The Android dashboard uses the read-only online market API:

GET /api/online/status
GET /api/online/price
GET /api/online/candlesticks
GET /api/online/indicators
GET /api/online/analysis

Supported primary instrument:

XAUUSD

Supported timeframes include:

M1
M5
M15
M30
H1
H4
D1

The public online market API is read-only.

It does not place, modify, or close broker orders.

---

3. MT5 Integration

MT5 is used as a market-data source and telemetry/decision bridge.

Current MT5 capabilities include:

- connection handling
- symbol discovery
- XAUUSD discovery
- bid/ask retrieval
- OHLC candle retrieval
- account/terminal telemetry
- read-only AI decision requests

The MT5 bridge does not authorize live trading.

---

4. AI Trading Brain

Step 13 is implemented as a multi-layer AI decision engine.

It evaluates:

- market regime
- setup
- direction
- trend alignment
- technical confluence
- confidence
- stop-loss requirements
- risk/reward requirements
- trade-management context

Possible primary decisions:

BUY
SELL
WAIT

The AI is advisory.

It cannot:

- place broker orders
- close broker positions
- modify broker positions
- bypass the Risk Engine
- bypass Emergency Stop
- enable live trading

---

5. Risk Engine

The deterministic Risk Engine provides the final trade-risk validation.

Current controls include:

- maximum risk per trade
- maximum daily loss
- maximum open positions
- maximum total exposure
- mandatory stop-loss
- minimum risk/reward
- broker/instrument-aware position sizing
- volume validation
- fail-closed pre-trade checks

A valid AI recommendation can still be rejected by Risk.

---

6. Execution

The current execution gateway is paper-only.

The production gateway:

AI → Risk → Paper Execution

is permitted.

Real broker execution is not implemented.

The system does not currently authorize:

OrderSend()
CTrade::Buy()
CTrade::Sell()
PositionOpen()

or equivalent real-money execution paths.

---

7. Emergency Stop

The safety system is fail-closed.

Trading is blocked when:

- emergency stop is active
- connection health is invalid
- heartbeat is stale
- required safety conditions are missing
- execution authorization is absent

Resetting the emergency stop does not enable live trading.

---

8. Paper / Demo Trading

Paper trading is implemented separately from real broker execution.

Paper functionality includes:

- simulated BUY/SELL trades
- simulated positions
- stop-loss/take-profit handling
- P&L
- performance statistics
- journal persistence
- dashboard reporting

Paper trading does not send orders to a broker.

---

9. Flutter Android Dashboard

The Flutter dashboard is connected to the Render production API.

Current areas include:

- dashboard
- market chart
- analysis
- positions
- settings
- paper trading
- journal
- system status

The positions screen is read-only.

The settings screen does not contain a live-trading enable control.

The application clearly reports when the system is operating in safe paper mode.

---

10. Database / Journal

The backend contains persistent trading models and journal functionality.

The journal distinguishes execution types and is currently used for paper/demo trading.

The system does not treat paper trades as real broker executions.

---

11. Backtesting

The canonical production backtester is:

backend/app/backtest_engine.py

It supports:

- historical OHLC processing
- technical indicators
- Step 13 AI decisions
- Risk Engine compatibility
- deterministic simulated execution
- equity tracking
- P&L
- trade ledger
- performance reporting
- spread/slippage/commission assumptions
- daily-loss handling
- conservative SL/TP handling

The obsolete duplicate "backend/app/backtest.py" has been removed.

---

12. Legacy Cleanup Completed

The following obsolete components have been removed:

backend/app/main_updated.py
backend/fastapi_app/main.py
backend/app/backtest.py
backend/app/streaming.py
backend/app/market_data.py

The production system now uses the newer market-data, indicator, AI, risk, and paper-execution architecture.

---

13. Testing

Production-focused tests cover:

- health endpoint
- online market API safety
- API validation
- AI decision flow
- strategy behavior
- broker safety
- execution authorization
- paper trading
- risk controls
- backtesting
- Flutter analysis/testing through CI

GitHub Actions runs backend tests and Flutter checks.

---

14. Deployment

Production deployment uses:

Docker
    ↓
Render
    ↓
online_main:app

Production health endpoint:

GET /health

Expected state:

{
  "status": "healthy",
  "service": "raymond-v2-8-trader",
  "live_trading_enabled": false
}

---

15. Current Readiness

Safe paper/demo release

READY

The system is suitable for continued:

- paper trading
- market-data monitoring
- AI decision testing
- risk testing
- backtesting
- dashboard testing
- journal testing

Real-money trading

NOT READY

Real-money execution remains intentionally disabled.

Before any future live-trading implementation, the system would require a separate controlled implementation and validation of:

- broker authentication
- broker order execution
- order acknowledgement
- position reconciliation
- broker-side SL/TP verification
- execution failure handling
- duplicate-order protection
- connection recovery
- live risk enforcement
- audit logging
- independent safety validation
- extensive paper/forward testing

---

16. Safety Rule

The core rule for RAYMOND v2.8 is:

«AI intelligence can recommend. Deterministic risk and safety controls can veto.»

No AI recommendation is sufficient by itself to authorize real-money execution.

---

17. Current Goal

The immediate goal is to finish the safe paper/demo production system cleanly.

Live broker execution remains outside the current release.
