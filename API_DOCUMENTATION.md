# RAYMOND v2.8 Trading System - Complete Documentation

## Overview

RAYMOND v2.8 is a **production-ready automated trading system** for XAUUSD (Gold vs USD) with:
- ✅ AI-driven strategy engine with multi-indicator analysis
- ✅ Real-time market data integration
- ✅ Comprehensive risk management & position protection
- ✅ Paper trading (default) + live trading capability
- ✅ Emergency stop mechanism (atomic operation)
- ✅ Persistent trade journal & backtesting
- ✅ Flutter Android mobile dashboard
- ✅ FastAPI backend with PostgreSQL database
- ✅ Full CI/CD with GitHub Actions

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   RAYMOND v2.8 Architecture                 │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────┐         ┌──────────────────────┐     │
│  │   Flutter App    │         │   FastAPI Backend    │     │
│  │  (Mobile UI)     │◄────────►│  (Port 8000)         │     │
│  │  5 Screens       │  REST    │  RESTful APIs        │     │
│  │  Real-time Data  │  APIs    │  Async Support       │     │
│  └──────────────────┘         └──────────────────────┘     │
│         │                               │                    │
│         │                               ▼                    │
│         │                    ┌─────────────────────┐         │
│         │                    │  Business Logic     │         │
│         │                    ├─────────────────────┤         │
│         │                    │ • Strategy Engine   │         │
│         │                    │ • Risk Management   │         │
│         │                    │ • Broker Adapters   │         │
│         │                    │ • Market Data       │         │
│         │                    │ • Backtesting       │         │
│         │                    └─────────────────────┘         │
│         │                               │                    │
│         │                               ▼                    │
│         │                    ┌─────────────────────┐         │
│         └───────────────────►│   PostgreSQL DB     │         │
│                              │ (SQLAlchemy ORM)    │         │
│                              │                     │         │
│                              │ • Trades            │         │
│                              │ • Positions         │         │
│                              │ • Decisions         │         │
│                              │ • Risk Events       │         │
│                              │ • Journal           │         │
│                              │ • Backtests         │         │
│                              └─────────────────────┘         │
│                                       ▲                      │
│                                       │                      │
│                                 ┌─────────────┐              │
│                                 │  Brokers    │              │
│                                 ├─────────────┤              │
│                                 │ • MT5       │              │
│                                 │ • Exness    │              │
│                                 │ • Paper     │              │
│                                 └─────────────┘              │
│                                       ▲                      │
│                                       │                      │
│                                 ┌─────────────┐              │
│                                 │Market Data  │              │
│                                 ├─────────────┤              │
│                                 │ • XAUUSD    │              │
│                                 │ • Candlestick
│                                 │ • Indicators│              │
│                                 │ • Streaming │              │
│                                 └─────────────┘              │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites
- Python 3.11+
- Flutter SDK 3.0+
- Docker & Docker Compose (optional)
- PostgreSQL 14+ (production) or SQLite (development)

### Backend Setup (FastAPI)

```bash
# 1. Clone repository
git clone https://github.com/raebby040-cpu/raymond-v2-8-trader.git
cd raymond-v2-8-trader

# 2. Create virtual environment
cd backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Setup environment
cp .env.example .env
# Edit .env with your configuration

# 5. Initialize database
python app/migrations.py create
python app/migrations.py seed  # Optional: load demo data

# 6. Run backend
uvicorn app.main:app --reload --port 8000
```

**Backend API available at:** `http://localhost:8000`
**API Documentation:** `http://localhost:8000/docs` (Swagger UI)

### Frontend Setup (Flutter)

```bash
# 1. Navigate to Flutter app
cd flutter_app

# 2. Get dependencies
flutter pub get

# 3. Run on Android device/emulator
flutter run -d android

# 4. Build APK for distribution
flutter build apk --release
```

### Docker Deployment

```bash
# Start entire stack
docker-compose -f docker-compose.dev.yml up

# Backend: http://localhost:8000
# Database: PostgreSQL on localhost:5432
```

---

## API Endpoints

### Health & Status
- `GET /health` - System health check
- `GET /` - Root endpoint with service info
- `GET /api/admin/status` - Detailed admin status

### Market Data
- `GET /api/market/price?symbol=XAUUSD` - Current price with bid/ask
- `GET /api/market/candlesticks?symbol=XAUUSD&timeframe=H1&limit=100` - Historical candles
- `GET /api/market/indicators?symbol=XAUUSD` - Technical indicators (EMA20, EMA50, RSI, ATR, MACD)

### Trading
- `POST /api/trading/place-order` - Place new trade
- `GET /api/trading/positions` - Get open positions
- `POST /api/trading/close-position` - Close a position

### Strategy & AI
- `GET /api/strategy/decision?symbol=XAUUSD` - AI trading decision
- `POST /api/strategy/backtest` - Run backtest

