RAYMOND v2.8 Pull Request Template

Summary

<!-- Briefly describe what this pull request changes. -->Change Type

Select all that apply:

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor
- [ ] Performance improvement
- [ ] Documentation
- [ ] Testing
- [ ] Security
- [ ] Configuration
- [ ] Deployment
- [ ] Flutter/mobile
- [ ] Backend/API
- [ ] Trading strategy
- [ ] Risk management
- [ ] Market data
- [ ] Paper trading
- [ ] Demo trading
- [ ] Broker integration

---

What Changed

<!-- Describe the important changes in this pull request. -->Backend

<!-- Describe backend/API changes, if any. -->Flutter

<!-- Describe Flutter/mobile changes, if any. -->Trading / Strategy

<!-- Describe strategy or trading logic changes, if any. -->Risk

<!-- Describe risk-management changes, if any. -->Market Data

<!-- Describe market-data changes, if any. -->Deployment

<!-- Describe Render/Docker/configuration changes, if any. -->---

API Changes

If API endpoints changed, list them here.

Public Market API

The production/mobile market-data contract is:

/api/online/*

Relevant endpoints:

GET /api/online/status
GET /api/online/price
GET /api/online/candlesticks
GET /api/online/indicators
GET /api/online/analysis

Internal API

Internal MT5-backed routes may use:

/api/market/*

Do not treat internal MT5 routes as the public Flutter market-data contract.

---

Safety Check

RAYMOND must remain in safe mode unless a separately approved production process explicitly changes this.

Current required setting:

LIVE_TRADING_ENABLED=false

Confirm:

- [ ] Live trading remains disabled
- [ ] No real-money broker orders are enabled
- [ ] No real broker positions can be modified by this change
- [ ] Paper trading remains safe
- [ ] Demo trading remains safe
- [ ] Risk controls remain active
- [ ] No emergency-stop protections were bypassed

---

Broker Execution

If this pull request touches broker integration:

- [ ] No live orders are sent accidentally
- [ ] Order acknowledgement is handled
- [ ] Fill status is handled
- [ ] Rejections are handled
- [ ] Timeouts are handled
- [ ] Duplicate orders are prevented
- [ ] Broker disconnects are handled
- [ ] Position reconciliation is handled
- [ ] Execution events are logged

If real broker execution is not implemented, state:

Real broker execution is not implemented.

---

Testing

Automated Tests

- [ ] "pytest tests/ -v"
- [ ] Backend tests pass
- [ ] API tests pass
- [ ] Risk tests pass
- [ ] Strategy tests pass
- [ ] Market-data tests pass
- [ ] Paper-trading tests pass
- [ ] Relevant Flutter tests pass

Manual Tests

- [ ] "/health" returns HTTP 200
- [ ] "/api/online/status" responds
- [ ] "/api/online/price" responds
- [ ] "/api/online/candlesticks" responds
- [ ] "/api/online/indicators" responds
- [ ] "/api/online/analysis" responds when applicable
- [ ] Flutter dashboard loads market data when applicable
- [ ] No live broker order was generated

---

Render Deployment

For changes intended for production:

- [ ] Changes are committed to "main"
- [ ] Render auto-deployment is enabled
- [ ] Deployment completed successfully
- [ ] "/health" verified after deployment
- [ ] "/api/online/status" verified after deployment
- [ ] Logs reviewed for startup errors
- [ ] Live trading remains disabled

Production service:

raymond-v2-8-trader

Production URL:

https://raymond-v2-8-trader.onrender.com

Production entrypoint:

online_main:app

Health check:

/health

---

Security

- [ ] No passwords committed
- [ ] No API keys committed
- [ ] No broker credentials committed
- [ ] No authentication tokens committed
- [ ] No private keys committed
- [ ] Secrets use environment variables or secure secret storage
- [ ] CORS changes reviewed
- [ ] Authentication changes reviewed
- [ ] Authorization changes reviewed
- [ ] Dependencies reviewed

---

Database

If database changes are included:

- [ ] Migration included
- [ ] Migration tested locally
- [ ] Existing data compatibility checked
- [ ] Backup requirement identified
- [ ] Rollback procedure considered

---

Documentation

- [ ] README updated if necessary
- [ ] Deployment documentation updated if necessary
- [ ] API documentation updated if necessary
- [ ] Broker documentation updated if necessary
- [ ] Release notes updated if necessary

---

Screenshots / Logs

<!-- Add screenshots or relevant log output when useful. -->---

Risk Assessment

Risk Level

- [ ] Low
- [ ] Medium
- [ ] High
- [ ] Critical

Why?

<!-- Explain the potential impact of this change. -->---

Rollback Plan

<!-- Explain how this change can be reverted safely. -->Minimum rollback requirements:

1. Keep live trading disabled.
2. Revert to the last known-good version.
3. Verify "/health".
4. Verify "/api/online/status".
5. Confirm "LIVE_TRADING_ENABLED=false".

---

Final Approval

Before merging:

- [ ] Code reviewed
- [ ] Tests pass
- [ ] Deployment impact reviewed
- [ ] Security reviewed where applicable
- [ ] Trading-risk impact reviewed where applicable
- [ ] No accidental live trading path introduced
- [ ] Documentation is accurate
- [ ] Rollback plan is understood

---

Important Trading Safety Statement

RAYMOND v2.8 must not be considered approved for real-money trading solely because:

- the API is online
- the Flutter application works
- market data is available
- AI analysis works
- paper trades work
- demo trades work
- Render deployment succeeds

Real-money trading requires a separately validated broker-execution lifecycle with order acknowledgement, fill/rejection handling, reconciliation, failure recovery, security controls, monitoring, and explicit approval.

Until that approval exists:

LIVE_TRADING_ENABLED=false
