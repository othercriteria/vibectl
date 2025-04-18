FROM ubuntu:22.04

# Avoid prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Create docker group with proper GID
ARG DOCKER_GID=999
RUN groupadd -g ${DOCKER_GID} docker 2>/dev/null || groupmod -g ${DOCKER_GID} docker 2>/dev/null || echo "Using existing docker group"

# Add current user to docker group
RUN useradd -m -s /bin/bash docker-user && usermod -aG docker docker-user || echo "User already exists"

# Install required packages
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    jq \
    vim \
    nano \
    python3 \
    python3-pip \
    git \
    htop \
    iputils-ping \
    netcat-openbsd \
    dnsutils \
    npm \
    gnupg \
    lsb-release \
    ca-certificates \
    nginx \
    apache2-utils \
    redis-server \
    docker.io \
    iproute2 \
    procps \
    gettext-base \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Install latest Kind with a specific verified version
RUN curl -Lo /usr/local/bin/kind https://kind.sigs.k8s.io/dl/v0.22.0/kind-linux-amd64 \
    && chmod +x /usr/local/bin/kind

# Install kubectl (matching Kind node version)
RUN curl -LO "https://dl.k8s.io/release/v1.29.1/bin/linux/amd64/kubectl" && \
    chmod +x kubectl && \
    mv kubectl /usr/local/bin/

# Install vibectl
RUN pip3 install vibectl llm-anthropic

# Copy entrypoint and service definitions
COPY service-entrypoint.sh /service-entrypoint.sh
COPY kubernetes/ /kubernetes/

# Make entrypoint executable
RUN chmod +x /service-entrypoint.sh

# Set up the entrypoint
ENTRYPOINT ["/service-entrypoint.sh"]