### Risk Management
- `POST /api/risk/validate-position` - Validate position against risk rules

### Journal & History
- `GET /api/journal/trades?limit=50&offset=0` - Trade history

### Admin
- `POST /api/admin/emergency-stop` - Emergency stop (requires API key)
- `GET /api/admin/status` - System status

---

## Strategy Engine

### Indicators Used

1. **EMA Crossover (Golden/Death Cross)** - 30% weight
   - EMA20 > EMA50: Bullish signal (BUY)
   - EMA20 < EMA50: Bearish signal (SELL)

2. **RSI (14-period)** - 25% weight
   - RSI < 30: Oversold (BUY signal)
   - RSI > 70: Overbought (SELL signal)

3. **ATR Volatility** - 20% weight
   - High volatility: Breakout opportunity
   - Low volatility: Consolidation phase

4. **Momentum** - 15% weight
   - Positive momentum (>1%): BUY
   - Negative momentum (<-1%): SELL

### Decision Levels

- **STRONG_BUY**: Buy score > 0.75 (High conviction)
- **BUY**: Buy score > 0.60 (Good signal)
- **WEAK_BUY**: Buy score > 0.50 (Mild signal)
- **HOLD**: No clear direction
- **WEAK_SELL**: Sell score > 0.50
- **SELL**: Sell score > 0.60
- **STRONG_SELL**: Sell score > 0.75

### Example Decision Response

```json
{
  "timestamp": "2024-09-08T14:30:00Z",
  "final_decision": "strong_buy",
  "confidence": 0.85,
  "current_price": 2050.45,
  "bid": 2050.40,
  "ask": 2050.50,
  "recommendation": {
    "action": "BUY",
    "suggested_entry": 2050.45,
    "stop_loss": 2045.17,
    "take_profit": 2060.70,
    "risk_reward_ratio": 1.67
  },
  "risk_level": "MEDIUM",
  "analysis": {
    "ema_crossover": {
      "signal": "buy",
      "strength": 0.75,
      "ema20": 2049.50,
      "ema50": 2047.00
    },
    "rsi": {
      "signal": "buy",
      "strength": 0.65,
      "rsi": 65.50
    },
    "atr_volatility": {
      "signal": "hold",
      "strength": 0.45,
      "atr": 12.35
    },
    "momentum": {
      "signal": "buy",
      "strength": 0.72,
      "momentum": 1.85
    }
  }
}
```

---

## Risk Management

### Default Risk Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| Max Daily Loss | 2.0% | Max loss per day in % of balance |
| Max Trade Loss | 1.0% | Max loss per single trade |
| Max Open Positions | 3 | Max concurrent positions allowed |
| Max Leverage | 20x | Maximum account leverage |
| Min Stop Loss | 5 pips | Minimum distance from entry |
| Max Position Size | 10 lots | Maximum position size |
| Emergency Stop | 5.0% | Trigger emergency close at 5% loss |

### Position Validation

Every position is validated against:
- ✅ Stop loss distance (minimum 5 pips)
- ✅ Position size limits
- ✅ Risk % per trade (max 1-2%)
- ✅ Account leverage limits
- ✅ Open position count

### Emergency Stop Mechanism

**Endpoint:** `POST /api/admin/emergency-stop`
**Headers Required:** `x-api-key: {EMERGENCY_API_KEY}`

**Behavior:**
1. Closes ALL open positions immediately
2. Blocks new order placement
3. Logs critical event
4. Returns confirmation with positions closed

---

## Database Schema

### Core Tables

**Trades**
- trade_id (primary key)
- symbol, direction, order_type
- entry_price, exit_price, quantity
- stop_loss, take_profit
- status (open/closed/cancelled)
- pnl, pnl_percent
- opened_at, closed_at
- broker, strategy_decision, confidence

**Positions**
- position_id (primary key)
- trade_id (foreign key)
- symbol, direction, quantity
- entry_price, current_price
- unrealized_pnl, unrealized_pnl_percent
- opened_at, is_active

**StrategyDecisions**
- Audit trail of all AI decisions
- Indicators at decision time
- Entry/exit recommendations
- Execution status

**RiskEvents**
- Alert/warning logs
- Stale market detection
- Stop loss hits
- Emergency events

**Journal**
- Trade analysis notes
- Market review entries
- Risk review logs
- Searchable categories/tags

**Account**
- Account balance tracking
- Equity & margin metrics
- Performance statistics
- Win rate, max drawdown

**Backtest**
- Historical backtest results
- Strategy performance metrics
- Walk-forward analysis
- Monte Carlo simulation results

---

## Testing

### Run Tests

```bash
cd backend

# Run all tests
pytest

# Run specific test file
pytest tests/test_strategy.py

# Run with coverage
pytest --cov=app tests/

# Run async tests
pytest -asyncio tests/test_api.py
```

