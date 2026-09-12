RAYMOND v2.8 Deployment Guide

Deployment Status

RAYMOND v2.8 is deployed on Render.

Current safety status

- Live trading: DISABLED
- Real broker order execution: NOT IMPLEMENTED
- Paper trading: ENABLED
- Demo trading: SUPPORTED
- Public market-data bridge: ENABLED
- Production API entrypoint: "online_main:app"
- Production health endpoint: "/health"

«IMPORTANT: Do not enable live trading until broker execution, order acknowledgement, fill handling, reconciliation, failure recovery, authentication, and production safety controls have been fully implemented and tested.»

---

1. Repository

GitHub repository:

https://github.com/raebby040-cpu/raymond-v2-8-trader

Default branch:

main

---

2. Local Development

Prerequisites

- Python 3.10+
- Git
- pip
- Docker (optional)
- SQLite for local development

Clone the repository

git clone https://github.com/raebby040-cpu/raymond-v2-8-trader.git
cd raymond-v2-8-trader

Create a virtual environment

Linux/macOS:

python -m venv .venv
source .venv/bin/activate

Windows:

python -m venv .venv
.venv\Scripts\activate

Install dependencies

cd backend
pip install -r requirements.txt
cd ..

Run the main application locally

uvicorn app.main:app --reload --port 8000

Run the production-style entrypoint locally

uvicorn online_main:app --reload --port 8000

The production Docker image uses:

online_main:app

---

3. Health Check

After starting the API:

curl http://localhost:8000/health

Expected response includes:

{
  "status": "healthy",
  "live_trading_enabled": false
}

The health endpoint confirms that the API process is running.

---

4. Production Architecture

The production deployment uses:

GitHub main
    |
    v
Render
    |
    v
Dockerfile
    |
    v
