FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy only the files needed for pip install -e .
# This ensures Docker layer caching works properly and builds are deterministic
COPY pyproject.toml LICENSE README.md ./
COPY vibectl/ vibectl/

# Install vibectl in development mode to get the latest changes
RUN pip install -e .

# Create directories for certificates and config
RUN mkdir -p /etc/vibectl/config /etc/vibectl/secret /etc/vibectl/certs

# Expose the gRPC port
EXPOSE 50051

# Set default command
CMD ["vibectl-server", "serve", "--config", "/etc/vibectl/config/config.yaml"]
