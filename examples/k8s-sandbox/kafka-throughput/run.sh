#!/usr/bin/env bash
# Orchestrates the Kafka Throughput Demo using Docker Compose.

# Fail fast on any error
set -euo pipefail

echo "🚀 Starting Kafka Throughput Demo Setup..."

# --- Configuration ---
# TODO: Add argument parsing for specific demo parameters if needed later.

# Check for VIBECTL_ANTHROPIC_API_KEY
if [ -z "${VIBECTL_ANTHROPIC_API_KEY:-}" ]; then
  echo "❗️ VIBECTL_ANTHROPIC_API_KEY environment variable is not set."
  # Loop until a non-empty key is provided or the user cancels
  while [ -z "${VIBECTL_ANTHROPIC_API_KEY:-}" ]; do
    read -rsp "🔑 Enter your Anthropic API key (starts with 'sk-ant-', press Enter to cancel): " key_input
    echo # Print a newline after the prompt
    if [ -z "$key_input" ]; then
      echo "❌ API key not provided. Exiting."
      exit 1
    fi
    # Basic check for the prefix
    if [[ "$key_input" == sk-ant-* ]]; then
      export VIBECTL_ANTHROPIC_API_KEY="$key_input"
      echo "✅ API key accepted."
    else
      echo "⚠️ Invalid API key format. It should start with 'sk-ant-'. Please try again or press Enter to cancel."
    fi
  done
else
  echo "✅ Using existing VIBECTL_ANTHROPIC_API_KEY from environment."
fi

# Detect Docker GID for container permissions
# Try getent first (Linux)
if command -v getent &> /dev/null && getent group docker &> /dev/null; then
    DOCKER_GID=$(getent group docker | cut -d: -f3)
# Try stat on the socket (macOS, other Linux)
elif command -v stat &> /dev/null && [ -S /var/run/docker.sock ]; then
    if stat -c '%g' /var/run/docker.sock &> /dev/null; then # Linux stat
        DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)
    elif stat -f '%g' /var/run/docker.sock &> /dev/null; then # macOS stat
        DOCKER_GID=$(stat -f '%g' /var/run/docker.sock)
    fi
fi

# Default if detection failed or socket doesn't exist
if [ -z "${DOCKER_GID:-}" ]; then
    DOCKER_GID=999
    echo "⚠️ Could not detect Docker GID. Using default: ${DOCKER_GID}. File permissions inside containers might be affected."
else
    echo "🔍 Detected Docker GID: ${DOCKER_GID}"
fi
export DOCKER_GID # Export GID for build --build-arg

# --- Generate Kafka Cluster ID (if needed) ---
STATUS_DIR="./status-volume"

# Ensure status directory exists (needed for storing the ID)
mkdir -p "${STATUS_DIR}"

