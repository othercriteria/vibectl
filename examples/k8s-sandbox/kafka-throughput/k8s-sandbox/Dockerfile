FROM ubuntu:22.04

# Avoid prompts during package installations
ENV DEBIAN_FRONTEND=noninteractive

# Install basic requirements and python
RUN apt-get update && apt-get install -y \
    curl \
    python3.11 \
    python3.11-venv \
    docker.io \
    apt-transport-https \
    ca-certificates \
    gnupg \
    lsb-release \
    dirmngr \
    gettext \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Link python3 to python3.11
RUN ln -sf /usr/bin/python3.11 /usr/bin/python3 \
    && ln -sf /usr/bin/pip3.11 /usr/bin/pip3

# Install kubectl (pin to a specific version for stability)
RUN KUBECTL_VERSION="v1.32.4" \
    && curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl

# Install K3d (pin to a specific version for stability)
RUN K3D_VERSION="v5.8.3" \
    && curl -s "https://raw.githubusercontent.com/k3d-io/k3d/${K3D_VERSION}/install.sh" | bash

# Create a docker group with the same GID as the host
# Pass this in at build time from compose.yml
ARG DOCKER_GID=999

# Create or modify docker group to use the provided GID
RUN getent group docker >/dev/null 2>&1 && \
    groupmod -g ${DOCKER_GID} docker || \
    groupadd -g ${DOCKER_GID} docker

# Create non-root user 'sandbox' and add to docker group
RUN useradd -ms /bin/bash sandbox \
    && usermod -aG docker sandbox

# Create home directory and set permissions
RUN mkdir -p /home/sandbox/.config \
             /home/sandbox/vibectl-src \
             /home/sandbox/.kube \
             /home/sandbox/kafka \
    && chown -R sandbox:sandbox /home/sandbox

# Now switch to the sandbox user
USER sandbox
WORKDIR /home/sandbox

# Set up venv and install packages as sandbox user
RUN python3 -m venv .venv
ENV PATH="/home/sandbox/.venv/bin:${PATH}"
RUN pip install --no-cache-dir pip setuptools wheel --upgrade
RUN pip install --no-cache-dir \
    kubernetes \
    llm \
    llm-anthropic \
    requests \
    prometheus_client # Add required llm plugins

# Entrypoint runs as sandbox user, executed with bash
ENTRYPOINT ["bash", "/usr/local/bin/entrypoint.sh"]
