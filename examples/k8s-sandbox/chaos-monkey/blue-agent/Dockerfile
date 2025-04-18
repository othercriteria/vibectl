FROM python:3.11-slim

# Install required packages
RUN apt-get update && apt-get install -y \
    curl \
    jq \
    less \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Install kubectl
RUN curl -LO "https://dl.k8s.io/release/v1.29.1/bin/linux/amd64/kubectl" && \
    chmod +x kubectl && \
    mv kubectl /usr/local/bin/

# Install vibectl
RUN pip install vibectl llm-anthropic

# Copy entrypoint and instructions
COPY blue-agent/agent-entrypoint.sh /agent-entrypoint.sh
COPY blue-agent/memory-init.txt /memory-init.txt
COPY defense-playbook.md /defense-playbook.md
COPY blue-agent/custom-instructions.txt /custom-instructions.txt

# Make entrypoint executable
RUN chmod +x /agent-entrypoint.sh

# Set up environment
ENV VIBECTL_MODEL="claude-3.7-sonnet"
ENV MEMORY_MAX_CHARS=2000
ENV ACTION_PAUSE_TIME=30

# Set the entrypoint
ENTRYPOINT ["/agent-entrypoint.sh"]
