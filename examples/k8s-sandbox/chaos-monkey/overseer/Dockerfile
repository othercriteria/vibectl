FROM node:18-slim AS frontend-builder

WORKDIR /app/frontend

# Copy frontend files
COPY frontend/ ./

# Install dependencies
RUN npm install

# Build the frontend
RUN npm run build

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    docker.io \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Create directory for status and logs
RUN mkdir -p /app/data /app/static

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Copy the React frontend build files and restructure to make paths simpler
COPY --from=frontend-builder /app/frontend/build/ /app/frontend_build/
RUN cp /app/frontend_build/index.html /app/static/ && \
    cp /app/frontend_build/asset-manifest.json /app/static/ && \
    cp /app/frontend_build/manifest.json /app/static/ && \
    cp -r /app/frontend_build/static/* /app/static/

# Expose the web server port
EXPOSE 8080

# Environment variables with defaults
ENV SESSION_DURATION=30 \
    METRICS_INTERVAL=15 \
    VERBOSE=false \
    PORT=8080 \
    HOST=0.0.0.0 \
    DATA_DIR=/app/data

# Health check
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

# Set entry point
CMD ["python", "overseer.py"]
