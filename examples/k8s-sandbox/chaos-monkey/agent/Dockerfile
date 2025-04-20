FROM python:3.11-slim

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
    && rm -rf /var/lib/apt/lists/*

# Install kubectl
RUN curl -LO "https://dl.k8s.io/release/v1.29.1/bin/linux/amd64/kubectl" && \
    chmod +x kubectl && \
    mv kubectl /usr/local/bin/

# Install vibectl
RUN pip install vibectl llm-anthropic

# Create directory for shared files
RUN mkdir -p /config /playbooks

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

# Set the entrypoint
ENTRYPOINT ["/agent-entrypoint.sh"]
