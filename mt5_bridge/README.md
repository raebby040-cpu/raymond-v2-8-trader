# Raymond v2.8 MT5 Execution Bridge

This service runs on the machine where the MetaTrader 5 desktop terminal
is installed.

## Safety

The bridge is DEMO-only.

Real MT5 accounts are rejected by the application.

This bridge does not enable Raymond live trading.

Raymond's backend remains responsible for:

- strategy decisions
- risk validation
- emergency stop
- execution authorization
- position reconciliation
- trade history
- live-trading safety gates

## Requirements

- Windows machine or Windows VPS
- MetaTrader 5 terminal installed
- Python 3.11
- A DEMO MT5 account
- Network access to the Raymond backend

## Installation

Open PowerShell in this directory:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
