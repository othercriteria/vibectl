FROM ubuntu:22.04

# Avoid prompts during package installations
ENV DEBIAN_FRONTEND=noninteractive

# Install basic requirements
RUN apt-get update && apt-get install -y software-properties-common && add-apt-repository ppa:deadsnakes/ppa && apt-get update && apt-get install -y \
    curl \
    python3.11 \
    python3.11-venv \
    docker.io \
    apt-transport-https \
    ca-certificates \
    gnupg \
    lsb-release \
    dirmngr \
    && rm -rf /var/lib/apt/lists/*

# Ensure pip is installed for python3.11
RUN python3.11 -m ensurepip --upgrade

# Install Docker Buildx (official method)
RUN mkdir -p ~/.docker/cli-plugins/ && \
    curl -SL https://github.com/docker/buildx/releases/latest/download/buildx-linux-amd64 -o ~/.docker/cli-plugins/docker-buildx && \
    chmod +x ~/.docker/cli-plugins/docker-buildx

# Install pyyaml for the Helm post-renderer (system Python)
RUN python3.11 -m pip install --no-cache-dir pyyaml

# Install kubectl
RUN curl -fsSL https://dl.k8s.io/release/v1.28.0/bin/linux/amd64/kubectl -o /usr/local/bin/kubectl && \
    chmod +x /usr/local/bin/kubectl

# Install K3d
RUN curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash

# Install Helm
RUN curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Create a docker group with the same GID as the host
# Pass this in at build time from compose.yml
ARG DOCKER_GID=999

# Create or modify docker group to use the provided GID
RUN getent group docker >/dev/null 2>&1 && \
    groupmod -g ${DOCKER_GID} docker || \
    groupadd -g ${DOCKER_GID} docker

# Create non-root user and add to docker group
RUN useradd -ms /bin/bash bootstrap
RUN usermod -aG docker bootstrap

# Create directories for the environment
RUN mkdir -p /home/bootstrap/{ollama-models,.config,vibectl-src,.kube}
RUN chown -R bootstrap:bootstrap /home/bootstrap

# Set up virtual environment
RUN python3.11 -m venv /home/bootstrap/.venv \
    && . /home/bootstrap/.venv/bin/activate \
    && pip install --no-cache-dir pip setuptools wheel --upgrade \
    && pip install --no-cache-dir pyyaml

# llm-ollama will be installed in entrypoint script depending on USE_STABLE_VERSIONS

# Ensure PATH includes venv binaries
ENV PATH="/home/bootstrap/.venv/bin:${PATH}"

# Set default environment variables
ENV USE_STABLE_VERSIONS=false
ENV VIBECTL_VERSION=0.5.0
ENV LLM_VERSION=0.24.2
ENV K3D_CLUSTER_NAME=vibectl-demo

# Copy the Ollama model Dockerfile for in-container builds (late to avoid cache busting)
COPY Dockerfile.ollama-model /home/bootstrap/Dockerfile.ollama-model
# Copy entrypoint script and make it executable (late to avoid cache busting)
COPY bootstrap-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/bootstrap-entrypoint.sh

# Create a Docker socket test script
RUN echo '#!/bin/bash\n\
echo "Testing Docker socket connection..."\n\
if ! docker ps > /dev/null 2>&1; then\n\
  echo "Error: Cannot access Docker socket. Check that the volume mount and group permissions are correct."\n\
  exit 1\n\
fi\n\
echo "Docker socket connection successful."\n\
exec "$@"' > /usr/local/bin/docker-test.sh && \
    chmod +x /usr/local/bin/docker-test.sh

# Use the docker test script as the entrypoint wrapper
ENTRYPOINT ["/usr/local/bin/docker-test.sh", "/usr/local/bin/bootstrap-entrypoint.sh"]
