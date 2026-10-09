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

# Start through the canonical online runtime with user-owned
# paper-position read endpoints registered.
#
# This entry point imports canonical_online_main and preserves
# the existing online runtime and startup patches.
#
# Paper trading only:
# - Live broker execution remains disabled.
# - Position reads require authentication.
# - Position queries are filtered by the authenticated user's ID.
CMD ["sh", "-c", "uvicorn canonical_user_positions_main:app --host 0.0.0.0 --port ${PORT:-8000}"]
