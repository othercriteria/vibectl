FROM ubuntu:22.04

# Avoid prompts during package installations
ENV DEBIAN_FRONTEND=noninteractive

# Install basic requirements and python
RUN apt-get update && apt-get install -y \
    curl \
    python3.11 \
    python3.11-pip \
    python3.11-venv \
    docker.io \
    apt-transport-https \
    ca-certificates \
    gnupg \
    lsb-release \
    dirmngr \
    && rm -rf /var/lib/apt/lists/*

# Link python3 to python3.11
RUN ln -sf /usr/bin/python3.11 /usr/bin/python3 \
    && ln -sf /usr/bin/pip3.11 /usr/bin/pip3

# Install kubectl (pin to a specific version for stability)
RUN KUBECTL_VERSION="v1.28.0" \
    && curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl

# Install K3d (pin to a specific version for stability)
RUN K3D_VERSION="v5.6.0" \
    && curl -s "https://raw.githubusercontent.com/k3d-io/k3d/${K3D_VERSION}/install.sh" | bash

# Install Helm (pin to a specific version for stability)
RUN HELM_VERSION="v3.13.0" \
    && curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

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
RUN mkdir -p /home/sandbox/{.config,vibectl-src,.kube,kafka} \
    && chown -R sandbox:sandbox /home/sandbox

# Set up virtual environment as the sandbox user
USER sandbox
WORKDIR /home/sandbox
RUN python3 -m venv .venv
ENV PATH="/home/sandbox/.venv/bin:${PATH}"
RUN pip install --no-cache-dir pip setuptools wheel --upgrade
# Install vibectl dependencies - assuming installed from source mount later
# RUN pip install --no-cache-dir click pyyaml requests kubernetes

# Copy Kafka manifest and entrypoint script (late to avoid cache busting)
USER root
COPY kafka-kraft.yaml /home/sandbox/kafka/kafka-kraft.yaml
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh \
    && chown sandbox:sandbox /home/sandbox/kafka/kafka-kraft.yaml \
    && chown root:root /usr/local/bin/entrypoint.sh

# Create a Docker socket test script (from Bootstrap demo)
RUN echo '#!/bin/bash\n\
echo "Testing Docker socket connection..."\n\
if ! docker ps > /dev/null 2>&1; then\n\
  echo "Error: Cannot access Docker socket. Check that the volume mount and group permissions are correct."\n\
  exit 1\n\
fi\n\
echo "Docker socket connection successful."\n\
exec "$@"' > /usr/local/bin/docker-test.sh && \
    chmod +x /usr/local/bin/docker-test.sh

# Set working directory and user for entrypoint
USER sandbox
WORKDIR /home/sandbox

# Use the docker test script as the entrypoint wrapper
ENTRYPOINT ["/usr/local/bin/docker-test.sh", "/usr/local/bin/entrypoint.sh"]
