FROM python:3.11-slim

WORKDIR /app

# Install build dependencies, then Python packages, then remove build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    pip install --no-cache-dir kafka-python && \
    apt-get purge -y --auto-remove gcc python3-dev && \
    rm -rf /var/lib/apt/lists/*

COPY producer.py .

# Create a non-root user and switch to it
RUN useradd --create-home appuser
USER appuser

ENTRYPOINT ["python", "-u", "producer.py"]
