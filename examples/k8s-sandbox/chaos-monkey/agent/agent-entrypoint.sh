#!/bin/bash
set -euo pipefail

# Required environment variables
# AGENT_ROLE=blue|red - Role of the agent (blue=defender, red=attacker)
# AGENT_NAME=defender|attacker - Human-readable name of the agent
# MEMORY_INIT_FILE - Path to the memory initialization file
# PLAYBOOK_FILE - Path to the agent's playbook (defense or attack)
# CUSTOM_INSTRUCTIONS_FILE - Path to custom instructions file

# Default values if not set in environment
SESSION_DURATION=${SESSION_DURATION:-30}
MEMORY_MAX_CHARS=${MEMORY_MAX_CHARS:-2000}
ACTION_PAUSE_TIME=${ACTION_PAUSE_TIME:-30}
VERBOSE=${VERBOSE:-false}
KUBE_CONFIG=${KUBE_CONFIG:-/config/kube/config}
AGENT_ROLE=${AGENT_ROLE:-blue}
AGENT_NAME=${AGENT_NAME:-defender}
MEMORY_INIT_FILE=${MEMORY_INIT_FILE:-/memory-init.txt}
PLAYBOOK_FILE=${PLAYBOOK_FILE:-/playbook.md}
CUSTOM_INSTRUCTIONS_FILE=${CUSTOM_INSTRUCTIONS_FILE:-/custom-instructions.txt}
INITIAL_DELAY=${INITIAL_DELAY:-0}

# Set color for agent output
if [ "$AGENT_ROLE" = "blue" ]; then
    COLOR_CODE="\033[34m" # Blue color
elif [ "$AGENT_ROLE" = "red" ]; then
    COLOR_CODE="\033[31m" # Red color
else
    COLOR_CODE="\033[0m" # Default color
fi
NO_COLOR="\033[0m"

echo -e "${COLOR_CODE}Starting ${AGENT_NAME^} Agent${NO_COLOR}"
echo -e "${COLOR_CODE}Role: ${AGENT_ROLE}${NO_COLOR}"
echo -e "${COLOR_CODE}Session duration: ${SESSION_DURATION} minutes${NO_COLOR}"
echo -e "${COLOR_CODE}Memory max chars: ${MEMORY_MAX_CHARS}${NO_COLOR}"
echo -e "${COLOR_CODE}Action pause time: ${ACTION_PAUSE_TIME} seconds${NO_COLOR}"

# Enhanced logging for verbose mode
function log() {
    if [ "${VERBOSE}" = "true" ]; then
        echo -e "${COLOR_CODE}[$(date +%T)] ${AGENT_ROLE^^}: $1${NO_COLOR}"
    fi
}

