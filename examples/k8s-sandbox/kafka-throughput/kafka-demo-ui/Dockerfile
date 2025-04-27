# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install dependencies
COPY requirements.txt .
# Install docker library along with other requirements
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    pip install --no-cache-dir -r requirements.txt docker && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Add non-root user and group for security
ARG DOCKER_GID=999 # Default GID
RUN groupadd -g ${DOCKER_GID} docker-host-group || echo "Group ${DOCKER_GID} may already exist" && \
    groupadd -r ui-group && \
    useradd -r -g ui-group -G docker-host-group ui-user

# Copy application code
COPY --chown=ui-user:ui-group . .

# Switch to non-root user
USER ui-user

# Expose port
EXPOSE 8081

# Define environment variable defaults (can be overridden)
ENV STATUS_DIR=/tmp/status
ENV CHECK_INTERVAL_S=5
ENV LATENCY_FILE_NAME=latency.txt

# Run the application
CMD ["python", "app.py"]
