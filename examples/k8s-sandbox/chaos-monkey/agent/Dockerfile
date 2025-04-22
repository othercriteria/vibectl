FROM python:3.11-slim

# Build arguments for package versions
ARG VIBECTL_VERSION="0.4.1"
ARG LLM_ANTHROPIC_VERSION="0.15.1"
ARG ANTHROPIC_SDK_VERSION="0.49.0"
ARG LLM_VERSION="0.24.2"

# Install required packages
RUN apt-get update && apt-get install -y \
    curl \
    jq \
    less \
    vim \
    netcat-openbsd \
    procps \
    dnsutils \
    iputils-ping \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install kubectl
RUN curl -LO "https://dl.k8s.io/release/v1.29.1/bin/linux/amd64/kubectl" && \
    chmod +x kubectl && \
    mv kubectl /usr/local/bin/

# Create source directory for the vibectl repo and shared files
RUN mkdir -p /vibectl-src /config /playbooks
WORKDIR /

# Copy unified entrypoint script
COPY agent/agent-entrypoint.sh /agent-entrypoint.sh

# Make entrypoint executable
RUN chmod +x /agent-entrypoint.sh

# Default environment variables (can be overridden)
ENV VIBECTL_MODEL="claude-3.7-sonnet"
ENV MEMORY_MAX_CHARS=2000
ENV ACTION_PAUSE_TIME=30
ENV AGENT_ROLE=blue
ENV AGENT_NAME=defender
ENV KUBE_CONFIG=/config/kube/config
ENV INITIAL_DELAY=0
ENV USE_STABLE_VERSIONS=false
ENV VIBECTL_VERSION=${VIBECTL_VERSION}
ENV LLM_ANTHROPIC_VERSION=${LLM_ANTHROPIC_VERSION}
ENV ANTHROPIC_SDK_VERSION=${ANTHROPIC_SDK_VERSION}
ENV LLM_VERSION=${LLM_VERSION}

# Set the entrypoint
ENTRYPOINT ["/agent-entrypoint.sh"]
