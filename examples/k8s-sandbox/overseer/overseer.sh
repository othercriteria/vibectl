#!/usr/bin/env bash
set -e

echo "🔍 Starting CTF Challenge Overseer"
echo "👑 Coordinating the sandbox environment and monitoring challenge status"

# Set default values
MIN_RUNTIME_SECONDS=${MIN_RUNTIME_SECONDS:-60}
SUCCESS_VERIFICATION_COUNT=${SUCCESS_VERIFICATION_COUNT:-2}
POLL_INTERVAL_SECONDS=${POLL_INTERVAL_SECONDS:-10}

# The status directory is shared between containers
STATUS_DIR=${STATUS_DIR:-"/tmp/status"}
mkdir -p "$STATUS_DIR"

# Status files
SANDBOX_STATUS_FILE="$STATUS_DIR/sandbox_status.json"
POLLER_STATUS_FILE="$STATUS_DIR/poller_status.json"
OVERSEER_STATUS_FILE="$STATUS_DIR/overseer_status.json"

# Initialize overseer status
cat > "$OVERSEER_STATUS_FILE" <<EOF
{
  "overseer_started_at": "$(date -Iseconds)",
  "challenge_status": "initializing",
  "active_ports": "$ACTIVE_PORTS",
  "difficulty": "$CHALLENGE_DIFFICULTY",
  "min_runtime_seconds": $MIN_RUNTIME_SECONDS,
  "success_verification_count": $SUCCESS_VERIFICATION_COUNT
}
EOF

# Set color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color

# Track challenge verification
declare -A PORT_SUCCESS_COUNT
START_TIME=$(date +%s)

echo -e "${BLUE}=== CTF Challenge Overseer Configuration ===${NC}"
echo -e "Challenge Difficulty: ${GREEN}$CHALLENGE_DIFFICULTY${NC}"
echo -e "Active Ports: ${GREEN}$ACTIVE_PORTS${NC}"
echo -e "Minimum Runtime: ${GREEN}$MIN_RUNTIME_SECONDS seconds${NC}"
echo -e "Verification Count: ${GREEN}$SUCCESS_VERIFICATION_COUNT attempts${NC}"
echo -e "${BLUE}=============================================${NC}"

# Update overseer status
update_overseer_status() {
  local status=$1
  local message=$2
  local current_time=$(date -Iseconds)

  jq --arg status "$status" \
     --arg message "$message" \
     --arg time "$current_time" \
     '.challenge_status = $status | .last_updated = $time | .status_message = $message' \
     "$OVERSEER_STATUS_FILE" > "${OVERSEER_STATUS_FILE}.tmp" && mv "${OVERSEER_STATUS_FILE}.tmp" "$OVERSEER_STATUS_FILE"

  echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} Status: ${GREEN}$status${NC} - $message"
}

# Check if sandbox is healthy
check_sandbox_health() {
  if ! docker ps | grep -q "k8s-sandbox"; then
    echo -e "${RED}Sandbox container not running! Exiting...${NC}"
    update_overseer_status "failed" "Sandbox container not running"
    exit 1
  fi
}

# Verify a service on a port
verify_service() {
  local port=$1
  local expected_flag=$2

  # Check if port is specified in active ports
  if [[ ! "$ACTIVE_PORTS" == *"$port"* ]]; then
    # Port not active, so consider it already verified
    return 0
  fi

  # Get the Kind container details
  local kind_container="ctf-cluster-control-plane"
  local kind_ip

  kind_ip=$(docker exec k8s-sandbox bash -c "docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' $kind_container 2>/dev/null" 2>/dev/null || echo "")

  if [ -z "$kind_ip" ]; then
    echo -e "${YELLOW}Could not determine Kind container IP${NC}"
    return 1
  fi

  # Check if port is listening
  if ! docker exec k8s-sandbox bash -c "nc -z $kind_ip $port 2>/dev/null"; then
    echo -e "${YELLOW}Port $port is not listening on Kind container${NC}"
    return 1
  fi

  # Check response content
  local response
  response=$(docker exec k8s-sandbox bash -c "curl -s --connect-timeout 5 --max-time 10 http://${kind_ip}:$port")

  if [ -z "$response" ]; then
    echo -e "${YELLOW}Empty response from port $port${NC}"
    return 1
  fi

  # Check for expected flag
  if echo "$response" | grep -q "$expected_flag"; then
    if ! echo "$response" | grep -qi "error\|exception\|failed\|denied"; then
      echo -e "${GREEN}Found flag on port $port!${NC}"
      return 0
    else
      echo -e "${YELLOW}Response contains error message with flag-like text${NC}"
      echo -e "${GRAY}$response${NC}"
      return 1
    fi
  else
    echo -e "${YELLOW}Port $port returned unexpected content${NC}"
    echo -e "${GRAY}$response${NC}"
    return 1
  fi
}

