FROM ubuntu:22.04

# Avoid prompts during package installations
ENV DEBIAN_FRONTEND=noninteractive

# Install required packages
RUN apt-get update && apt-get install -y \
    bash \
    curl \
    docker.io \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# Copy our script
COPY poller.sh /poller.sh
RUN chmod +x /poller.sh

# Set the default command
CMD ["/poller.sh"]
