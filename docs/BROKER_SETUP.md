# RAYMOND v2.8 Broker Setup Guide

## MetaTrader 5 (MT5) Setup

### Prerequisites
- MT5 terminal installed (Windows/Linux)
- Broker account with MetaTrader 5 support
- Demo or live account credentials

### Connection Setup

#### Step 1: Install MetaTrader5 Python Package
```bash
pip install MetaTrader5
```

#### Step 2: Configure Environment Variables
```bash
# .env
MT5_LOGIN=123456789
MT5_PASSWORD=your-password
MT5_SERVER=BrokerName-MT5  # Get from your broker
MT5_ACCOUNT_TYPE=demo  # or live
```

#### Step 3: Test Connection
```python
from app.brokers import MT5BrokerAdapter
import asyncio

async def test():
    adapter = MT5BrokerAdapter()
    connected = await adapter.connect()
    if connected:
        info = await adapter.get_account_info()
        print("Connected:", info)
    else:
        print("Connection failed")

asyncio.run(test())
```

#### Step 4: Place Test Order
```python
order_data = {
    "symbol": "XAUUSD",
    "order_type": "market",
    "direction": "buy",
    "quantity": 0.1
}
result = await adapter.place_order(order_data)
print("Order result:", result)
```

### Common Issues

**Issue:** "MetaTrader5 not initialized"
- Solution: Ensure MT5 terminal is running and logged in

**Issue:** "Login failed"
- Solution: Verify credentials and that account is not locked

**Issue:** "Connection timeout"
- Solution: Check network connectivity and broker server status

---

## Exness Setup

### Prerequisites
- Exness account (https://exness.com)
- API token generated from Exness dashboard
- Account type (demo or live)

### Connection Setup

#### Step 1: Generate API Token
1. Log in to Exness dashboard
2. Go to API Management
3. Create new API token
4. Copy token (you won't see it again)

#### Step 2: Configure Environment Variables
```bash
# .env
EXNESS_TOKEN=your-api-token-here
EXNESS_ACCOUNT_ID=your-account-id
EXNESS_ACCOUNT_TYPE=demo  # or live
```

#### Step 3: Test Connection
```python
from app.brokers import ExnessBrokerAdapter
import asyncio

async def test():
    adapter = ExnessBrokerAdapter()
    connected = await adapter.connect()
    if connected:
        info = await adapter.get_account_info()
        print("Connected:", info)
    else:
        print("Connection failed")

asyncio.run(test())
```

#### Step 4: Place Test Order
```python
order_data = {
    "symbol": "XAUUSD",
    "order_type": "market",
    "direction": "buy",
    "quantity": 0.1
}
result = await adapter.place_order(order_data)
print("Order result:", result)
```

### API Rate Limits
- **Requests per minute:** 60
- **Burst limit:** 10 requests per second
- **Implement exponential backoff for retries**

### Common Issues

**Issue:** "Invalid API token"
- Solution: Regenerate token and update .env

**Issue:** "Account not found"
- Solution: Verify account ID matches Exness dashboard

**Issue:** "Insufficient balance"
- Solution: Check account balance before placing orders

---

## Paper Trading Mode (Default)

### Configuration
```bash
# .env
LIVE_TRADING_ENABLED=false  # Default
```

### How It Works
1. All orders are simulated
2. Fills are instant at current market price
3. Position tracking is in-memory
4. No real money is risked
5. All trades are logged to database

### Testing Paper Trading
```bash
# 1. Start server
uvicorn app.main:app --reload

# 2. Place paper trade
curl -X POST http://localhost:8000/api/trading/place-order \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "XAUUSD",
    "order_type": "market",
    "direction": "buy",
    "quantity": 0.5
  }'

# 3. Check positions
curl http://localhost:8000/api/trading/positions

# 4. Close position
curl -X POST http://localhost:8000/api/trading/close-position?position_id=POS-001
```

---

## Switching to Live Trading (⚠️ CRITICAL)

### Prerequisites
- ✅ Comprehensive testing completed
- ✅ All safety checks passed
- ✅ Emergency stop mechanism verified
- ✅ Risk parameters validated
- ✅ Data backup created
- ✅ Team approval obtained

### Step 1: Backup Everything
```bash
# Backup database
cp raymond.db raymond.db.backup-$(date +%s)

# Export trade journal
sqlite3 raymond.db "SELECT * FROM trades;" > trades_backup.csv
```

### Step 2: Update Environment
```bash
# .env
LIVE_TRADING_ENABLED=true  # ⚠️ CHANGE ONLY AFTER APPROVAL
LIVE_ACCOUNT_TYPE=live
```

### Step 3: Verify Configuration
```bash
# Check that trading is still restricted
curl http://localhost:8000/api/admin/status | jq '.live_trading_enabled'
```

### Step 4: Execute with Monitoring
```bash
# 1. Monitor logs in real-time
tail -f logs/raymond.log

# 2. Watch positions
watch -n 5 'curl http://localhost:8000/api/trading/positions'

# 3. Have emergency stop ready
# Endpoint: POST /api/admin/emergency-stop
```

### Step 5: Gradual Rollout
- Start with small position sizes (0.01-0.05 lots)
- Monitor for 24+ hours
- Gradually increase position size
- Document all trades and P&L

### Emergency Shutdown
```bash
# Immediately stop all executions
curl -X POST http://localhost:8000/api/admin/emergency-stop

# This will:
# 1. Block all new orders
# 2. Close all open positions
# 3. Set LIVE_TRADING_ENABLED=false
# 4. Log incident for audit
```

---

## Monitoring & Alerts

### Health Checks
```bash
# API health
curl http://localhost:8000/health

# Broker connection status
curl http://localhost:8000/api/admin/status

# Market data freshness
curl http://localhost:8000/api/market/price
```

### Alert Triggers
- Market data stale (no update > 5 minutes)
- Broker connection lost
- Daily loss limit exceeded
- Position risk exceeds threshold
- API rate limit approaching

### Automated Response
- Log to Slack/Email
- Trigger emergency stop if critical
- Notify on-call engineer

---

## Maintenance

### Daily Tasks
- [ ] Check logs for errors
- [ ] Verify all positions closed
- [ ] Review trade journal
- [ ] Confirm database backup

### Weekly Tasks
- [ ] Update API tokens if needed
- [ ] Review P&L and strategy metrics
- [ ] Run backtest with latest data
- [ ] Check security vulnerabilities

### Monthly Tasks
- [ ] Rotate API credentials
- [ ] Update dependencies
- [ ] Audit broker statements
- [ ] Full system test

---

## Support & Resources

- **MT5 Documentation:** https://www.metatrader5.com/en/terminal/help
- **Exness API Docs:** https://www.exness.com/api-documentation
- **Issue Tracker:** https://github.com/raebby040-cpu/raymond-v2-8-trader/issues
