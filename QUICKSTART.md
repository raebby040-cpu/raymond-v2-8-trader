# RAYMOND v2.8 - Quick Start Guide

Get the trading system running in under 5 minutes.

## Prerequisites

- **Python 3.11+** (or use Docker)
- **pip** or **poetry** for dependency management
- **Git** for cloning the repository

## Option 1: Local Development (Recommended for Development)

### Step 1: Clone Repository

```bash
git clone https://github.com/raebby040-cpu/raymond-v2-8-trader.git
cd raymond-v2-8-trader/backend
```

### Step 2: Create Virtual Environment

```bash
python -m venv .venv

# On macOS/Linux:
source .venv/bin/activate

# On Windows:
.venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment

```bash
cp ../.env.example .env
# Edit .env if needed (optional for development)
```

### Step 5: Run the Application

```bash
uvicorn fastapi_app.main:app --reload --port 8000
```

You should see:
```
INFO:     Application startup complete
INFO:     ✓ Database tables initialized
INFO:     ✓ RAYMOND v2.8 started in development mode
```

### Step 6: Access the API

- **API Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health
- **Random Joke**: http://localhost:8000/joke

---

## Option 2: Docker (Recommended for Production)

### Step 1: Build Docker Image

```bash
docker-compose build
```

### Step 2: Start Services

```bash
docker-compose up -d
```

### Step 3: View Logs

```bash
docker-compose logs -f backend
```

### Step 4: Access the API

- **API Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

### Step 5: Stop Services

```bash
docker-compose down
```

---

## Testing the API

### Health Check

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:45.123456",
  "version": "2.8.0",
  "environment": "development",
  "live_trading_enabled": false,
  "database": "connected"
}
```

### Get Current Price

```bash
curl "http://localhost:8000/api/market/price?symbol=XAUUSD"
```

### Analyze Strategy

```bash
curl -X POST http://localhost:8000/api/strategy/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "XAUUSD",
    "ema20": 2050.5,
    "ema50": 2048.25,
    "rsi": 55.3,
    "current_price": 2050.45
  }'
```

### Place a Paper Trade Order

```bash
curl -X POST http://localhost:8000/api/trading/place-order \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "XAUUSD",
    "direction": "buy",
    "quantity": 1.0,
    "entry_price": 2050.45,
    "stop_loss": 2045.0,
    "take_profit": 2055.0
  }'
```

### Get Open Positions

```bash
curl http://localhost:8000/api/trading/positions
```

### Emergency Stop (Requires API Key)

```bash
curl -X POST http://localhost:8000/api/admin/emergency-stop \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_emergency_api_key_here" \
  -d '{"reason": "Manual halt for testing"}'
```

---

## Running Tests

```bash
# Unit tests
pytest

# With coverage
pytest --cov=app --cov-report=html

# Watch mode (requires pytest-watch)
ptw
```

---

## Troubleshooting

### Issue: `ModuleNotFoundError: No module named 'fastapi'`

**Solution:** Ensure virtual environment is activated and dependencies are installed.

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### Issue: `Address already in use :8000`

**Solution:** Change the port or kill the existing process.

```bash
# Use a different port
uvicorn fastapi_app.main:app --reload --port 8001

# Or kill process on port 8000
lsof -ti:8000 | xargs kill -9  # macOS/Linux
netstat -ano | findstr :8000   # Windows
```

### Issue: Database errors

**Solution:** The SQLite database is created automatically on startup. If you need to reset:

```bash
rm raymond.db
uvicorn fastapi_app.main:app --reload
```

### Issue: Emergency endpoint returns 503

**Solution:** Set `EMERGENCY_API_KEY` in `.env` file.

```bash
echo "EMERGENCY_API_KEY=your_secure_key_here" >> .env
```

---

## Important: Safety & Live Trading

⚠️ **CRITICAL:** Live trading is disabled by default.

To enable live trading in production:

1. Set `LIVE_TRADING_ENABLED=true` in `.env` (production only)
2. Deploy to production environment
3. Configure broker credentials (MT5/Exness)
4. Conduct thorough testing in paper trading mode
5. Get team sign-off before enabling
6. Monitor closely during deployment

**DO NOT enable live trading in development or staging.**

---

## Next Steps

1. **Explore API Docs**: Visit http://localhost:8000/docs for interactive Swagger UI
2. **Read Architecture**: See [README.md](../README.md) for system overview
3. **Configure Brokers**: Set up MT5/Exness credentials for live connections
4. **Run Backtests**: Use `/api/backtest/*` endpoints for historical analysis
5. **Monitor**: Set up logging and alerts for production deployment

---

## Support

For issues or questions:
- Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- Review [docs/RUNBOOK.md](docs/RUNBOOK.md)
- Contact: @raebby040-cpu
