FROM python:3.11-slim

# Create application directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies
COPY requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy Raymond backend source
COPY . /app

# Runtime port
EXPOSE 8000

# RAYMOND v2.8 online entrypoint
# Uses the hosting platform's PORT when supplied.
# Live trading remains disabled by the application safety controls.
CMD ["sh", "-c", "uvicorn online_main:app --host 0.0.0.0 --port ${PORT:-8000}"]
