#!/bin/bash
set -euo pipefail

# Required environment variables
# AGENT_ROLE=blue|red - Role of the agent (blue=defender, red=attacker)
# AGENT_NAME=defender|attacker - Human-readable name of the agent
# MEMORY_INIT_FILE - Path to the memory initialization file
# PLAYBOOK_FILE - Path to the agent's playbook (defense or attack)
# CUSTOM_INSTRUCTIONS_FILE - Path to custom instructions file

# Default values if not set in environment
MEMORY_MAX_CHARS=${MEMORY_MAX_CHARS:-2000}
ACTION_PAUSE_TIME=${ACTION_PAUSE_TIME:-30}
VERBOSE=${VERBOSE:-false}
# Use AGENT_KUBECONFIG_PATH if provided, otherwise default (though default won't work correctly now)
KUBE_CONFIG=${AGENT_KUBECONFIG_PATH:-/config/kube/agent-config} # Default path changed
AGENT_ROLE=${AGENT_ROLE:-blue}
AGENT_NAME=${AGENT_NAME:-defender}
MEMORY_INIT_FILE=${MEMORY_INIT_FILE:-/memory-init.txt}
PLAYBOOK_FILE=${PLAYBOOK_FILE:-/playbook.md}
CUSTOM_INSTRUCTIONS_FILE=${CUSTOM_INSTRUCTIONS_FILE:-/custom-instructions.txt}
VIBECTL_MODEL=${VIBECTL_MODEL:-claude-3-5-sonnet-20240620}
USE_STABLE_VERSIONS=${USE_STABLE_VERSIONS:-false}

# --- Setup Colors and Logging ---
# Set color for agent output
if [ "$AGENT_ROLE" = "blue" ]; then
    COLOR_CODE="\033[34m" # Blue color
    AGENT_ROLE_DISPLAY="Blue"
elif [ "$AGENT_ROLE" = "red" ]; then
    COLOR_CODE="\033[31m" # Red color
    AGENT_ROLE_DISPLAY="Red"
else
    COLOR_CODE="\033[0m" # Default color
    AGENT_ROLE_DISPLAY=$(echo "$AGENT_ROLE" | awk '{print toupper(substr($0,1,1))tolower(substr($0,2))}') # Capitalize first letter
fi
NO_COLOR="\033[0m"

echo -e "${COLOR_CODE}Starting ${AGENT_ROLE_DISPLAY} agent (${AGENT_NAME})...${NO_COLOR}"
echo -e "${COLOR_CODE}Role: ${AGENT_ROLE}${NO_COLOR}"
echo -e "${COLOR_CODE}Model: ${VIBECTL_MODEL}${NO_COLOR}"
echo -e "${COLOR_CODE}Memory Max Chars: ${MEMORY_MAX_CHARS}${NO_COLOR}"
echo -e "${COLOR_CODE}Action Pause Time: ${ACTION_PAUSE_TIME}s${NO_COLOR}"
echo -e "${COLOR_CODE}Passive Duration: ${PASSIVE_DURATION} minutes${NO_COLOR}"
echo -e "${COLOR_CODE}Active Duration: ${ACTIVE_DURATION} minutes${NO_COLOR}"
echo -e "${COLOR_CODE}Verbose: ${VERBOSE}${NO_COLOR}"

# Enhanced logging for verbose mode
function log() {
    # Only log if VERBOSE is true
    if [ "${VERBOSE}" = "true" ]; then
        echo -e "${COLOR_CODE}[$(date +%T)] ${AGENT_ROLE^^}: $1${NO_COLOR}"
    fi
}

# --- Dependency Installation ---
log "Starting dependency installation..."

