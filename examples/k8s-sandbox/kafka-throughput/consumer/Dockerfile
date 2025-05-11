FROM golang:1.24.3-bookworm AS builder

WORKDIR /app

# Copy go mod and sum files
COPY go.mod go.sum ./

# Download dependencies
RUN go mod download

# Copy source code
COPY consumer.go ./

# Get dependencies and build the application
RUN go get ./... && \
    CGO_ENABLED=0 GOOS=linux go build -o consumer .

# Use a smaller image for the final container
FROM debian:bookworm-slim

WORKDIR /app

# Install procps for pgrep (used in healthcheck)
RUN apt-get update && apt-get install -y procps && rm -rf /var/lib/apt/lists/*

# Copy the binary from builder
COPY --from=builder /app/consumer .

CMD ["./consumer"]
