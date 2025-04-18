FROM python:3.11-slim

WORKDIR /app

# Install necessary packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    docker.io \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Create directory for status and logs
RUN mkdir -p /app/data

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose the web server port
EXPOSE 8080

# Environment variables with defaults
ENV SESSION_DURATION=30 \
    METRICS_INTERVAL=15 \
    VERBOSE=false

# Health check
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

# Set entry point
CMD ["python", "overseer.py"]
