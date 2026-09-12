# RAYMOND v2.8 Broker Integration & Setup Guide

## 1. Purpose

This document describes the current broker and market-data architecture for RAYMOND v2.8.

RAYMOND is currently configured for:

- Paper trading
- Demo/sandbox validation where supported
- Read-only market-data access
- Technical analysis
- AI decision analysis
- Risk validation
- Safe deployment on Render

### Important safety status

**LIVE TRADING IS DISABLED.**

The current release does **not** implement real broker order execution.

Do not enable live trading, submit real-money orders, or place real broker credentials in source code.

The required production safety state is:

```text
LIVE_TRADING_ENABLED=false