online_main:app
    |
    +---- app.main
    |
    +---- /api/online/*

The public/mobile market-data layer is read-only.

The application must not use the online market-data bridge to place broker orders.

---

5. Render Configuration

Current production configuration:

Service:
raymond-v2-8-trader

Branch:
main

Runtime:
Docker

Dockerfile:
./Dockerfile

Region:
Singapore

Instances:
1

Health Check:
 /health

Auto Deploy:
Enabled

Render automatically deploys new commits pushed to "main".

After deployment, verify:

curl https://raymond-v2-8-trader.onrender.com/health

---

6. Production Market API

The public/mobile market-data contract is:

/api/online/*

Available endpoints:

GET /api/online/status
GET /api/online/price
GET /api/online/candlesticks
GET /api/online/indicators
GET /api/online/analysis

Market status

curl "https://raymond-v2-8-trader.onrender.com/api/online/status"

Gold price

curl "https://raymond-v2-8-trader.onrender.com/api/online/price?symbol=XAUUSD"

Candlesticks

curl "https://raymond-v2-8-trader.onrender.com/api/online/candlesticks?symbol=XAUUSD&timeframe=H1&limit=60"

Indicators

curl "https://raymond-v2-8-trader.onrender.com/api/online/indicators?symbol=XAUUSD&timeframe=H1&limit=100"

Analysis

curl "https://raymond-v2-8-trader.onrender.com/api/online/analysis?symbol=XAUUSD&timeframe=M15&limit=100"

---

7. Online Market API Safety

The online market API is:

READ ONLY

It must not:

- place broker orders
- modify positions
- close broker positions
- authorize live execution
- enable live trading
- send real-money orders

The online market API exists primarily to provide market information and analysis to the application.

---

8. Internal MT5 Market API

RAYMOND also contains MT5-backed internal routes under:

/api/market/*

These routes should not be confused with the public/mobile market API.

The Flutter application should use:

/api/online/*

for public market-data requests.

The internal MT5 routes should not be deleted simply because the public application uses the online bridge.

---

9. Docker

Build the production image:

docker build -t raymond-v2-8-trader .

Run locally:

docker run -p 8000:8000 \
  -e LIVE_TRADING_ENABLED=false \
  -e RAYMOND_ENV=development \
  raymond-v2-8-trader

Verify:

curl http://localhost:8000/health

---

10. Environment Configuration

Production must keep:

LIVE_TRADING_ENABLED=false

Recommended environment:

RAYMOND_ENV=production
LIVE_TRADING_ENABLED=false

Never commit secrets to GitHub.

Do not commit:

- broker passwords
- API keys
- access tokens
- database passwords
- private keys
- authentication secrets

Use secure environment variables for secrets.

---

11. Testing

Run the complete test suite:

pytest tests/ -v

Run linting where configured:

flake8 backend tests

or:

ruff check backend tests

A deployment should not proceed when critical tests are failing.

---

12. Deployment Verification

After every production deployment, check:

Health

curl "https://raymond-v2-8-trader.onrender.com/health"

Expected:

HTTP 200

Market status

curl "https://raymond-v2-8-trader.onrender.com/api/online/status"

Verify that live execution remains disabled.

The response should indicate:

live_trading_enabled = false
execution_authorized = false
broker_orders_allowed = false

Market price

curl "https://raymond-v2-8-trader.onrender.com/api/online/price?symbol=XAUUSD"

Candles

curl "https://raymond-v2-8-trader.onrender.com/api/online/candlesticks?symbol=XAUUSD&timeframe=H1&limit=60"

---

13. Flutter Application

The Flutter application uses:

https://raymond-v2-8-trader.onrender.com

Public market-data requests use:

/api/online/price
/api/online/candlesticks
/api/online/indicators
/api/online/status
/api/online/analysis

Paper trading, demo trading, journal, strategy, risk, and administrative requests remain separate API functions.

---

14. Production Safety

The following setting must remain unchanged:

LIVE_TRADING_ENABLED=false

Successful deployment does not mean that RAYMOND is ready for real-money trading.

The following are different capabilities:

Market data
    !=
AI analysis
    !=
Paper trading
    !=
Demo trading
    !=
Real broker execution

Real broker execution requires additional implementation and validation.

---

15. Real Broker Execution Status

Real broker order execution is currently:

NOT IMPLEMENTED

Do not claim that RAYMOND currently sends real orders to:

- MT5
- Exness
- any other broker

until the complete execution system has been implemented and tested.

Required future capabilities include:

- order submission
- order acknowledgement
- fill confirmation
- rejection handling
- slippage handling
- duplicate-order protection
- position reconciliation
- broker disconnect recovery
- timeout handling
- execution audit trail
- emergency stop
- authentication and authorization

---

16. Rollback

If a deployment causes a critical problem:

1. Keep live trading disabled.
2. Inspect Render deployment logs.
3. Identify the last known-good commit.
4. Redeploy the known-good version.
5. Check "/health".
6. Check "/api/online/status".
7. Confirm live trading remains disabled.
8. Confirm the Flutter application can reach the API.

Never enable live trading as part of troubleshooting.

---

17. Security Checklist

Before production trading approval:

- [ ] "LIVE_TRADING_ENABLED=false"
- [ ] No secrets committed to GitHub
- [ ] Production environment variables secured
- [ ] CORS reviewed
- [ ] Authentication reviewed
- [ ] Authorization reviewed
- [ ] Rate limiting reviewed
- [ ] Dependency security scanning completed
- [ ] Database backups verified
- [ ] Monitoring configured
- [ ] Emergency stop tested
- [ ] Broker execution implemented
- [ ] Order acknowledgement tested
- [ ] Fill handling tested
- [ ] Rejection handling tested
- [ ] Slippage handling tested
- [ ] Duplicate-order protection tested
- [ ] Position reconciliation tested
- [ ] Disconnect recovery tested
- [ ] Failure recovery tested
- [ ] Live trading approval completed

---

18. Common Problems

Health endpoint fails

Check Render logs and verify the production entrypoint:

online_main:app

Then:

curl "https://raymond-v2-8-trader.onrender.com/health"

Market data fails

Check:

curl "https://raymond-v2-8-trader.onrender.com/api/online/status"

Then:

curl "https://raymond-v2-8-trader.onrender.com/api/online/price?symbol=XAUUSD"

The online bridge depends on its upstream public market-data source.

Flutter shows no market data

Confirm that Flutter is calling:

/api/online/*

rather than depending on:

/api/market/*

for public market-data requests.

Render does not start

Verify:

Dockerfile = ./Dockerfile
Build context = repository root
Entrypoint = online_main:app
Host = 0.0.0.0
Port = ${PORT:-8000}
Health check = /health

---

19. Final Release Gate

RAYMOND v2.8 must not be considered ready for real-money trading simply because the application is deployed.

Production trading approval requires:

API health
+
reliable market data
+
Flutter integration
+
risk controls
+
paper-trading validation
+
automated tests
+
security review
+
broker execution
+
order reconciliation
+
failure recovery
+
monitoring

Until all required controls are complete:

LIVE_TRADING_ENABLED=false

must remain unchanged.

---

Support

Repository:

https://github.com/raebby040-cpu/raymond-v2-8-trader

Issues:

https://github.com/raebby040-cpu/raymond-v2-8-trader/issues

Production API:

https://raymond-v2-8-trader.onrender.com