# Determine package source based on USE_STABLE_VERSIONS
if [ "${USE_STABLE_VERSIONS}" = "true" ]; then
    # Use stable versions from PyPI
    log "Using stable versions from PyPI"
    echo -e "${COLOR_CODE}Installing stable package versions from PyPI...${NO_COLOR}"

    # Define versions (replace with actual desired stable versions)
    VIBECTL_VERSION=${VIBECTL_VERSION:-latest} # Example: Use latest or specific like 0.4.1
    LLM_VERSION=${LLM_VERSION:-latest}
    LLM_ANTHROPIC_VERSION=${LLM_ANTHROPIC_VERSION:-latest}
    ANTHROPIC_SDK_VERSION=${ANTHROPIC_SDK_VERSION:-latest}

    # Install specific versions of packages
    pip install --no-cache-dir \
        llm==${LLM_VERSION} \
        llm-anthropic==${LLM_ANTHROPIC_VERSION} \
        anthropic==${ANTHROPIC_SDK_VERSION} \
        vibectl==${VIBECTL_VERSION}

    # Make sure we're using the installed versions
    echo -e "${COLOR_CODE}Installed stable package versions from PyPI:${NO_COLOR}"
    echo -e "${COLOR_CODE}- vibectl: $(pip show vibectl | grep Version | awk '{print $2}')${NO_COLOR}"
    echo -e "${COLOR_CODE}- llm: $(pip show llm | grep Version | awk '{print $2}')${NO_COLOR}"
    echo -e "${COLOR_CODE}- llm-anthropic: $(pip show llm-anthropic | grep Version | awk '{print $2}')${NO_COLOR}"
    echo -e "${COLOR_CODE}- anthropic: $(pip show anthropic | grep Version | awk '{print $2}')${NO_COLOR}"
    log "Using vibectl found at: $(command -v vibectl)"
    # Show local dependencies if possible/needed
    # pip freeze | grep -E 'vibectl|llm|anthropic'
else
    # Local development path
    log "Installing required dependencies for local development (llm, llm-anthropic, anthropic)..."

    echo -e "${COLOR_CODE}Installing dependencies: llm, llm-anthropic, anthropic${ANTHROPIC_SDK_VERSION}${NO_COLOR}"
    if ! pip install --no-cache-dir \
        llm \
        llm-anthropic \
        anthropic; then
        echo -e "${COLOR_CODE}ERROR: Failed to install core dependencies (llm, llm-anthropic, anthropic).${NO_COLOR}"
        exit 1
    fi
    log "Core dependencies installed."

    log "Installing vibectl from source directory /vibectl-src"
    if [ -d "/vibectl-src" ]; then
        cd /vibectl-src
        echo -e "${COLOR_CODE}Installing vibectl from source...${NO_COLOR}"
        # Install editable, allowing pip to handle vibectl's direct dependencies
        if ! pip install --no-cache-dir -e .; then
             echo -e "${COLOR_CODE}ERROR: Failed to install vibectl from source using -e .${NO_COLOR}"
             exit 1
        fi
        cd - >/dev/null
        echo -e "${COLOR_CODE}vibectl installed from source. Version: $(pip show vibectl | grep Version | awk '{print $2}')${NO_COLOR}"
    else
        echo -e "${COLOR_CODE}ERROR: vibectl source directory not found at /vibectl-src and USE_STABLE_VERSIONS is not true.${NO_COLOR}"
        echo -e "${COLOR_CODE}Please ensure the repository is mounted correctly or use the --use-stable-versions flag.${NO_COLOR}"
        exit 1
    fi
fi

# Ensure vibectl is properly installed
if ! command -v vibectl &> /dev/null; then
    echo -e "${COLOR_CODE}ERROR: vibectl command not found after installation attempt.${NO_COLOR}"
    exit 1
fi
log "vibectl installation verified."

# --- API Key Configuration ---
log "Configuring API key..."
# Ensure API key is set (prefer VIBECTL_ANTHROPIC_API_KEY, fallback to ANTHROPIC_API_KEY)
if [ -z "${VIBECTL_ANTHROPIC_API_KEY:-}" ] && [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    export VIBECTL_ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}"
    log "Using ANTHROPIC_API_KEY for VIBECTL_ANTHROPIC_API_KEY."
elif [ -z "${VIBECTL_ANTHROPIC_API_KEY:-}" ]; then
    echo -e "${COLOR_CODE}Error: No API key provided. Please set VIBECTL_ANTHROPIC_API_KEY.${NO_COLOR}"
    exit 1
fi

# Configure vibectl using the llm tool approach
LLM_KEYS_PATH=$(llm keys path)
if [ -z "$LLM_KEYS_PATH" ]; then
    echo -e "${COLOR_CODE}Error: Could not determine keys path from llm tool.${NO_COLOR}"
    exit 1
