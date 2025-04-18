#!/usr/bin/env bash
set -e

# Default values
export SESSION_DURATION=${SESSION_DURATION:-30}
export VERBOSE=${VERBOSE:-false}
export NODE_PORT_1=${NODE_PORT_1:-30001}
export NODE_PORT_2=${NODE_PORT_2:-30002}
export NODE_PORT_3=${NODE_PORT_3:-30003}

# Detect Docker GID
if getent group docker >/dev/null 2>&1; then
  # Use getent if available (Linux)
  DOCKER_GID=$(getent group docker | cut -d: -f3)
  echo "🔍 Detected Docker group ID: $DOCKER_GID"
elif [ -e /var/run/docker.sock ]; then
  # Fallback to stat if docker.sock exists
  DOCKER_GID=$(stat -c '%g' /var/run/docker.sock 2>/dev/null || stat -f '%g' /var/run/docker.sock 2>/dev/null)
  echo "🔍 Detected Docker group ID: $DOCKER_GID"
else
  # Default if we can't detect
  DOCKER_GID=999
  echo "⚠️ Could not detect Docker group ID, using default: $DOCKER_GID"
fi

# Export the Docker GID for compose.yml
export DOCKER_GID

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --session-duration)
      export SESSION_DURATION="$2"
      shift 2
      ;;
    --verbose)
      export VERBOSE="true"
      shift
      ;;
    --help)
      echo "Usage: $0 [options]"
      echo "Options:"
      echo "  --session-duration MINUTES  Set the session duration in minutes (default: 30)"
      echo "  --verbose                   Enable verbose logging"
      echo "  --help                      Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Run '$0 --help' for usage information"
      exit 1
      ;;
  esac
done

# Check for Docker
if ! command -v docker &> /dev/null; then
  echo "Error: Docker is not installed or not in PATH"
  exit 1
fi

# Check for Docker Compose
if ! command -v docker compose &> /dev/null; then
  echo "Error: Docker Compose is not installed or not in PATH"
  exit 1
fi

# Check for API key
if [ -z "$VIBECTL_ANTHROPIC_API_KEY" ]; then
  echo "❗ VIBECTL_ANTHROPIC_API_KEY is not set"
  read -p "Enter your Anthropic API key (starts with 'sk-ant-'): " ANTHROPIC_KEY
  if [ -z "$ANTHROPIC_KEY" ]; then
    echo "❌ No API key provided. Cannot continue."
    exit 1
  fi
  export VIBECTL_ANTHROPIC_API_KEY="$ANTHROPIC_KEY"
  echo "✅ API key set"
else
  echo "✅ Using existing VIBECTL_ANTHROPIC_API_KEY from environment"
fi

echo "Starting Chaos Monkey demo with the following configuration:"
echo "  Session duration: ${SESSION_DURATION} minutes"
echo "  Verbose mode: ${VERBOSE}"

# Start only required services: services, red-agent, blue-agent
docker compose up --build services red-agent blue-agent

# Set up trap to catch interrupts and exit signals
cleanup() {
  echo "🧹 Cleaning up containers and resources..."

  # Stop and remove containers via docker compose
  docker compose down --volumes --remove-orphans 2>/dev/null || true

  # Try to delete the kind cluster if kind is available
  if command -v kind >/dev/null 2>&1; then
    echo "☸️ Cleaning up Kind resources..."
    kind delete cluster --name chaos-monkey 2>/dev/null || true
  fi

  # Force remove any straggling kind-related containers
  echo "🐳 Checking for leftover containers..."
  for container in $(docker ps -a --filter "name=chaos-monkey" -q 2>/dev/null); do
    echo "Removing container: $container"
    docker rm -f "$container" 2>/dev/null || true
  done

  echo "✅ Cleanup completed"
}

# Set up trap to catch interrupts and exit signals
trap cleanup EXIT SIGINT SIGTERM
