#!/usr/bin/env bash
set -e

echo "🚀 Starting K8S Sandbox CTF Challenge..."

# Check if VIBECTL_ANTHROPIC_API_KEY is set
if [ -z "$VIBECTL_ANTHROPIC_API_KEY" ]; then
  echo "❌ ERROR: VIBECTL_ANTHROPIC_API_KEY environment variable is not set."
  echo "Please provide the API key when running the sandbox."
  exit 1
fi

# Check if VIBECTL_MODEL is set, default to claude-3.7-sonnet if not
if [ -z "$VIBECTL_MODEL" ]; then
  export VIBECTL_MODEL="claude-3.7-sonnet"
  echo "ℹ️ VIBECTL_MODEL not set, defaulting to $VIBECTL_MODEL"
fi

# Check which challenge difficulty to use (default to easy)
if [ -z "$CHALLENGE_DIFFICULTY" ]; then
  export CHALLENGE_DIFFICULTY="easy"
  echo "ℹ️ CHALLENGE_DIFFICULTY not set, defaulting to $CHALLENGE_DIFFICULTY"
fi

# Explicitly export API keys for all relevant tools - set both versions to ensure compatibility
# Environment variables are the most reliable way to set these across different tools
export VIBECTL_ANTHROPIC_API_KEY="$VIBECTL_ANTHROPIC_API_KEY"
export ANTHROPIC_API_KEY="$VIBECTL_ANTHROPIC_API_KEY"

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

# Set up OpenAI key as an empty value to avoid errors
export OPENAI_API_KEY=""

# Check Docker socket permissions
if ! docker ps >/dev/null 2>&1; then
  echo "❌ ERROR: Cannot access Docker socket. Permission denied."
  echo "Please run the sandbox using the provided ./run.sh script which sets the correct Docker group ID."
  exit 1
fi

# Clean up any previous clusters
echo "🧹 Cleaning up any previous kind clusters..."
kind delete cluster --name ctf-cluster 2>/dev/null || true

# Define fixed internal ports - these are the nodePort values inside the cluster
NODE_PORT_1=${NODE_PORT_1:-30001}
NODE_PORT_2=${NODE_PORT_2:-30002}
NODE_PORT_3=${NODE_PORT_3:-30003}

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

# Set vibectl config to increase memory limit
echo "📝 Configuring vibectl memory limit..."
vibectl config set memory_max_chars 1000

# Configure vibectl model
echo "🔧 Configuring vibectl model..."
vibectl config set model "$VIBECTL_MODEL"

# Initialize the challenge based on selected difficulty
echo "🧠 Setting up vibectl memory with CTF challenges (Difficulty: $CHALLENGE_DIFFICULTY)..."

if [ "$CHALLENGE_DIFFICULTY" == "easy" ]; then
  # Easy challenge - just create a single service
  CHALLENGE_MEMORY="You are working on a fresh kind k8s cluster. Your goal is to complete this task:

  1. Create a service that returns 'CTF-FLAG-1: K8S_MASTER' text when accessed on port ${NODE_PORT_1}. You can use any approach you think is best (pod, deployment, etc.).

  This is a simple challenge to test your basic k8s skills. Once you complete this challenge, you'll be ready for more complex tasks!"

  # Determine which ports to monitor based on active challenges
  ACTIVE_PORTS="${NODE_PORT_1}"
  echo "🏆 Running EASY challenge mode - monitoring port ${NODE_PORT_1}"

elif [ "$CHALLENGE_DIFFICULTY" == "medium" ]; then
  # Medium challenge - create two services
  CHALLENGE_MEMORY="You are working on a fresh kind k8s cluster. Your goal is to complete these tasks:

  1. Create a service that returns 'CTF-FLAG-1: K8S_MASTER' text when accessed on port ${NODE_PORT_1}. You can use any approach you think is best (pod, deployment, etc.).

  2. Create a service that returns 'CTF-FLAG-2: VIBECTL_PRO' text when accessed on port ${NODE_PORT_2}. Make sure this service is resilient and can handle load (hint: multiple replicas)."

  # Determine which ports to monitor based on active challenges
  ACTIVE_PORTS="${NODE_PORT_1},${NODE_PORT_2}"
  echo "🏆 Running MEDIUM challenge mode - monitoring ports ${NODE_PORT_1} and ${NODE_PORT_2}"

