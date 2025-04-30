#!/usr/bin/env bash
set -e

echo "🚀 Starting K8S CTF Sandbox Environment..."

# Check if VIBECTL_ANTHROPIC_API_KEY is set (fail fast)
if [ -z "$VIBECTL_ANTHROPIC_API_KEY" ]; then
  echo "❌ ERROR: VIBECTL_ANTHROPIC_API_KEY environment variable is not set."
  echo "Please provide the API key when running the sandbox."
  exit 1
fi

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

echo "🧠 Setting up vibectl with the challenge task..."

# Set up LLM tool API keys directly
echo "🔑 Setting up LLM tool API keys..."
# Get the exact path for the keys.json file from the llm tool
LLM_KEYS_PATH=$(llm keys path)
if [ -z "$LLM_KEYS_PATH" ]; then
  echo "❌ ERROR: Could not determine keys path from llm tool."
  echo "This is required for the sandbox to work properly."
  exit 1
fi
echo "📁 Using LLM keys path: $LLM_KEYS_PATH"

# Ensure the directory exists
mkdir -p "$(dirname "$LLM_KEYS_PATH")"

# Write the keys file
cat > "$LLM_KEYS_PATH" << EOF
{
  "anthropic": "$VIBECTL_ANTHROPIC_API_KEY"
}
EOF
chmod 600 "$LLM_KEYS_PATH"
echo "✅ LLM API key set via direct file configuration"

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

# <<< ADDED: Install vibectl from source >>>
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
# <<< END ADDED SECTION >>>

# Set vibectl config (from environment variables provided by Docker Compose)
echo "📝 Configuring vibectl..."
vibectl config set memory_max_chars ${VIBECTL_MEMORY_MAX_CHARS:-1500}
vibectl config set model "$VIBECTL_MODEL"

# Configure output options based on verbose mode
if [ "$VIBECTL_VERBOSE" = "true" ]; then
  echo "📝 Verbose mode enabled: showing raw output and kubectl commands"
  vibectl config set show_raw_output true
  vibectl config set show_kubectl true
  export VIBECTL_TRACEBACK=1
else
  vibectl config set show_raw_output false
  vibectl config set show_kubectl false
fi

echo "🏆 Starting challenge - setting up Kubernetes environment..."

# Use the challenge text from the configuration
cat <<EOF | vibectl instructions set
$CHALLENGE_TEXT

Time limit from cluster creation: ${RUNTIME_MINUTES} minutes.
You will continue running until challenge completion or time limit.
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

# Pause between vibectl runs
PAUSE_SECONDS=5

while true; do
  # Check if the challenge has been completed
  COMPLETION_FILE="$STATUS_DIR/challenge_complete.json"
  if [ -f "$COMPLETION_FILE" ]; then
    MESSAGE=$(jq -r '.message' "$COMPLETION_FILE" 2>/dev/null || echo "Challenge complete!")
    echo "🏆 $MESSAGE"
    echo "✅ CTF Challenge completed successfully. Exiting gracefully."
    exit 0
  fi

  # Check cluster health before running vibectl
  check_k8s_health

  # Run vibectl with auto-confirmation
  echo "🔄 Running vibectl vibe..."

  # Show vibectl memory in verbose mode
  if [ "$VIBECTL_VERBOSE" = "true" ]; then
    vibectl memory show
  fi

  # Capture full output and error for debugging
  VIBECTL_OUTPUT=$(mktemp)
  if ! vibectl vibe --yes > "$VIBECTL_OUTPUT" 2>&1; then
    ERROR_CODE=$?
    echo "⚠️ vibectl exited with code $ERROR_CODE - retrying in $PAUSE_SECONDS seconds"
    echo "──────────────────── vibectl output (for debugging) ────────────────────"
    cat "$VIBECTL_OUTPUT"
    echo "──────────────────────────── end of output ─────────────────────────────"
    echo "If the error above is unclear, try running with VIBECTL_VERBOSE=true or check if a Python traceback is available."
  else
    cat "$VIBECTL_OUTPUT"
  fi
  rm -f "$VIBECTL_OUTPUT"

  # Update status
  cat > "$SANDBOX_STATUS_FILE" <<EOF
{
  "sandbox_started_at": "$(date -Iseconds)",
  "status": "running",
  "last_updated": "$(date -Iseconds)"
}
EOF

  # Brief pause before next attempt
  sleep $PAUSE_SECONDS
done
