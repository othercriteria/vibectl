FROM ubuntu:22.04

RUN apt-get update && \
    apt-get install -y curl jq netcat-openbsd && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create directory structure
RUN mkdir -p /usr/local/bin/config

# Copy scripts
COPY overseer.sh /usr/local/bin/
COPY config/ /usr/local/bin/config/

# Make scripts executable
RUN chmod +x /usr/local/bin/overseer.sh /usr/local/bin/config/challenge-config.sh

# Set working directory
WORKDIR /usr/local/bin

# Set entrypoint
ENTRYPOINT ["/usr/local/bin/overseer.sh"]
