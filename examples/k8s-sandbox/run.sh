#!/usr/bin/env bash
set -e

echo "🔧 Setting up the K8S Sandbox..."

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

# Enhanced cleanup function with more thorough resource removal
cleanup() {
  echo "🧹 Cleaning up containers and resources..."

  # Stop and remove containers via docker compose
  docker compose -f compose.yml down --volumes --remove-orphans 2>/dev/null || true

  # Try to delete the kind cluster if kind is available
  if command -v kind >/dev/null 2>&1; then
    echo "☸️ Cleaning up Kind resources..."
    kind delete cluster --name ctf-cluster 2>/dev/null || true
  fi

  # Force remove any straggling kind-related containers
  echo "🐳 Checking for leftover containers..."
  for container in $(docker ps -a --filter "name=ctf-cluster" -q 2>/dev/null); do
    echo "Removing container: $container"
    docker rm -f "$container" 2>/dev/null || true
  done

  # Remove any sandbox-related networks
  echo "🔌 Cleaning up networks..."
  docker network rm kind k8s-sandbox_ctf-network 2>/dev/null || true

  echo "✅ Cleanup completed"
}

# Clean up any previous runs
cleanup

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

# Set up trap to catch interrupts and exit signals
trap cleanup EXIT SIGINT SIGTERM

echo "🚀 Starting the K8S Sandbox with Docker GID: $DOCKER_GID"

# Run docker compose with explicit file specification
docker compose -f compose.yml up --build
