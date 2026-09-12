RAYMOND v2.8 - Quick Start Guide

Get the RAYMOND v2.8 trading system running safely in development or through the deployed Render service.

«Safety: RAYMOND is currently configured for paper/demo trading. Live broker trading must remain disabled.»

Prerequisites

- Python 3.11+ for local development
- Docker for containerized development
- Git for cloning the repository

---

Option 1: Local Development

Step 1: Clone the Repository

git clone https://github.com/raebby040-cpu/raymond-v2-8-trader.git
cd raymond-v2-8-trader

Step 2: Create a Virtual Environment

python -m venv .venv

macOS/Linux:

source .venv/bin/activate

Windows:

.venv\Scripts\activate

Step 3: Install Dependencies

cd backend
pip install -r requirements.txt

Step 4: Configure the Environment

From the repository root:

cp .env.example backend/.env

Edit the environment file only when development configuration is required.

Keep live trading disabled.

Step 5: Run the Development API

uvicorn fastapi_app.main:app --reload --port 8000

The development API should be available at:

http://localhost:8000

Step 6: Check the API

- API documentation: "http://localhost:8000/docs"
- Health check: "http://localhost:8000/health"

---

Option 2: Docker

Docker is the preferred way to reproduce the containerized application.

From the repository root:

Step 1: Build

docker-compose build

Step 2: Start

docker-compose up -d

Step 3: Check Health

curl http://localhost:8000/health

Step 4: View Logs

docker-compose logs -f backend

Step 5: Stop

docker-compose down

You can also use the repository startup script:

./RUN.sh

---

Production Deployment

The Render deployment uses the repository "Dockerfile".

The production application starts through:

online_main:app

The production market-data bridge is read-only and uses:

/api/online/*

The deployed service provides:

GET /health
GET /api/online/status
GET /api/online/price
GET /api/online/candlesticks
GET /api/online/indicators
GET /api/online/analysis

The online market-data bridge does not place broker orders or modify positions.

---

Testing the API

Health Check

curl http://localhost:8000/health

The response should indicate that the service is healthy.

Online Market Status

curl http://localhost:8000/api/online/status

Current XAUUSD Price

curl "http://localhost:8000/api/online/price?symbol=XAUUSD"

XAUUSD Candlesticks

curl "http://localhost:8000/api/online/candlesticks?symbol=XAUUSD&timeframe=H1&limit=60"

Technical Indicators

curl "http://localhost:8000/api/online/indicators?symbol=XAUUSD&timeframe=H1&limit=100"

Online Analysis

curl "http://localhost:8000/api/online/analysis?symbol=XAUUSD&timeframe=M15&limit=100"

---

Paper Trading

Paper/demo trading endpoints are separate from the read-only online market-data bridge.

Get Demo Status

curl http://localhost:8000/api/demo/status

Get Demo Performance

curl http://localhost:8000/api/demo/performance

Get Demo Trades

curl http://localhost:8000/api/demo/trades

Get Open Positions

curl http://localhost:8000/api/trading/positions

Paper/demo trading does not authorize real-money broker execution.

---

Emergency Stop

The emergency-stop endpoint requires the configured API key.

Example:

curl -X POST http://localhost:8000/api/admin/emergency-stop \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_emergency_api_key_here" \
  -d '{"reason":"Manual halt for testing"}'

Do not commit real API keys or broker credentials to GitHub.

---

Running Tests

From the repository root:

pytest

For coverage:

pytest --cov=app --cov-report=html

---

Troubleshooting

API does not start

Check that Python and dependencies are installed:

python --version
pip install -r backend/requirements.txt

Port 8000 is already in use

Run the application on another port:

uvicorn fastapi_app.main:app --reload --port 8001

Docker service is not responding

Check the containers:

docker-compose ps

Then inspect the backend logs:

docker-compose logs -f backend

Market data is unavailable

Check:

curl http://localhost:8000/api/online/status

The online market feed is read-only and independent of broker order execution.

---

Trading Safety

LIVE TRADING MUST REMAIN DISABLED.

The current RAYMOND v2.8 deployment is being validated before any real-money execution is considered.

Do not:

- Enable "LIVE_TRADING_ENABLED=true"
- Send real broker orders
- Connect the system to a funded trading account for execution
- Treat paper/demo results as proof of live execution readiness

The current validation path is:

Market Data
    ↓
Technical Indicators
    ↓
Strategy / AI Analysis
    ↓
Risk Controls
    ↓
Paper / Demo Trading

Real broker execution is a separate future integration step and must not be enabled during the current validation phase.

---

Next Steps

1. Verify "/health"
2. Verify "/api/online/status"
3. Verify XAUUSD price and candlestick data
4. Verify the Flutter application uses "/api/online/*"
5. Run the automated test suite
6. Validate paper/demo trading
7. Review broker integration separately before considering any live execution

---

Support

For project documentation, see:

- "README.md"
- "docs/DEPLOYMENT.md"
- "docs/BROKER_SETUP.md"
- "docs/RUNBOOK.md"

For development issues, check the repository issues and logs before making configuration changes.
