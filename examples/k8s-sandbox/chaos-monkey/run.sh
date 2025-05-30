#!/usr/bin/env bash

# Aggressive failure modes
set -euo pipefail
IFS=$'\n\t'

# Default values
export PASSIVE_DURATION=${PASSIVE_DURATION:-5}
export ACTIVE_DURATION=${ACTIVE_DURATION:-25}
export VIBECTL_MODEL=${VIBECTL_MODEL:-claude-3.7-sonnet}
export VERBOSE=${VERBOSE:-false}
export USE_STABLE_VERSIONS=${USE_STABLE_VERSIONS:-false}

# Define package versions (should match those in docker-compose.yaml)
export VIBECTL_VERSION="0.5.3"
export LLM_VERSION="0.24.2"
export LLM_ANTHROPIC_VERSION="0.15.1"
export ANTHROPIC_SDK_VERSION="0.49.0"

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
    --passive-duration)
      export PASSIVE_DURATION="$2"
      shift 2
      ;;
    --active-duration)
      export ACTIVE_DURATION="$2"
      shift 2
      ;;
    --vibectl-model)
      export VIBECTL_MODEL="$2"
      shift 2
      ;;
    --verbose)
      export VERBOSE="true"
      shift
      ;;
    --use-stable-versions)
      export USE_STABLE_VERSIONS="true"
      shift
      ;;
    --help)
      echo "Usage: $0 [options]"
      echo "Options:"
      echo "  --passive-duration MINUTES  Set passive phase duration (default: 5 min)"
      echo "  --active-duration MINUTES   Set active phase duration (default: 25 min)"
      echo "  --vibectl-model MODEL       Set the model for vibectl (default: claude-3.7-sonnet)"
      echo "  --verbose                   Enable verbose logging"
      echo "  --use-stable-versions       Use stable, known good versions of packages from PyPI"
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
if [ -z "${VIBECTL_ANTHROPIC_API_KEY:-}" ]; then
  echo "❗ VIBECTL_ANTHROPIC_API_KEY is not set"
  read -p "Enter your Anthropic API key (starts with 'sk-ant-'): " ANTHROPIC_KEY
  if [ -z "${ANTHROPIC_KEY:-}" ]; then
    echo "❌ No API key provided. Cannot continue."
    exit 1
  fi
  export VIBECTL_ANTHROPIC_API_KEY="$ANTHROPIC_KEY"
  echo "✅ API key set"
else
  echo "✅ Using existing VIBECTL_ANTHROPIC_API_KEY from environment"
fi

echo "Starting Chaos Monkey demo with the following configuration:"
echo "  Passive phase duration: ${PASSIVE_DURATION} minutes"
echo "  Active phase duration: ${ACTIVE_DURATION} minutes"
echo "  Vibectl model: ${VIBECTL_MODEL}"
echo "  Verbose mode: ${VERBOSE}"
if [ "${USE_STABLE_VERSIONS}" = "true" ]; then
  echo "  Using stable package versions from PyPI:"
  echo "    - vibectl: ${VIBECTL_VERSION}"
  echo "    - llm: ${LLM_VERSION}"
  echo "    - llm-anthropic: ${LLM_ANTHROPIC_VERSION}"
  echo "    - anthropic: ${ANTHROPIC_SDK_VERSION}"
else
  echo "  Using vibectl from local repository source"
fi

# Start k8s-sandbox first to ensure it's fully ready before starting agents
echo "Starting Kubernetes sandbox..."
docker compose up -d --build k8s-sandbox || { echo "Failed to start k8s-sandbox"; exit 1; }

# Wait for k8s-sandbox to be healthy
echo "Waiting for Kubernetes sandbox to be ready..."
TIMEOUT=180
START_TIME=$(date +%s)
while ! docker inspect -f '{{.State.Health.Status}}' chaos-monkey-k8s-sandbox 2>/dev/null | grep -q "healthy"; do
  CURRENT_TIME=$(date +%s)
  ELAPSED_TIME=$((CURRENT_TIME - START_TIME))

  if [ $ELAPSED_TIME -gt $TIMEOUT ]; then
    echo "Error: Timed out waiting for Kubernetes sandbox to be ready"
    exit 1
  fi

  echo -n "."
  sleep 5
done
echo ""
echo "Kubernetes sandbox is ready!"

# Define the cleanup function
cleanup() {
  echo ""
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
  if docker ps -a --filter "name=chaos-monkey" -q &>/dev/null; then
    for container in $(docker ps -a --filter "name=chaos-monkey" -q); do
      echo "Removing container: $container"
      docker rm -f "$container" 2>/dev/null || true
    done
  fi

  echo "✅ Cleanup completed"
  exit 0
}

# Set the trap to call cleanup function on exit
trap cleanup INT TERM EXIT

# Start all remaining services
echo "Starting all remaining services..."
docker compose up --build
