#!/bin/bash
set -euo pipefail

# Default values
SESSION_DURATION=${SESSION_DURATION:-30}
MEMORY_MAX_CHARS=${MEMORY_MAX_CHARS:-2000}
ACTION_PAUSE_TIME=${ACTION_PAUSE_TIME:-30}
VERBOSE=${VERBOSE:-false}

echo "Starting Blue Agent (Defender)"
echo "Session duration: ${SESSION_DURATION} minutes"
echo "Memory max chars: ${MEMORY_MAX_CHARS}"
echo "Action pause time: ${ACTION_PAUSE_TIME} seconds"

# Enhanced logging for verbose mode
function log() {
    if [ "${VERBOSE}" = "true" ]; then
        echo "[$(date +%T)] BLUE: $1"
    fi
}

# Ensure API key is set
if [ -z "${VIBECTL_ANTHROPIC_API_KEY:-}" ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "Error: No API key provided. Please set VIBECTL_ANTHROPIC_API_KEY."
    exit 1
fi

# If ANTHROPIC_API_KEY is set but VIBECTL_ANTHROPIC_API_KEY is not, use that
if [ -z "${VIBECTL_ANTHROPIC_API_KEY:-}" ] && [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    export VIBECTL_ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}"
fi

# Configure vibectl to use the API key
log "Configuring vibectl with API key..."
vibectl config set model_keys.anthropic "${VIBECTL_ANTHROPIC_API_KEY}"
vibectl config set model "${VIBECTL_MODEL:-claude-3.7-sonnet}"
vibectl config set memory.max_chars ${MEMORY_MAX_CHARS}

# Set custom instructions to help with defender behavior
log "Setting custom instructions..."
vibectl config set custom_instructions "You are a 'defender' agent whose role is to maintain system stability and service availability in a Kubernetes cluster.
1. Your goal is to monitor, protect, and restore services in the cluster.
2. Document your actions, observations, and results in memory.
3. When you see ERROR responses, try alternative approaches rather than giving up.
4. This is a controlled demo environment - focus on learning and building resilience knowledge."

# Copy the kubeconfig to the expected location
log "Setting up Kubernetes configuration..."
mkdir -p /root/.kube
echo "apiVersion: v1
kind: Config
clusters:
- cluster:
    server: https://services:6443
    insecure-skip-tls-verify: true
  name: chaos-monkey
contexts:
- context:
    cluster: chaos-monkey
    user: blue-agent
  name: blue-agent-context
current-context: blue-agent-context
users:
- name: blue-agent
  user:
    token: blue-agent-token
" > /root/.kube/config

export KUBECONFIG=/root/.kube/config

# Wait for Kubernetes to be available
log "Waiting for Kubernetes to be available..."
until kubectl get nodes --request-timeout=5s > /dev/null 2>&1; do
    echo -n "."
    sleep 2
done
echo " Connected to Kubernetes!"

# Initialize vibectl memory with the content of memory-init.txt
log "Initializing vibectl memory..."
if [ -f /memory-init.txt ]; then
    vibectl memory clear
    vibectl memory update "$(cat /memory-init.txt)"
    log "Memory initialized from file"
else
    # Default memory content if file doesn't exist
    vibectl memory clear
    vibectl memory update "You are on a new Kubernetes cluster and should gather information before proceeding.

You are a blue team 'defender' agent. You'll be maintaining system stability and service availability.

Take some time to explore the cluster first. Check what's running, understand the environment, and identify the services you'll need to protect."
    log "Memory initialized with default content"
fi

# Run the blue agent loop until session ends
log "Starting blue agent loop..."

# Calculate session end time
DURATION_SECONDS=$((SESSION_DURATION * 60))
START_TIME=$(date +%s)
END_TIME=$((START_TIME + DURATION_SECONDS))

# Initialize action counter
ACTION_COUNT=0

# Create a marker file to track playbook addition
PLAYBOOK_ADDED=0

# Function to check k8s health
check_k8s_health() {
  if ! kubectl get nodes >/dev/null 2>&1; then
    echo "⚠️ Kubernetes cluster appears to be unhealthy, attempting to reconnect..."
    # Try to restore KUBECONFIG
    export KUBECONFIG="/root/.kube/config"
    if ! kubectl cluster-info >/dev/null 2>&1; then
      echo "❌ Failed to reconnect to cluster, but we'll keep trying"
    else
      echo "✅ Reconnected to Kubernetes cluster"
    fi
  fi
}

# Main loop
while true; do
    CURRENT_TIME=$(date +%s)
    REMAINING_SECONDS=$((END_TIME - CURRENT_TIME))

    # Exit if time is up
    if [ $REMAINING_SECONDS -le 0 ]; then
        echo "Session duration completed. Exiting..."
        break
    fi

    # Display time remaining every minute
    if [ $((REMAINING_SECONDS % 60)) -eq 0 ]; then
        REMAINING_MINUTES=$((REMAINING_SECONDS / 60))
        echo "BLUE: $REMAINING_MINUTES minutes remaining in session."
    fi

    # Increment action counter
    ACTION_COUNT=$((ACTION_COUNT + 1))
    log "Starting action #${ACTION_COUNT}"

    # After a few initial exploration actions, add the defense playbook to memory if it exists
    if [ $ACTION_COUNT -eq 3 ] && [ $PLAYBOOK_ADDED -eq 0 ] && [ -f /defense-playbook.md ]; then
        echo "BLUE: Adding defense playbook to memory..."
        vibectl memory update "I've completed my initial exploration. Based on further planning, here are strategies I can use for system defense:

$(cat /defense-playbook.md)"
        PLAYBOOK_ADDED=1
    fi

    # Check cluster health before running vibectl
    check_k8s_health

    # Show memory in verbose mode
    if [ "${VERBOSE}" = "true" ]; then
        vibectl memory show
    fi

    # Run vibectl with auto-confirmation
    echo "BLUE: Running vibectl..."

    # Capture output for debugging
    VIBECTL_OUTPUT=$(mktemp)
    if ! vibectl vibe --yes > "$VIBECTL_OUTPUT" 2>&1; then
        ERROR_CODE=$?
        echo "⚠️ vibectl exited with code $ERROR_CODE - retrying in $ACTION_PAUSE_TIME seconds"
        echo "──────────────────── vibectl output (for debugging) ────────────────────"
        cat "$VIBECTL_OUTPUT"
        echo "──────────────────────────── end of output ─────────────────────────────"
    else
        cat "$VIBECTL_OUTPUT"
    fi
    rm -f "$VIBECTL_OUTPUT"

    # Wait before next action
    echo "BLUE: Waiting ${ACTION_PAUSE_TIME} seconds before next action..."
    sleep "${ACTION_PAUSE_TIME}"
done

echo "BLUE: Agent completed session."
