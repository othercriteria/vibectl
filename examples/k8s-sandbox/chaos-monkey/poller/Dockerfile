FROM ubuntu:22.04

# Avoid prompts during package installations
ENV DEBIAN_FRONTEND=noninteractive

# Install required packages and kubectl
RUN apt-get update && apt-get install -y \
    bash \
    curl \
    docker.io \
    iputils-ping \
    netcat-openbsd \
    jq \
    apt-transport-https \
    gnupg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install kubectl
RUN curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.29/deb/Release.key | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg && \
    echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.29/deb/ /' | tee /etc/apt/sources.list.d/kubernetes.list && \
    apt-get update && \
    apt-get install -y kubectl && \
    rm -rf /var/lib/apt/lists/*

# Copy our script
COPY poller.sh /poller.sh
RUN chmod +x /poller.sh

# Set the default command
CMD ["/poller.sh"]
