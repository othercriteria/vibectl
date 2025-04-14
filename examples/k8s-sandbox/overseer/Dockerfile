FROM alpine:3.19

# Install dependencies
RUN apk add --no-cache bash curl jq docker-cli netcat-openbsd

# Create a directory for status files with proper permissions
RUN mkdir -p /tmp/status && chmod 777 /tmp/status

# Copy overseer script
COPY overseer.sh /usr/local/bin/overseer.sh
RUN chmod +x /usr/local/bin/overseer.sh

# Set entrypoint
ENTRYPOINT ["/usr/local/bin/overseer.sh"]