### Test Suites Included

1. **Strategy Tests** (`test_strategy.py`)
   - EMA crossover signals
   - RSI calculations
   - ATR volatility analysis
   - Momentum analysis
   - AI decision layer

2. **Broker Tests** (`test_brokers.py`)
   - MT5 adapter functionality
   - Exness adapter functionality
   - Order placement & cancellation
   - Execution verification

3. **Risk Management Tests** (`test_risk_management.py`)
   - Position risk calculation
   - Risk/reward ratios
   - Risk parameter validation

4. **API Tests** (`test_api.py`)
   - Endpoint functionality
   - Request/response validation
   - Error handling

---

## Live Trading Mode

### Enabling Live Trading

**CRITICAL: Live trading is DISABLED by default**

To enable:

1. **Set environment variable:**
   ```bash
   export LIVE_TRADING_ENABLED=true
   ```

2. **Configure broker credentials:**
   ```bash
   MT5_LOGIN=your_real_login
   MT5_PASSWORD=your_real_password
   EXNESS_TOKEN=your_real_token
   ```

3. **In production deployment:**
   - Set via CI/CD secrets
   - Require manual approval
   - Document runbook
   - Team sign-off required

### Safety Checks

Before live trading, ensure:
- ✅ All tests passing
- ✅ Backtest results > 0.70 win rate
- ✅ Risk parameters reviewed
- ✅ Emergency stop API key set
- ✅ Database backups enabled
- ✅ Monitoring/alerting configured
- ✅ Runbook documented

---

## Backtesting

### Running a Backtest

```bash
POST /api/strategy/backtest
Content-Type: application/json

{
  "strategy_name": "EMA_Crossover",
  "symbol": "XAUUSD",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "initial_balance": 10000.0
}
```

### Response

```json
{
  "backtest_id": "BT-20240908143000",
  "status": "completed",
  "total_trades": 125,
  "winning_trades": 98,
  "losing_trades": 27,
  "win_rate": 0.784,
  "total_pnl": 2150.75,
  "total_pnl_percent": 21.51,
  "max_drawdown": 0.045,
  "sharpe_ratio": 1.85,
  "sortino_ratio": 2.12,
  "profit_factor": 1.95
}
```

---

## Troubleshooting

### Backend Issues

**Port 8000 already in use:**
```bash
lsof -i :8000  # Find process
kill -9 <PID>  # Kill it
```

**Database connection error:**
```bash
# Check DATABASE_URL in .env
# For SQLite: sqlite:///./raymond_trading.db
# For PostgreSQL: postgresql://user:pass@localhost:5432/raymond

# Reinitialize database
python app/migrations.py drop
python app/migrations.py create
python app/migrations.py seed
```

**Import errors:**
```bash
pip install --upgrade -r requirements.txt
```

### Flutter Issues

**App won't connect to backend:**
```bash
# Check backend is running
curl http://localhost:8000/health

# Update API base URL in Flutter app
# flutter_app/lib/services/api_client.dart
```

**Build errors:**
```bash
flutter clean
flutter pub get
flutter run
```

---

## Deployment

### Production Deployment (Docker)

```bash
# Build Docker image
docker build -f backend/Dockerfile -t raymond-trading:latest .

# Run container
docker run -d \
  -p 8000:8000 \
  -e RAYMOND_ENV=production \
  -e DATABASE_URL=postgresql://user:pass@postgres:5432/raymond \
  -e LIVE_TRADING_ENABLED=false \
  raymond-trading:latest
```

### Kubernetes Deployment

See `docs/kubernetes-deployment.yaml` for full K8s setup.

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit changes: `git commit -am 'Add feature'`
4. Push to branch: `git push origin feature/your-feature`
5. Submit pull request

**All PRs must:**
- ✅ Pass CI/CD tests
- ✅ Have code review approval
- ✅ Not contain secrets/API keys
- ✅ Include test coverage

---

## Support & Contact

- **Issues:** GitHub Issues
- **Documentation:** See `/docs` folder
- **Emergency:** Contact on-call maintainer
- **Maintainer:** @raebby040-cpu

---

## License

See LICENSE file for terms.

---

## Changelog

### v2.8.0 (Current)
- ✅ Complete backend implementation
- ✅ Database integration (SQLAlchemy + PostgreSQL/SQLite)
- ✅ Real-time market data streaming
- ✅ Comprehensive test suite
- ✅ Flutter mobile frontend
- ✅ Risk management system
- ✅ Emergency stop mechanism
- ✅ Backtesting framework
- ✅ CI/CD with GitHub Actions

### v2.7.0
- Previous version features

---

**Last Updated:** September 8, 2024
**Version:** 2.8.0
**Status:** ✅ Production Ready (Paper Trading)
