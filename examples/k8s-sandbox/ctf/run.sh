#!/usr/bin/env bash
set -e

echo "🔧 Setting up the K8S Sandbox..."

# Process command line arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --difficulty|-d)
      CHALLENGE_DIFFICULTY="$2"
      shift 2
      ;;
    --verbose|-v)
      export VIBECTL_VERBOSE=true
      echo "ℹ️ Verbose mode enabled"
      shift
      ;;
    --help|-h)
      echo "Usage: $0 [options]"
      echo "Options:"
      echo "  --difficulty, -d LEVEL   Set the challenge difficulty (easy, medium, hard)"
      echo "                           Default: easy"
      echo "  --verbose, -v            Enable verbose output in vibectl"
      echo "  --help, -h               Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Use --help to see available options"
      exit 1
      ;;
  esac
done

# Set default challenge difficulty if not specified
if [ -z "$CHALLENGE_DIFFICULTY" ]; then
  export CHALLENGE_DIFFICULTY="easy"
  echo "ℹ️ Challenge difficulty not specified, defaulting to $CHALLENGE_DIFFICULTY"
else
  echo "ℹ️ Using challenge difficulty: $CHALLENGE_DIFFICULTY"
fi

# Set ACTIVE_PORTS based on difficulty level
case "$CHALLENGE_DIFFICULTY" in
  easy)
    export ACTIVE_PORTS="30001"
    ;;
  medium)
    export ACTIVE_PORTS="30001,30002"
    ;;
  hard)
    export ACTIVE_PORTS="30001,30002,30003"
    ;;
  *)
    echo "⚠️ Unknown difficulty level: $CHALLENGE_DIFFICULTY, defaulting to easy"
    export CHALLENGE_DIFFICULTY="easy"
    export ACTIVE_PORTS="30001"
    ;;
esac

echo "🔍 Setting active ports: $ACTIVE_PORTS for difficulty level: $CHALLENGE_DIFFICULTY"

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
  # Ensure this runs even if compose up failed
  docker compose -f compose.yml down --volumes --remove-orphans 2>/dev/null || true

  # Try to delete the kind cluster if kind is available
  if command -v kind >/dev/null 2>&1; then
    echo "☸️ Cleaning up Kind resources..."
    kind delete cluster --name ctf-cluster 2>/dev/null || true
  fi

  # Force remove any straggling kind-related containers
  echo "🐳 Checking for leftover containers..."
  for container in $(docker ps -a --filter "name=ctf-cluster" --filter "name=k8s-" -q 2>/dev/null); do
    echo "Removing container: $container"
    docker rm -f "$container" 2>/dev/null || true
  done

  # Remove any sandbox-related networks
  echo "🔌 Cleaning up networks..."
  docker network rm kind k8s-sandbox_ctf-network 2>/dev/null || true

  echo "✅ Cleanup completed"
}

# Clean up any previous runs first.
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
export CHALLENGE_DIFFICULTY
export ACTIVE_PORTS
export VIBECTL_VERBOSE

# Set up trap to catch interrupts and exit signals
trap cleanup EXIT SIGINT SIGTERM

echo "🚀 Starting the K8S Sandbox with Docker GID: $DOCKER_GID and Challenge Difficulty: $CHALLENGE_DIFFICULTY"
echo "📡 Active ports: $ACTIVE_PORTS"
if [ "$VIBECTL_VERBOSE" = "true" ]; then
  echo "📝 Verbose mode: enabled"
fi

# Run docker compose in foreground and abort when any container exits
# Overseer should exit when challenge is complete or timed out
echo "🏗️ Starting Docker Compose. Will abort when overseer exits..."
docker compose -f compose.yml up --build --abort-on-container-exit

echo "🏁 Docker Compose finished. Triggering cleanup via trap..."
# The trap will handle the actual cleanup on script exit
exit 0