# Check all services
check_all_services() {
  local all_verified=true
  local status_message=""

  # Split active ports
  IFS=',' read -ra PORT_ARRAY <<< "$ACTIVE_PORTS"

  for port in "${PORT_ARRAY[@]}"; do
    local expected_flag=""

    # Determine which flag to expect based on the port
    case "$port" in
      30001)
        expected_flag="CTF-FLAG-1: K8S_MASTER"
        ;;
      30002)
        expected_flag="CTF-FLAG-2: VIBECTL_PRO"
        ;;
      30003)
        expected_flag="CTF-FLAG-3: CHALLENGE_COMPLETE"
        ;;
    esac

    echo -e "${BLUE}Checking service on port $port...${NC}"

    if verify_service "$port" "$expected_flag"; then
      # Increment success count for this port
      if [ -z "${PORT_SUCCESS_COUNT[$port]}" ]; then
        PORT_SUCCESS_COUNT[$port]=1
      else
        PORT_SUCCESS_COUNT[$port]=$((PORT_SUCCESS_COUNT[$port] + 1))
      fi

      echo -e "${GREEN}Port $port check ${PORT_SUCCESS_COUNT[$port]}/${SUCCESS_VERIFICATION_COUNT} successful${NC}"

      # Check if we've reached the verification threshold
      if [ "${PORT_SUCCESS_COUNT[$port]}" -lt "$SUCCESS_VERIFICATION_COUNT" ]; then
        all_verified=false
        status_message="Port $port verified ${PORT_SUCCESS_COUNT[$port]}/${SUCCESS_VERIFICATION_COUNT} times"
      fi
    else
      # Reset counter on failure
      if [ -n "${PORT_SUCCESS_COUNT[$port]}" ] && [ "${PORT_SUCCESS_COUNT[$port]}" -gt 0 ]; then
        echo -e "${YELLOW}Reset port $port check count after failure${NC}"
        PORT_SUCCESS_COUNT[$port]=0
      fi

      all_verified=false
      status_message="Port $port verification failed"
    fi
  done

  # Return result
  if $all_verified; then
    return 0
  else
    echo -e "${YELLOW}$status_message${NC}"
    return 1
  fi
}

# Signal all containers to shut down gracefully
shutdown_all() {
  local exit_code=$1
  local message=$2

  echo -e "${GREEN}$message${NC}"
  update_overseer_status "completed" "$message"

  # First, notify all containers of success
  echo -e "${BLUE}Notifying containers of successful completion...${NC}"

  # Create a completion marker for others to see
  cat > "$STATUS_DIR/challenge_complete.json" << EOF
{
  "completed_at": "$(date -Iseconds)",
  "success": true,
  "message": "$message"
}
EOF

  # Give the poller a moment to see the completion status
  sleep 3

  echo -e "${BLUE}Shutting down containers in order...${NC}"

  # First stop the poller (it's only monitoring)
  echo -e "${YELLOW}Stopping poller container...${NC}"
  docker stop k8s-poller >/dev/null 2>&1 || true

  # Then stop the sandbox (main container)
  echo -e "${YELLOW}Stopping sandbox container...${NC}"
  docker stop k8s-sandbox >/dev/null 2>&1 || true

  echo -e "${GREEN}Challenge cleanup complete! Shutting down overseer...${NC}"

  # Exit with the specified code (after a brief pause)
  sleep 1
  exit "$exit_code"
}

# Main monitoring loop
update_overseer_status "running" "Monitoring challenge services"

while true; do
  # Check if we've met minimum runtime
  CURRENT_TIME=$(date +%s)
  RUNTIME=$((CURRENT_TIME - START_TIME))

  # Always check sandbox health
  check_sandbox_health

  # Don't verify services until minimum runtime has passed
  if [ "$RUNTIME" -lt "$MIN_RUNTIME_SECONDS" ]; then
    echo -e "${YELLOW}Running for ${RUNTIME}s of ${MIN_RUNTIME_SECONDS}s minimum runtime${NC}"
    sleep "$POLL_INTERVAL_SECONDS"
    continue
  fi

  # Check all services
  if check_all_services; then
    # All services verified the required number of times
    shutdown_all 0 "🏆 All services verified successfully! Challenge complete!"
  fi

  # Sleep before next check
  sleep "$POLL_INTERVAL_SECONDS"
done
