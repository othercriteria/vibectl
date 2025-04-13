FROM alpine:3.18

# Install required packages (minimal)
RUN apk add --no-cache \
    bash \
    curl \
    iputils

# Copy our poller script
COPY poller.sh /poller.sh
RUN chmod +x /poller.sh

# Set the default command
CMD ["/poller.sh"]
