FROM python:3.11-slim

# Create app dir
WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application code
COPY . /app

# Expose port and run uvicorn
EXPOSE 8000

# Use the correct entry point path
CMD ["uvicorn", "fastapi_app.main:app", "--host", "0.0.0.0", "--port", "8000"]
