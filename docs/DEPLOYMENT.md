# RAYMOND v2.8 Deployment Guide

## Deployment Status

RAYMOND v2.8 is currently deployed on Render.

**Production safety status:**
- Live trading: **DISABLED**
- Real broker order execution: **NOT IMPLEMENTED**
- Paper trading: **ENABLED**
- Demo trading: **SUPPORTED**
- Public market-data bridge: **ENABLED**
- Market-data bridge: Yahoo Finance public chart feed
- Production API entrypoint: `online_main:app`
- Production health endpoint: `/health`

> **IMPORTANT:** Do not enable live trading or connect real-money execution until broker execution, order acknowledgement, reconciliation, recovery handling, authentication, and production safety controls have been fully validated.

---

## 1. Repository

GitHub repository:

https://github.com/raebby040-cpu/raymond-v2-8-trader

Default branch:

```text
main