# Clean up old status files from previous runs, but preserve kafka_cluster_id.txt
echo "🧹 Cleaning up stale files in ${STATUS_DIR}..."
# Loop through files in STATUS_DIR and delete them
for f in "${STATUS_DIR}"/*; do
    # Check if it is a file and not the one we want to preserve
    if [ -f "$f" ]; then
        echo "   Deleting stale file: $f"
        rm -f "$f"
    fi
done
echo "✅ Stale file cleanup complete."

# --- Prerequisite Checks ---
echo "🧐 Checking prerequisites..."

# Check for docker
if ! command -v docker &> /dev/null; then
    echo "❌ Error: 'docker' command not found. Please install Docker."
    exit 1
fi

# Check for docker compose (v1 or v2)
if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
elif docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
else
    echo "❌ Error: 'docker-compose' or 'docker compose' command not found. Please install Docker Compose."
    exit 1
fi
echo "✅ Docker and Docker Compose found ($COMPOSE_CMD)."

# Check docker socket permissions (optional check)
if [ -S /var/run/docker.sock ] && [ ! -r /var/run/docker.sock ] && [ ! -w /var/run/docker.sock ]; then
    echo "⚠️ Warning: Docker socket (/var/run/docker.sock) might not be readable/writable by the current user."
    echo "   You might need to run this script with sudo or add your user to the 'docker' group."
fi

# --- Cleanup Function ---
cleanup() {
  echo # Add a newline for clarity
  echo "🧹 Cleaning up Kafka Demo resources..."
  # Use the determined compose command
  # Use --project-name to avoid conflicts if needed, but compose.yml in dir should be sufficient
  # Use --timeout to prevent hanging
  # Suppress "network not found" errors etc. during down
  ${COMPOSE_CMD} -f compose.yml down --volumes --remove-orphans --timeout 30 2>/dev/null || true

  # Explicitly remove the shared volume just in case 'down --volumes' misses it
  # docker volume rm kafka-throughput_status-volume 2>/dev/null || true

  # Note: k3d cleanup is handled *inside* the k8s-sandbox container's entrypoint/trap

  echo "✅ Cleanup attempt finished."
}

# --- Main Execution ---
echo "🚀 Building and starting Docker containers..."

# Allow skipping startup if only build is requested
ONLY_BUILD=false
if [ "${1:-}" == "--build-only" ]; then
  ONLY_BUILD=true
fi

# Ensure we are in the script's directory to find compose.yml
cd "$(dirname "$0")"

# --- Step 1: Build Images ---
echo "🛠️ Building Docker images..."
# Pass DOCKER_GID as a build argument
if ! ${COMPOSE_CMD} -f compose.yml build --build-arg DOCKER_GID=${DOCKER_GID}; then
    echo "❌ Error: Docker build failed." >&2
    exit 1 # Exit if build fails
fi
echo "✅ Docker images built successfully."

# Exit here if only build was requested
if [ "${ONLY_BUILD}" = true ]; then
  echo "✅ Build complete (--build-only requested)."
  exit 0
fi

# --- Step 2: Start Containers ---
echo "🚢 Starting services..."
# Use the determined compose command
# Use --project-name to avoid conflicts if needed, but compose.yml in dir should be sufficient
# Use --env-file to pass the generated variables
if ! ${COMPOSE_CMD} -f compose.yml up -d; then
    echo "❌ Error: Docker compose up failed." >&2
    # Cleanup might already be triggered by failed container, but attempt explicit cleanup
    exit 1
fi

# --- Step 3: Wait for Kafka Readiness ---
echo "⏳ Waiting for the k8s-sandbox container to signal Kafka readiness..."
# This assumes the k8s-sandbox container creates this file when ready
# Path relative to the script's directory (examples/k8s-sandbox/kafka-throughput/)
status_file_path="${STATUS_DIR}/kafka_ready"
max_wait_seconds=300 # 5 minutes
wait_interval=1
elapsed_wait=0

# Wait for the status file to appear
while ! [ -f "${status_file_path}" ]; do
    if [ $elapsed_wait -ge $max_wait_seconds ]; then
        echo "" # Newline after dots
        echo "❌ Error: Timed out waiting for Kafka readiness signal (${status_file_path}) after ${max_wait_seconds}s."
        echo "   Check the logs of the 'k8s-sandbox' container:"
        ${COMPOSE_CMD} -f compose.yml logs k8s-sandbox
        # Cleanup will run automatically via trap EXIT
        exit 1
    fi
    # Print a dot every interval to show progress
    echo -n "."
    sleep $wait_interval
    elapsed_wait=$((elapsed_wait + wait_interval))
done

echo "" # Newline after the dots
echo "✅ Kafka cluster reported as ready via ${status_file_path}."

# --- Post-Startup Information ---
echo
echo "🎉 Kafka Throughput Demo is running!"
echo "   - Kafka Broker (via k8s-sandbox port-forward): localhost:9092"
echo "   - Producer, Consumer, Kafka-Demo-UI, and Vibectl Agent are running in containers."
echo "   - Shared status volume mounted at './status-volume/'"
echo
echo "ℹ️ Monitoring:"
echo "   - View container logs: ${COMPOSE_CMD} -f compose.yml logs -f <service_name> (e.g., k8s-sandbox, producer)"
echo "   - View Vibectl agent actions: ${COMPOSE_CMD} -f compose.yml logs -f k8s-sandbox | grep 'vibectl auto'"
echo "   - Check latency file: cat ./status-volume/latency.txt"
echo
echo "🛑 To stop the demo and clean up resources, press Ctrl+C."
