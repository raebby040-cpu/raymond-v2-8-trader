# RAYMOND v2.8 Emergency Runbook

## ⚠️ CRITICAL: Emergency Stop Procedure

### Situation: System Out of Control

**Immediate Actions (Next 30 seconds):**

1. **Activate Emergency Stop**
   ```bash
   curl -X POST http://localhost:8000/api/admin/emergency-stop \
     -H "Authorization: Bearer $EMERGENCY_API_KEY"
   ```

2. **Kill the Process**
   ```bash
   pkill -f "uvicorn app.main"
   ```

3. **Notify Team**
   - Slack: #trading-alerts
   - Email: team@example.com
   - Phone: On-call number

**Within 5 minutes:**

4. **Verify All Positions Closed**
   ```bash
   # Check broker account
   # Confirm no open positions in MT5/Exness
   ```

5. **Backup Database**
   ```bash
   cp raymond.db raymond.db.emergency-$(date +%s)
   ```

6. **Review Logs**
   ```bash
   tail -100 logs/raymond.log
   grep ERROR logs/raymond.log
   ```

---

## 🔴 Critical Issues

### Issue: Market Feed Disconnected

**Symptoms:**
- No price updates for > 5 minutes
- `market_feed_healthy: false` in /api/admin/status
- Stale-market alert triggered

**Action:**
1. Check internet connection
2. Verify market data provider is online
3. Check API rate limits (Alpha Vantage: 5 req/min)
4. Restart market data provider

```bash
# Restart with fresh connection
sudo systemctl restart raymond-market-feed
```

5. If still disconnected after 5 min → **EMERGENCY STOP**

---

### Issue: Broker Connection Lost

**Symptoms:**
- Cannot place orders
- `broker_connected: false` in status
- Connection timeout errors in logs

**Action:**
1. Check broker status page
2. Verify credentials are correct
3. Check network connectivity
4. Reconnect to broker:

```bash
# Restart broker adapter
Python -c "from app.brokers import MT5BrokerAdapter; adapter = MT5BrokerAdapter(); await adapter.connect()"
```

5. If reconnection fails → **EMERGENCY STOP**

---

### Issue: Large Unexpected Loss

**Symptoms:**
- Daily P&L < -$500 (or your threshold)
- `daily_loss_limit_exceeded` alert

**Action:**
1. Close all open positions immediately
   ```bash
   curl -X POST http://localhost:8000/api/trading/close-position?position_id=ALL
   ```

2. Review what happened
   ```bash
   tail -50 logs/raymond.log | grep -A5 -B5 "TRADE"
   ```

3. Check for market gaps or slippage
4. Verify risk parameters were enforced
5. Do **NOT** resume trading until root cause found

---

### Issue: Database Corruption

**Symptoms:**
- `sqlite3.DatabaseError`
- Cannot query trades table
- Application crashes on startup

**Action:**
1. Stop application immediately
2. Restore from backup
   ```bash
   cp raymond.db.backup raymond.db
   ```

3. Verify database integrity
   ```bash
   sqlite3 raymond.db "PRAGMA integrity_check;"
   ```

4. Restart application
5. Run full backtest to verify

---

## 🟡 Warning Issues

### Issue: High Latency

**Symptoms:**
- API response time > 2 seconds
- Order fills delayed > 5 seconds
- Streaming lag > 10 seconds

**Action:**
1. Check system resources
   ```bash
   top
   df -h
   ```

2. Reduce concurrent operations
3. Scale up resources if needed
4. Monitor latency with:
   ```bash
   curl -w "\nTime: %{time_total}\n" http://localhost:8000/health
   ```

---

### Issue: Memory Leak

**Symptoms:**
- Memory usage steadily increasing
- `free` shows decreasing available RAM
- Process slowdown over time

**Action:**
1. Check memory usage
   ```bash
   ps aux | grep uvicorn
   ```

2. Identify memory consumer
   ```bash
   python -m tracemalloc app/main.py
   ```

3. Restart application
   ```bash
   docker-compose restart api
   ```

4. Monitor for recurrence

---

### Issue: API Rate Limit Hit

**Symptoms:**
- HTTP 429 (Too Many Requests) errors
- Market data provider returning 429

**Action:**
1. Identify which provider (Alpha Vantage: 5/min)
2. Implement exponential backoff
3. Increase request interval
4. Switch to backup provider if available

---

## 🟢 Common Issues

### Issue: Order Not Filling

**Symptoms:**
- Order placed but status still "PENDING"
- Not showing in broker account

**Action:**
1. Verify broker connection
2. Check spread — may be too wide
3. Manual fill via broker platform
4. Cancel and retry

---

### Issue: Portfolio Risk Too High

**Symptoms:**
- Warning: "Portfolio risk: 6.5%" (threshold: 5%)
- Cannot open new positions

**Action:**
1. Close smallest/most profitable position
2. Wait for risk to drop below threshold
3. Check risk parameter settings
4. Reduce position sizes in strategy

---

## Recovery Checklist

After any critical incident:

- [ ] All open positions closed
- [ ] Database backed up
- [ ] Logs reviewed and documented
- [ ] Root cause identified
- [ ] Fix implemented and tested
- [ ] Team notified
- [ ] Post-mortem scheduled
- [ ] Preventive measures added

## Contact Information

**On-Call Engineer:**
- Phone: +1-555-RAYMOND
- Email: oncall@example.com
- Slack: @raymond-oncall

**Broker Support:**
- MT5: support@yourbroker.com
- Exness: support@exness.com

**System Owner:**
- @raebby040-cpu (GitHub)
- Lead Engineer: @your-name

---

**Last Updated:** 2026-09-08  
**Version:** 2.8  
**Status:** ACTIVE
