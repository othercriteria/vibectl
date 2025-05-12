# Kafka Consumer (Go)

This is a Go implementation of the Kafka consumer for the throughput demo. It's designed to be more performant than the Python version.

## Development Setup

### Using Nix

The easiest way to get a Go development environment is using Nix:

```bash
# Enter a shell with Go and other tools
nix-shell -p go gopls gotools

# Verify Go is available
go version
```

### Managing Dependencies

The project uses Go modules for dependency management. Key files:
- `go.mod`: Declares direct dependencies and Go version
- `go.sum`: Contains cryptographic checksums of dependencies

To update dependencies:

```bash
# Update all dependencies to latest versions
go get -u ./...

# Update a specific dependency (Sarama is now maintained by IBM)
go get -u github.com/IBM/sarama

# Tidy up go.mod and go.sum
go mod tidy

# Verify dependencies
go mod verify
```

### Common Go Commands

```bash
# Build the consumer
go build

# Run tests
go test ./...

# Run the consumer
go run consumer.go

# Check for common code issues
go vet ./...

# Format code
go fmt ./...
```

## Docker Build

The Dockerfile uses a multi-stage build:
1. `golang:1.24.3-bookworm` for building
2. `debian:bookworm-slim` for the final image

To build:
```bash
docker build -t kafka-throughput-consumer .
```

## Environment Variables

The consumer can be configured using these environment variables:
- `KAFKA_BROKER`: Kafka broker address (default: "kafka:9092")
- `KAFKA_TOPIC`: Topic to consume from (default: "throughput-topic")
- `CONSUMER_GROUP_ID`: Consumer group ID (default: "kafka-throughput-consumer-group")
- `CONSUMER_CLIENT_ID`: Client ID (default: "kafka-throughput-consumer")
- `MAX_RETRIES`: Maximum connection retries (default: 5)
- `INITIAL_RETRY_DELAY_S`: Initial retry delay in seconds (default: 5)