# Ensure API key is set
if [ -z "${VIBECTL_ANTHROPIC_API_KEY:-}" ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo -e "${COLOR_CODE}Error: No API key provided. Please set VIBECTL_ANTHROPIC_API_KEY.${NO_COLOR}"
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

# Set custom instructions based on agent role
log "Setting custom instructions..."
if [ -f "${CUSTOM_INSTRUCTIONS_FILE}" ]; then
    vibectl config set custom_instructions "$(cat ${CUSTOM_INSTRUCTIONS_FILE})"
    log "Custom instructions set from file"
else
    # Default instructions based on role
    if [ "$AGENT_ROLE" = "blue" ]; then
        vibectl config set custom_instructions "You are a 'defender' agent whose role is to maintain system stability and service availability in a Kubernetes cluster.
1. Your goal is to monitor, protect, and restore services in the cluster.
2. Document your actions, observations, and results in memory.
3. When you see ERROR responses, try alternative approaches rather than giving up.
4. This is a controlled demo environment - focus on learning and building resilience knowledge."
    else
        vibectl config set custom_instructions "You are a 'chaos monkey' agent whose role is to introduce controlled disruptions into a Kubernetes cluster.
1. Your goal is to find and exploit vulnerabilities in the system to test resilience.
2. Document your actions, observations, and results in memory.
3. When you see ERROR responses, try alternative approaches rather than giving up.
4. This is a controlled demo environment - do not hesitate to take disruptive actions within the cluster."
    fi
    log "Default custom instructions set for role: ${AGENT_ROLE}"
fi

# Set up Kubernetes configuration using the shared config
log "Setting up Kubernetes configuration..."
mkdir -p /root/.kube

# Check for shared kubeconfig and fail if not available
if [ ! -f "${KUBE_CONFIG}" ]; then
    echo -e "${COLOR_CODE}ERROR: Shared kubeconfig not found at ${KUBE_CONFIG}${NO_COLOR}"
    echo -e "${COLOR_CODE}The demo requires a shared kubeconfig to be mounted${NO_COLOR}"
    exit 1
fi

# Use the shared config
export KUBECONFIG="${KUBE_CONFIG}"

# Copy to standard location for tools that may expect it there
cp "${KUBE_CONFIG}" /root/.kube/config

# Wait for Kubernetes to be available
log "Waiting for Kubernetes to be available..."
RETRY_COUNT=0
MAX_RETRIES=30

log "Connecting to Kubernetes API at $(kubectl config view -o jsonpath='{.clusters[0].cluster.server}')"

while ! kubectl get nodes --request-timeout=5s > /dev/null 2>&1; do
    echo -n "."
    RETRY_COUNT=$((RETRY_COUNT + 1))

    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo -e " ${COLOR_CODE}Failed to connect to Kubernetes after $MAX_RETRIES attempts${NO_COLOR}"
        echo -e "${COLOR_CODE}ERROR: Cannot connect to Kubernetes API server${NO_COLOR}"
        echo -e "${COLOR_CODE}Current kubeconfig:${NO_COLOR}"
        kubectl config view
        echo -e "${COLOR_CODE}Trying to reach API server:${NO_COLOR}"
        curl -k "$(kubectl config view -o jsonpath='{.clusters[0].cluster.server}')/version" || echo "Connection failed"
        exit 1
    fi

    sleep 2
done

echo -e " ${COLOR_CODE}Connected to Kubernetes!${NO_COLOR}"

# Verify connection
log "Cluster information:"
kubectl cluster-info
log "Nodes:"
kubectl get nodes

# Initialize vibectl memory with the content of memory-init.txt
log "Initializing vibectl memory..."
if [ -f "${MEMORY_INIT_FILE}" ]; then
    vibectl memory clear
    vibectl memory update "$(cat ${MEMORY_INIT_FILE})"
    log "Memory initialized from file"
else
    # Default memory content if file doesn't exist
    vibectl memory clear

    if [ "$AGENT_ROLE" = "blue" ]; then
        vibectl memory update "You are on a new Kubernetes cluster and should gather information before proceeding.

You are a blue team 'defender' agent. You'll be maintaining system stability and service availability.

Take some time to explore the cluster first. Check what's running, understand the environment, and identify the services you'll need to protect."
    else
        vibectl memory update "You are on a new Kubernetes cluster and should gather information before proceeding.

You are a red team 'chaos monkey' agent. You'll be introducing controlled failures to test system resilience.

Take some time to explore the cluster first. Check what's running, understand the environment, and identify potential targets for later chaos testing."
    fi

    log "Memory initialized with default content for role: ${AGENT_ROLE}"
fi

# Run the agent loop until session ends
log "Starting ${AGENT_ROLE} agent loop..."

# Add initial delay if needed (especially for red agent)
if [ ${INITIAL_DELAY} -gt 0 ]; then
    echo -e "${COLOR_CODE}${AGENT_ROLE^^}: Waiting ${INITIAL_DELAY} seconds before starting operations...${NO_COLOR}"
    sleep "${INITIAL_DELAY}"
fi

# Calculate session end time
DURATION_SECONDS=$((SESSION_DURATION * 60))
START_TIME=$(date +%s)
END_TIME=$((START_TIME + DURATION_SECONDS))

# Initialize action counter
ACTION_COUNT=0

# Create a marker file to track playbook addition
PLAYBOOK_ADDED=0

# Function to check k8s health - fail if connection is lost
check_k8s_health() {
  if ! kubectl get nodes >/dev/null 2>&1; then
    echo -e "${COLOR_CODE}⚠️ Kubernetes cluster connection lost, attempting to reconnect...${NO_COLOR}"

    # Try to reconnect one time
    sleep 5

    if ! kubectl get nodes >/dev/null 2>&1; then
      echo -e "${COLOR_CODE}❌ Failed to reconnect to cluster${NO_COLOR}"
      echo -e "${COLOR_CODE}ERROR: Lost connection to Kubernetes cluster${NO_COLOR}"
      exit 1
    else
      echo -e "${COLOR_CODE}✅ Reconnected to Kubernetes cluster${NO_COLOR}"
    fi
  fi
}

# Main loop
while true; do
    CURRENT_TIME=$(date +%s)
    REMAINING_SECONDS=$((END_TIME - CURRENT_TIME))

    # Exit if time is up
    if [ $REMAINING_SECONDS -le 0 ]; then
        echo -e "${COLOR_CODE}Session duration completed. Exiting...${NO_COLOR}"
        break
    fi

    # Display time remaining every minute
    if [ $((REMAINING_SECONDS % 60)) -eq 0 ]; then
        REMAINING_MINUTES=$((REMAINING_SECONDS / 60))
        echo -e "${COLOR_CODE}${AGENT_ROLE^^}: $REMAINING_MINUTES minutes remaining in session.${NO_COLOR}"
    fi

    # Increment action counter
    ACTION_COUNT=$((ACTION_COUNT + 1))
    log "Starting action #${ACTION_COUNT}"

    # After a few initial exploration actions, add the playbook to memory if it exists
    if [ $ACTION_COUNT -eq 3 ] && [ $PLAYBOOK_ADDED -eq 0 ] && [ -f "${PLAYBOOK_FILE}" ]; then
        echo -e "${COLOR_CODE}${AGENT_ROLE^^}: Adding playbook to memory...${NO_COLOR}"

        if [ "$AGENT_ROLE" = "blue" ]; then
            vibectl memory update "I've completed my initial exploration. Based on further planning, here are strategies I can use for system defense:

$(cat ${PLAYBOOK_FILE})"
        else
            vibectl memory update "I've completed my initial exploration. Based on further planning, here are strategies I can use for chaos testing:

$(cat ${PLAYBOOK_FILE})"
        fi

        PLAYBOOK_ADDED=1
    fi

    # Check cluster health before running vibectl
    check_k8s_health

    # Show memory in verbose mode
    if [ "${VERBOSE}" = "true" ]; then
        vibectl memory show
    fi

    # Run vibectl with auto-confirmation
    echo -e "${COLOR_CODE}${AGENT_ROLE^^}: Running vibectl...${NO_COLOR}"

    # Capture output for debugging
    VIBECTL_OUTPUT=$(mktemp)
    if ! vibectl vibe --yes > "$VIBECTL_OUTPUT" 2>&1; then
        ERROR_CODE=$?
        echo -e "${COLOR_CODE}⚠️ vibectl exited with code $ERROR_CODE - retrying in $ACTION_PAUSE_TIME seconds${NO_COLOR}"
        echo -e "${COLOR_CODE}──────────────────── vibectl output (for debugging) ────────────────────${NO_COLOR}"
        cat "$VIBECTL_OUTPUT"
        echo -e "${COLOR_CODE}──────────────────────────── end of output ─────────────────────────────${NO_COLOR}"
    else
        cat "$VIBECTL_OUTPUT"
    fi
    rm -f "$VIBECTL_OUTPUT"

    # Wait before next action
    echo -e "${COLOR_CODE}${AGENT_ROLE^^}: Waiting ${ACTION_PAUSE_TIME} seconds before next action...${NO_COLOR}"
    sleep "${ACTION_PAUSE_TIME}"
done

echo -e "${COLOR_CODE}${AGENT_ROLE^^}: Agent completed session.${NO_COLOR}"
