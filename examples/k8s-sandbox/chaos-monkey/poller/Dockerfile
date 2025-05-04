FROM ubuntu:22.04

# Avoid prompts during package installations
ENV DEBIAN_FRONTEND=noninteractive

# Install required packages and kubectl
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    curl \
    docker.io \
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

# Install Python dependencies
RUN pip3 install --no-cache-dir rich

# Copy our Python script
COPY poller.py /poller.py
RUN chmod +x /poller.py

# Set up environment variables with defaults
ENV STATUS_DIR=/tmp/status

# Set the default command
CMD ["python3", "/poller.py"]
