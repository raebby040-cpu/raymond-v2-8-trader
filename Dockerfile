FROM python:3.11-slim

WORKDIR /app

# System dependencies required to build Python packages.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first so Docker can cache this layer.
COPY backend/requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the backend application.
COPY backend/ /app/

# Copy backtesting and supporting scripts.
COPY scripts/ /app/scripts/

# Render provides PORT at runtime.
EXPOSE 8000

# IMPORTANT:
# Start through canonical_online_main.py.
#
# canonical_online_main.py loads the existing online_main application
# and installs the canonical persistent paper-trading runtime before
# FastAPI startup workers begin.
#
# Canonical paper accounting:
#   Starting balance = $1,000
#   Balance = starting balance + realized P&L
#   Equity = balance + unrealized P&L
#
# Persistent Position records are the source of truth.
#
# Live broker execution remains disabled.
CMD ["sh", "-c", "uvicorn canonical_online_main:app --host 0.0.0.0 --port ${PORT:-8000}"]
