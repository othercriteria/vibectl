#!/usr/bin/env bash
set -e

echo "🚀 Starting K8S CTF Sandbox Environment..."

# The status directory is shared between containers
STATUS_DIR=${STATUS_DIR:-"/tmp/status"}
mkdir -p "$STATUS_DIR" || echo "⚠️ Could not create status directory - it may already exist"
# Make sure the directory has the right permissions - don't fail if this doesn't work
chmod 777 "$STATUS_DIR" 2>/dev/null || {
  echo "⚠️ Could not change status directory permissions - continuing anyway"
  ls -ld "$STATUS_DIR"
  id
}
CONFIG_FILE="$STATUS_DIR/challenge_config.sh"
CONFIG_JSON="$STATUS_DIR/challenge_config.json"

# Wait for overseer to create the configuration file
echo "⏳ Waiting for challenge configuration from overseer..."
TIMEOUT=30
ATTEMPTS=0
while [[ $ATTEMPTS -lt $TIMEOUT ]]; do
  if [ -f "$CONFIG_FILE" ] && [ -f "$CONFIG_JSON" ]; then
    echo "✅ Challenge configuration found."
    break
  fi

  ATTEMPTS=$((ATTEMPTS + 1))
  sleep 1
  if [[ $((ATTEMPTS % 5)) -eq 0 ]]; then
    echo "Still waiting for challenge configuration... ($ATTEMPTS seconds)"
  fi
done

if [[ $ATTEMPTS -eq $TIMEOUT ]]; then
  echo "❌ ERROR: Timed out waiting for challenge configuration."
  echo "The overseer must be running and generating configuration before the sandbox starts."
  exit 1
fi

# Get configuration directly from the JSON file instead of sourcing the shell file
echo "📝 Loading configuration from JSON..."
CHALLENGE_DIFFICULTY=$(jq -r '.challenge_difficulty' "$CONFIG_JSON")
ACTIVE_PORTS=$(jq -r '.active_ports | join(",")' "$CONFIG_JSON")
NODE_PORT_1=$(jq -r '.ports | keys | .[0]' "$CONFIG_JSON")
NODE_PORT_2=$(jq -r '.ports | keys | .[1]' "$CONFIG_JSON")
NODE_PORT_3=$(jq -r '.ports | keys | .[2]' "$CONFIG_JSON")
EXPECTED_FLAG_1=$(jq -r ".ports.\"$NODE_PORT_1\".expected_flag" "$CONFIG_JSON")
EXPECTED_FLAG_2=$(jq -r ".ports.\"$NODE_PORT_2\".expected_flag" "$CONFIG_JSON")
EXPECTED_FLAG_3=$(jq -r ".ports.\"$NODE_PORT_3\".expected_flag" "$CONFIG_JSON")
VERIFICATION_COUNT=$(jq -r '.verification_count' "$CONFIG_JSON")
RUNTIME_MINUTES=$(jq -r '.runtime_minutes' "$CONFIG_JSON")
POLL_INTERVAL_SECONDS=$(jq -r '.poll_interval_seconds' "$CONFIG_JSON")
CHALLENGE_TEXT=$(jq -r '.challenge_text' "$CONFIG_JSON")

# Fail fast if configuration is incorrect or incomplete
if [ -z "$CHALLENGE_TEXT" ]; then
  echo "❌ ERROR: Challenge text is not defined in configuration."
  echo "Make sure the overseer is correctly generating the configuration file."
  exit 1
fi

# Check Docker socket permissions
if ! docker ps >/dev/null 2>&1; then
  echo "❌ ERROR: Cannot access Docker socket. Permission denied."
  echo "Please run the sandbox using the provided ./run.sh script which sets the correct Docker group ID."
  exit 1
fi

# Clean up any previous clusters
echo "🧹 Cleaning up any previous kind clusters..."
kind delete cluster --name ctf-cluster 2>/dev/null || true