fi
log "Using LLM keys path: $LLM_KEYS_PATH"
mkdir -p "$(dirname "$LLM_KEYS_PATH")"

# Write the keys file directly
cat > "$LLM_KEYS_PATH" << EOF
{
  "anthropic": "$VIBECTL_ANTHROPIC_API_KEY"
}
EOF
chmod 600 "$LLM_KEYS_PATH"
log "LLM API key configured via keys file."

# --- Vibectl Configuration ---
log "Configuring vibectl settings..."
vibectl config set model "${VIBECTL_MODEL}"
vibectl config set memory_max_chars ${MEMORY_MAX_CHARS}
vibectl config set show_memory true
vibectl config set show_streaming false
vibectl config set show_iterations true

# Configure output options based on verbose mode
if [ "$VERBOSE" = "true" ]; then
    echo -e "${COLOR_CODE}${AGENT_ROLE^^}: Verbose mode enabled: showing raw output and kubectl commands${NO_COLOR}"
    vibectl config set show_raw_output true
    vibectl config set show_kubectl true
    vibectl config set show_metrics true
    export VIBECTL_TRACEBACK=1 # Enable tracebacks for debugging
else
    vibectl config set show_raw_output false
    vibectl config set show_kubectl false
    vibectl config set show_metrics false
fi

# --- Custom Instructions Setup ---
log "Reading custom instructions..."
if [ ! -f "${CUSTOM_INSTRUCTIONS_FILE}" ]; then
    echo -e "${COLOR_CODE}ERROR: Custom instructions file not found at ${CUSTOM_INSTRUCTIONS_FILE}${NO_COLOR}"
    exit 1
fi
ORIGINAL_CUSTOM_INSTRUCTIONS=$(cat "${CUSTOM_INSTRUCTIONS_FILE}")
log "Original custom instructions loaded."
# Initially set the original instructions via config
vibectl config set custom_instructions "${ORIGINAL_CUSTOM_INSTRUCTIONS}"

# --- Kubernetes Setup ---
echo -e "[$(date +%H:%M:%S)] ${COLOR_CODE}${AGENT_ROLE^^}:${NO_COLOR} Setting up Kubernetes configuration..."

# Wait for shared kubeconfig and fail if not available after timeout
MAX_RETRIES=30
RETRY_COUNT=0
RETRY_INTERVAL=5
log "Waiting for agent-specific kubeconfig file at ${KUBE_CONFIG}..."
while [ ! -f "${KUBE_CONFIG}" ]; do
    echo -n "."
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo ""
        echo -e "${COLOR_CODE}ERROR: Agent kubeconfig not found at ${KUBE_CONFIG} after ${MAX_RETRIES} retries.${NO_COLOR}"
        # Check if the default shared config exists as a fallback hint
        if [ -f "/config/kube/config" ]; then
            echo -e "${COLOR_CODE}Hint: The old shared config (/config/kube/config) was found. Ensure docker-compose passes the correct AGENT_KUBECONFIG_PATH variable.${NO_COLOR}"
        fi
        exit 1
    fi
    sleep $RETRY_INTERVAL
done
echo "" # New line after waiting dots
log "Agent kubeconfig found at ${KUBE_CONFIG}"

# Use the specific agent config
export KUBECONFIG="${KUBE_CONFIG}"
mkdir -p /root/.kube
cp "${KUBE_CONFIG}" /root/.kube/config # Copy to default location for tools that expect it there
log "Agent kubeconfig set and copied to /root/.kube/config."

# Wait for Kubernetes API to be available
log "Waiting for Kubernetes API server to be available..."
RETRY_COUNT=0
log "Connecting to Kubernetes API at $(kubectl config view -o jsonpath='{.clusters[0].cluster.server}')"
while ! kubectl get nodes --request-timeout=5s > /dev/null 2>&1; do
    echo -n "."
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo -e " ${COLOR_CODE}Failed to connect to Kubernetes API after $MAX_RETRIES attempts.${NO_COLOR}"
        # Provide more debugging info
        echo -e "${COLOR_CODE}Attempting connection details:${NO_COLOR}"
        kubectl config view
        echo -e "${COLOR_CODE}Attempting to curl API server version endpoint:${NO_COLOR}"
        curl -k "$(kubectl config view -o jsonpath='{.clusters[0].cluster.server}')/version" || echo "Curl connection failed"
        exit 1
    fi
    sleep 2
