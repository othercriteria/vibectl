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

# Explicitly export API key to make sure it's available for vibectl and llm
export VIBECTL_ANTHROPIC_API_KEY="$VIBECTL_ANTHROPIC_API_KEY"
export ANTHROPIC_API_KEY="$VIBECTL_ANTHROPIC_API_KEY"

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

# Set environment variables for the API key - this is the most reliable method
# We're already exporting them above, but we'll make this section more visible
echo "🔑 Configuring vibectl API keys..."
echo "Using environment variables for API key configuration"
# Environment variables have precedence over config settings, so this is the safest approach
# No need to use vibectl config set as it doesn't properly handle nested values

# Initialize the challenge with specific memory instructions
echo "🧠 Setting up vibectl memory with CTF challenges..."
CHALLENGE_MEMORY="You are working on a fresh kind k8s cluster. Your goal is to complete these tasks:

1. Create a service that returns 'CTF-FLAG-1: K8S_MASTER' text when accessed on port ${NODE_PORT_1}. You can use any approach you think is best (pod, deployment, etc.).

2. Create a service that returns 'CTF-FLAG-2: VIBECTL_PRO' text when accessed on port ${NODE_PORT_2}. Make sure this service is resilient and can handle load (hint: multiple replicas).

3. Create a service that returns 'CTF-FLAG-3: CHALLENGE_COMPLETE' text when accessed on port ${NODE_PORT_3}. For this service, use a ConfigMap to store the flag text."

# Set vibectl memory with the challenges
vibectl memory set "$CHALLENGE_MEMORY"

# Start vibectl in autonomous mode with auto-confirmation
echo "🤖 Starting vibectl in autonomous mode..."
echo "📝 CTF challenge has begun! Internal ports ${NODE_PORT_1}, ${NODE_PORT_2}, and ${NODE_PORT_3} will be monitored by the poller."

# Loop to repeatedly execute vibectl vibe with auto-confirmation
while true; do
  yes | vibectl vibe
  sleep 10
done