# Create a basic kind cluster without port mappings
echo "⚙️ Creating Kind Kubernetes cluster..."
cat > /tmp/kind-config.yaml <<EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
EOF

# Create the kind cluster
if ! kind create cluster --name ctf-cluster --config /tmp/kind-config.yaml; then
  echo "❌ Failed to create Kind cluster."
  exit 1
fi

# Get container IP address for the kind control-plane
CONTROL_PLANE_CONTAINER="ctf-cluster-control-plane"
CONTROL_PLANE_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "${CONTROL_PLANE_CONTAINER}")
echo "🔄 Control plane container IP: ${CONTROL_PLANE_IP}"

if [ -z "$CONTROL_PLANE_IP" ]; then
  echo "❌ Failed to get control plane IP address."
  exit 1
fi

# Generate kubeconfig and fix server address to use container IP instead of localhost
echo "📝 Generating kubeconfig with correct API server address..."
kind get kubeconfig --name ctf-cluster > /tmp/kind-kubeconfig-original
cat /tmp/kind-kubeconfig-original | sed "s/127.0.0.1:[0-9]\\+/${CONTROL_PLANE_IP}:6443/g" > /tmp/kind-kubeconfig

# Set the KUBECONFIG explicitly - Using the modified file
export KUBECONFIG="/tmp/kind-kubeconfig"
echo "📄 Using KUBECONFIG: $KUBECONFIG"

# Wait for Kubernetes API to become available
echo "⏳ Waiting for Kubernetes API to be ready..."
TIMEOUT=60
ATTEMPTS=0
while [[ $ATTEMPTS -lt $TIMEOUT ]]; do
  if kubectl cluster-info >/dev/null 2>&1; then
    echo "✅ Kubernetes API is ready."
    break
  fi

  ATTEMPTS=$((ATTEMPTS + 1))
  sleep 1
  if [[ $((ATTEMPTS % 5)) -eq 0 ]]; then
    echo "Still waiting for Kubernetes API... ($ATTEMPTS seconds)"
  fi
done

if [[ $ATTEMPTS -eq $TIMEOUT ]]; then
  echo "❌ Timed out waiting for Kubernetes API to be ready."
  exit 1
fi

# Verify cluster is running
echo "🔍 Verifying cluster status..."
kubectl cluster-info

echo "🔧 Installing vibectl from source..."
VIBECTL_SOURCE_DIR="/home/sandbox/vibectl-src" # Define source mount point
if [ -d "${VIBECTL_SOURCE_DIR}" ]; then
    echo "Installing vibectl from source directory: ${VIBECTL_SOURCE_DIR}..."
    cd "${VIBECTL_SOURCE_DIR}"
    # Install in editable mode
    if ! pip install --quiet -e .; then # Added --quiet
        echo "❌ Error: Failed to install vibectl from source."
        exit 1
    fi
    echo "✅ vibectl installed from source"
    cd - >/dev/null
else
    echo "❌ Error: vibectl source directory not found at ${VIBECTL_SOURCE_DIR}" >&2
    echo "   Make sure the volume is mounted correctly in compose.yml" >&2
    exit 1
fi

# Set up vibectl API keys using the correct configuration structure
echo "🔑 Setting up API keys using vibectl configuration..."
if [ -n "$VIBECTL_ANTHROPIC_API_KEY" ]; then
  vibectl config set providers.anthropic.key "$VIBECTL_ANTHROPIC_API_KEY"
  echo "✅ Anthropic API key configured"
else
  echo "❌ ERROR: VIBECTL_ANTHROPIC_API_KEY environment variable is not set."
  echo "Please provide the API key when running the sandbox."
  exit 1
fi

