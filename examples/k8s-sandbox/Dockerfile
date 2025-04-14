FROM ubuntu:22.04

# Avoid prompts during package installations
ENV DEBIAN_FRONTEND=noninteractive

# Install basic requirements (only what's needed)
RUN apt-get update && apt-get install -y \
    curl \
    python3 \
    python3-pip \
    python3-venv \
    docker.io \
    netcat-openbsd \
    iproute2 \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Install kubectl directly from the binary release
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && chmod +x kubectl \
    && mv kubectl /usr/local/bin/

# Install latest Kind with a specific verified version
RUN curl -Lo /usr/local/bin/kind https://kind.sigs.k8s.io/dl/v0.22.0/kind-linux-amd64 \
    && chmod +x /usr/local/bin/kind

# Create a docker group with the same GID as the host
# We'll pass this in at build time from compose.yml
ARG DOCKER_GID=999

# Create or modify docker group to use the provided GID
RUN getent group docker >/dev/null 2>&1 && \
    groupmod -g ${DOCKER_GID} docker || \
    groupadd -g ${DOCKER_GID} docker

# Create non-root user and add to docker group
RUN useradd -ms /bin/bash sandbox
RUN usermod -aG docker sandbox

# Create directories for the challenge and Kubernetes config
RUN mkdir -p /home/sandbox/challenge /home/sandbox/.kube /home/sandbox/vibectl-src
RUN chown -R sandbox:sandbox /home/sandbox

# Copy sandbox-entrypoint.sh script and make it executable
COPY examples/k8s-sandbox/sandbox-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/sandbox-entrypoint.sh

# Switch to the non-root user
USER sandbox
WORKDIR /home/sandbox/challenge

# Ensure .kube directory has correct permissions
RUN mkdir -p /home/sandbox/.kube && chmod 700 /home/sandbox/.kube

# Copy just the requirements/setup files first for better caching
COPY --chown=sandbox:sandbox pyproject.toml README.md setup.* /home/sandbox/vibectl-src/

# Set up virtual environment (will be cached if requirements don't change)
RUN python3 -m venv /home/sandbox/.venv \
    && . /home/sandbox/.venv/bin/activate \
    && pip install --no-cache-dir pip setuptools wheel --upgrade \
    && pip install --no-cache-dir llm-anthropic \
    && python -m llm install llm-anthropic

# Now copy the rest of the source code (this layer will change often)
COPY --chown=sandbox:sandbox . /home/sandbox/vibectl-src/

# Install vibectl in development mode
RUN . /home/sandbox/.venv/bin/activate \
    && cd /home/sandbox/vibectl-src \
    && pip install --no-cache-dir . || \
    ( echo "Trying modern editable install..." && \
      pip install --no-cache-dir -e . --config-settings editable_mode=compat )

# Ensure PATH includes venv binaries
ENV PATH="/home/sandbox/.venv/bin:${PATH}"

# Health check ensures cluster is ready before starting dependencies
HEALTHCHECK --interval=10s --timeout=10s --start-period=120s --retries=15 \
    CMD test -f /tmp/kind-kubeconfig && kubectl --kubeconfig=/tmp/kind-kubeconfig get nodes >/dev/null 2>&1 || exit 1

# Set the entrypoint to the sandbox-entrypoint script
ENTRYPOINT ["/usr/local/bin/sandbox-entrypoint.sh"]