else
  # Hard (default) challenge - create all three services
  CHALLENGE_MEMORY="You are working on a fresh kind k8s cluster. Your goal is to complete these tasks:

  1. Create a service that returns 'CTF-FLAG-1: K8S_MASTER' text when accessed on port ${NODE_PORT_1}. You can use any approach you think is best (pod, deployment, etc.).

  2. Create a service that returns 'CTF-FLAG-2: VIBECTL_PRO' text when accessed on port ${NODE_PORT_2}. Make sure this service is resilient and can handle load (hint: multiple replicas).

  3. Create a service that returns 'CTF-FLAG-3: CHALLENGE_COMPLETE' text when accessed on port ${NODE_PORT_3}. For this service, use a ConfigMap to store the flag text."

  # Determine which ports to monitor based on active challenges
  ACTIVE_PORTS="${NODE_PORT_1},${NODE_PORT_2},${NODE_PORT_3}"
  echo "🏆 Running HARD challenge mode - monitoring all ports: ${NODE_PORT_1}, ${NODE_PORT_2}, and ${NODE_PORT_3}"
fi

# Export active ports for the poller
export ACTIVE_PORTS

# Set vibectl memory with the challenges
vibectl memory set "$CHALLENGE_MEMORY"

# Configure output options based on verbose mode
if [ "$VIBECTL_VERBOSE" = "true" ]; then
  echo "📝 Verbose mode enabled: showing raw output and kubectl commands"
  vibectl config set show_raw_output true
  vibectl config set show_kubectl true
else
  vibectl config set show_raw_output false
  vibectl config set show_kubectl false
fi

# Start vibectl in autonomous mode with auto-confirmation
echo "🤖 Starting vibectl in autonomous mode..."
echo "📝 CTF challenge has begun! Monitoring ports indicated in ACTIVE_PORTS: $ACTIVE_PORTS"

# Simple function to run vibectl vibe with auto-confirmation and error handling
run_vibectl() {
  # Run vibectl with --yes for auto-confirmation
  echo "🔄 Running vibectl vibe..."

  # Capture output for debugging but don't let errors crash the container
  if ! vibectl vibe --yes 2>&1; then
    ERROR_CODE=$?
    echo "⚠️ vibectl exited with error code $ERROR_CODE - restarting in 5 seconds"
    # We could add more recovery steps here if needed
    sleep 5
  else
    echo "✅ vibectl session completed normally"
  fi
}

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

# Function to check if test services are running
check_services() {
  # Track which services we've found to avoid excessive logging
  local service_1_found=false
  local service_2_found=false
  local service_3_found=false

  if [[ "$ACTIVE_PORTS" == *"$NODE_PORT_1"* ]] && ! $service_1_found; then
    if curl -s --connect-timeout 2 --max-time 5 "http://localhost:$NODE_PORT_1" | grep -q "CTF-FLAG-1"; then
      echo "🎯 Service 1 is running! (Port $NODE_PORT_1)"
      service_1_found=true
    fi
  fi

  if [[ "$ACTIVE_PORTS" == *"$NODE_PORT_2"* ]] && ! $service_2_found; then
    if curl -s --connect-timeout 2 --max-time 5 "http://localhost:$NODE_PORT_2" | grep -q "CTF-FLAG-2"; then
      echo "🎯 Service 2 is running! (Port $NODE_PORT_2)"
      service_2_found=true
    fi
  fi

  if [[ "$ACTIVE_PORTS" == *"$NODE_PORT_3"* ]] && ! $service_3_found; then
    if curl -s --connect-timeout 2 --max-time 5 "http://localhost:$NODE_PORT_3" | grep -q "CTF-FLAG-3"; then
      echo "🎯 Service 3 is running! (Port $NODE_PORT_3)"
      service_3_found=true
    fi
  fi
}

# Main loop that keeps the sandbox running even if vibectl crashes
echo "🔄 Starting main sandbox loop..."
while true; do
  # Check cluster health before running vibectl
  check_k8s_health

  # Check if services are responding
  check_services

  # Run vibectl with error handling
  run_vibectl

  # Always sleep between attempts to avoid thrashing
  sleep 5

  echo "♻️ Restarting vibectl - sandbox container remains running"
done
