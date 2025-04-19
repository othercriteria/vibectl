FROM ubuntu:22.04

# Avoid prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Create docker group with proper GID
ARG DOCKER_GID=999
RUN groupadd -g ${DOCKER_GID} docker 2>/dev/null || groupmod -g ${DOCKER_GID} docker 2>/dev/null || echo "Using existing docker group"

# Add current user to docker group
RUN useradd -m -s /bin/bash docker-user && usermod -aG docker docker-user || echo "User already exists"

# Install required packages - only what's necessary for running kind and kubectl
RUN apt-get update && apt-get install -y \
    curl \
    docker.io \
    iproute2 \
    netcat-openbsd \
    dnsutils \
    jq \
    gettext-base \
    net-tools \
    procps \
    ca-certificates \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Install kind
RUN curl -Lo /usr/local/bin/kind https://kind.sigs.k8s.io/dl/v0.22.0/kind-linux-amd64 \
    && chmod +x /usr/local/bin/kind

# Install kubectl (matching Kind node version)
RUN curl -LO "https://dl.k8s.io/release/v1.29.1/bin/linux/amd64/kubectl" && \
    chmod +x kubectl && \
    mv kubectl /usr/local/bin/

# Copy entrypoint and service definitions
COPY k8s-entrypoint.sh /k8s-entrypoint.sh
COPY kubernetes/ /kubernetes/

# Make entrypoint executable
RUN chmod +x /k8s-entrypoint.sh

# Set up the entrypoint
ENTRYPOINT ["/k8s-entrypoint.sh"]
