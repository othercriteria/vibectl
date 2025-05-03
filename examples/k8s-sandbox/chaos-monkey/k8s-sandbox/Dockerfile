FROM ubuntu:22.04

# Set environment variables to prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install prerequisites for adding K8s & Docker repos and necessary packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    apt-transport-https \
    ca-certificates \
    gpg \
    curl \
    gettext-base \
    netcat-openbsd && \
    # --- Add Docker GPG key & Repo ---
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    chmod a+r /etc/apt/keyrings/docker.gpg && \
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null && \
    # --- Add Kubernetes GPG key & Repo ---
    curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.30/deb/Release.key | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg && \
    echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.30/deb/ /' | tee /etc/apt/sources.list.d/kubernetes.list && \
    # --- Update apt cache again and install kubectl & docker-ce-cli ---
    apt-get update && \
    apt-get install -y --no-install-recommends kubectl docker-ce-cli && \
    # Clean up
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Kind binary
ARG KIND_VERSION=v0.23.0
RUN curl -Lo ./kind https://kind.sigs.k8s.io/dl/${KIND_VERSION}/kind-linux-amd64 && \
    chmod +x ./kind && \
    mv ./kind /usr/local/bin/kind

# Create directories
RUN mkdir -p /kubernetes /config/kube

# Copy Kubernetes manifests and entrypoint script
# COPY kubernetes/ /kubernetes/ # Removed to allow volume mounting
COPY k8s-entrypoint.sh /usr/local/bin/k8s-entrypoint.sh
RUN chmod +x /usr/local/bin/k8s-entrypoint.sh

# Set entrypoint
ENTRYPOINT ["/usr/local/bin/k8s-entrypoint.sh"]