# Set vibectl config (from environment variables provided by Docker Compose)
echo "📝 Configuring vibectl..."
vibectl config set memory.max_chars ${VIBECTL_MEMORY_MAX_CHARS:-1500}
vibectl config set llm.model "$VIBECTL_MODEL"
vibectl config set display.show_memory true
vibectl config set display.show_streaming false
# Configure output options based on verbose mode
if [ "$VIBECTL_VERBOSE" = "true" ]; then
  echo "📝 Verbose mode enabled: showing raw output and kubectl commands"
  vibectl config set display.show_raw_output true
  vibectl config set display.show_kubectl true
  vibectl config set display.show_metrics all
  export VIBECTL_TRACEBACK=1
else
  vibectl config set display.show_raw_output false
  vibectl config set display.show_kubectl false
  vibectl config set display.show_metrics none
fi

echo "🏆 Starting challenge - setting up Kubernetes environment..."

# Use the challenge text from the configuration
cat <<EOF | vibectl instructions set
$CHALLENGE_TEXT

Time limit from cluster creation: ${RUNTIME_MINUTES} minutes.

Success is checked programmatically so make sure you *exactly* conform to the goal.

Checks for the success condition run at a cadence of <1 minute.

You will be repeatedly able to act on the cluster, and execution ends only on success or timeout.

So if you are running, you have not succeeded (yet!).
EOF
vibectl instructions show
vibectl memory set "You are working on a fresh kind k8s cluster."

# Function to maintain connectivity to the k8s cluster
check_k8s_health() {
  if ! kubectl get nodes >/dev/null 2>&1; then
    echo "⚠️ Kubernetes cluster appears to be unhealthy, attempting to reconnect..."
    # Try to restore KUBECONFIG
    export KUBECONFIG="/tmp/kind-kubeconfig"
    if ! kubectl cluster-info >/dev/null 2>&1; then
      echo "❌ Failed to reconnect to cluster, but we'll keep trying"
    else
      echo "✅ Reconnected to Kubernetes cluster"
    fi
  fi
}

# Main loop that keeps the sandbox running
echo "🔄 Starting sandbox execution..."

# Update status file for the overseer
SANDBOX_STATUS_FILE="$STATUS_DIR/sandbox_status.json"

# Initialize sandbox status
cat > "$SANDBOX_STATUS_FILE" <<EOF
{
  "sandbox_started_at": "$(date -Iseconds)",
  "status": "running",
  "last_updated": "$(date -Iseconds)"
}
EOF

# Check if the challenge has been completed *before* starting the loop
COMPLETION_FILE="$STATUS_DIR/challenge_complete.json"
if [ -f "$COMPLETION_FILE" ]; then
  MESSAGE=$(jq -r '.message' "$COMPLETION_FILE" 2>/dev/null || echo "Challenge complete!")
  echo "🏆 $MESSAGE"
  echo "✅ CTF Challenge completed successfully. Exiting gracefully."
  exit 0
fi

# Check cluster health *before* starting the potentially long-running process
check_k8s_health

# Run vibectl in autonomous mode
echo "🔄 Starting vibectl autonomous mode with 5s interval..."

# Show vibectl memory in verbose mode (will be shown by auto if configured)
if [ "$VIBECTL_VERBOSE" = "true" ]; then
  echo "Verbose mode is enabled. vibectl auto will show memory if configured."
fi

# Capture full output and error for debugging (less critical for auto, but useful if it fails)
# Run vibectl auto indefinitely with a 5-second interval
if ! vibectl auto --interval 5; then
    ERROR_CODE=$?
    echo "⚠️ vibectl auto exited unexpectedly with code $ERROR_CODE"
    echo "If the error above is unclear, try running with VIBECTL_VERBOSE=true or check if a Python traceback is available."
    exit $ERROR_CODE # Exit if auto fails
fi

# If vibectl auto exits cleanly (e.g., interrupted), we just finish.
echo "✅ vibectl auto finished or was interrupted."

# The status update is no longer needed within a loop.
# The completion check happens before starting auto, and the overseer monitors completion.
# The loop structure is completely replaced by the single `vibectl auto` command above.