done
echo "" # Ensure we're on a new line after dots
echo -e "${COLOR_CODE}Connected to Kubernetes!${NO_COLOR}"

# Verify connection
log "Cluster information:"
kubectl cluster-info
log "Nodes:"
kubectl get nodes

# Function to check k8s health - fail if connection is lost
check_k8s_health() {
  if ! kubectl get nodes --request-timeout=5s >/dev/null 2>&1; then
    echo -e "${COLOR_CODE}⚠️ Kubernetes cluster connection lost, attempting to reconnect...${NO_COLOR}"
    sleep 5
    if ! kubectl get nodes --request-timeout=5s >/dev/null 2>&1; then
      echo -e "${COLOR_CODE}❌ Failed to reconnect to cluster. Exiting.${NO_COLOR}"
      exit 1
    else
      echo -e "${COLOR_CODE}✅ Reconnected to Kubernetes cluster${NO_COLOR}"
    fi
  fi
}

# --- Agent Initialization & Memory Setup ---

# Initialize vibectl memory with the base instructions
log "Initializing vibectl memory with base instructions..."
if [ -f "${MEMORY_INIT_FILE}" ]; then
    vibectl memory clear
    if ! vibectl memory update "$(cat "${MEMORY_INIT_FILE}")"; then
        echo -e "${COLOR_CODE}ERROR: Failed to initialize memory from ${MEMORY_INIT_FILE}${NO_COLOR}"
        exit 1
    fi
    log "Base memory initialized from file: ${MEMORY_INIT_FILE}"
else
    echo -e "${COLOR_CODE}ERROR: Base memory initialization file not found at ${MEMORY_INIT_FILE}${NO_COLOR}"
    exit 1
fi

# Add the playbook content to memory if it exists
if [ -f "${PLAYBOOK_FILE}" ]; then
    log "Injecting playbook from ${PLAYBOOK_FILE}"
    playbook_content="$(cat "${PLAYBOOK_FILE}")"
    # Use a clear prompt indicating this is a playbook
    playbook_prompt="Here is your strategic playbook to consult:\n${playbook_content}"
    if ! vibectl memory update "${playbook_prompt}"; then
        echo -e "${COLOR_CODE}WARNING: Failed to inject playbook into memory.${NO_COLOR}"
    fi
    log "Playbook content injected into memory."
else
    log "Playbook file not found at ${PLAYBOOK_FILE}. Proceeding without playbook guidance."
fi

# Add the notification about the phased RBAC
# Get PASSIVE_DURATION from env, default to 5 if not set (should be set by compose)
PASSIVE_DURATION=${PASSIVE_DURATION:-5}
log "Injecting notification about phased RBAC (Passive phase: ${PASSIVE_DURATION} minutes)..."
PHASE_NOTIFICATION="IMPORTANT OPERATIONAL NOTE: You will operate in two phases. For the first ${PASSIVE_DURATION} minutes, you are in a passive, read-only observation phase with restricted Kubernetes RBAC permissions (get, list, watch only). Use this time to explore and understand the environment WITHOUT making changes. After ${PASSIVE_DURATION} minutes, your RBAC permissions will automatically expand to allow active operations according to your role. Plan your actions accordingly."

if ! vibectl memory update "${PHASE_NOTIFICATION}"; then
     echo -e "${COLOR_CODE}WARNING: Failed to inject phased RBAC notification into memory.${NO_COLOR}"
fi
log "Phased RBAC notification injected."

check_k8s_health

echo -e "${COLOR_CODE}${AGENT_ROLE^^}: Starting continuous autonomous operation with interval ${ACTION_PAUSE_TIME}s...${NO_COLOR}"

# Run vibectl auto indefinitely with the specified interval
# Let Docker Compose or the k8s-entrypoint.sh script handle stopping the container.
if ! vibectl auto --interval ${ACTION_PAUSE_TIME}; then
    echo -e "${COLOR_CODE}ERROR: vibectl auto command exited unexpectedly.${NO_COLOR}"
fi

# This part might not be reached
echo -e "${COLOR_CODE}${AGENT_ROLE^^}: Agent process finished or was interrupted. Exiting.${NO_COLOR}"
