#!/usr/bin/env bash
set -e

# This script is now simplified to focus on checking services and reporting status
# rather than making decisions about when to exit
echo "🔍 Starting CTF Challenge Poller Service"
echo "👀 Checking service availability - success determination handled by overseer"

# Set color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color

# Status directory shared with overseer
STATUS_DIR=${STATUS_DIR:-"/tmp/status"}
mkdir -p "$STATUS_DIR" || echo -e "${YELLOW}⚠️ Could not create status directory - it may already exist${NC}"
POLLER_STATUS_FILE="$STATUS_DIR/poller_status.json"
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
  echo "The overseer must be running and generating configuration before the poller starts."
  exit 1
fi

# Get configuration directly from the JSON file
echo -e "${BLUE}📝 Loading configuration from JSON...${NC}"
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

# For convenience, assign variables used in the original script
PORT_1=$NODE_PORT_1
PORT_2=$NODE_PORT_2
PORT_3=$NODE_PORT_3

echo "🚩 Using expected flags:"
echo "  - Flag 1: $EXPECTED_FLAG_1 on port $PORT_1"
echo "  - Flag 2: $EXPECTED_FLAG_2 on port $PORT_2"
echo "  - Flag 3: $EXPECTED_FLAG_3 on port $PORT_3"
echo "🔍 Monitoring ports: $ACTIVE_PORTS"

# Initialize flags based on challenge configuration
declare -A FLAGS_ACTIVE
declare -A FLAGS_FOUND
declare -A PORT_TO_EXPECTED_FLAG
declare -A PORT_SUCCESS_COUNT  # Track success count for each port

# Associate ports with flags and initialize active/found status
PORT_TO_EXPECTED_FLAG[$PORT_1]="$EXPECTED_FLAG_1"
PORT_TO_EXPECTED_FLAG[$PORT_2]="$EXPECTED_FLAG_2"
PORT_TO_EXPECTED_FLAG[$PORT_3]="$EXPECTED_FLAG_3"

# Set active flag based on whether the port is in the active ports list
for port in $PORT_1 $PORT_2 $PORT_3; do
  if [[ "$ACTIVE_PORTS" == *"$port"* ]]; then
    FLAGS_ACTIVE[$port]=true
    FLAGS_FOUND[$port]=false
    PORT_SUCCESS_COUNT[$port]=0  # Initialize success count
    echo "✅ Challenge for port $port is active"
  else
    FLAGS_ACTIVE[$port]=false
    FLAGS_FOUND[$port]=true  # Mark as found since we don't need to check it
    PORT_SUCCESS_COUNT[$port]=$VERIFICATION_COUNT  # Set to max
    echo "ℹ️ Challenge for port $port is not active in this difficulty level"
  fi
done

# Function to print status
print_status() {
  echo -e "${BLUE}=== CTF Challenge Status ===${NC}"

  for port in $PORT_1 $PORT_2 $PORT_3; do
    local port_number="${port##*_}"
    if [[ "${FLAGS_ACTIVE[$port]}" != "true" ]]; then
      echo -e "Port $port: ${GRAY}NOT ACTIVE${NC}"
    elif [[ "${FLAGS_FOUND[$port]}" == "true" ]]; then
      echo -e "Port $port: ${GREEN}COMPLETED ✅${NC}"
    else
      echo -e "Port $port: ${RED}PENDING (${PORT_SUCCESS_COUNT[$port]}/${VERIFICATION_COUNT}) ❌${NC}"
    fi
  done

  echo -e "${BLUE}=========================${NC}"
}

# Function to check if the service is ready
check_service() {
  local port=$1
  local expected_flag=${PORT_TO_EXPECTED_FLAG[$port]}
  local container_id

  container_id=$(find_sandbox_container) || return 1

  # Check if docker exec command works at all
  if ! docker exec "$container_id" echo "Connection test" >/dev/null 2>&1; then
    echo -e "${RED}Cannot connect to sandbox container.${NC}"
    return 1
  fi

  # Get the Kind container ID (direct access to nodes)
  local kind_container="${KIND_CONTAINER:-ctf-cluster-control-plane}"
  local kind_container_ip

  # Get the IP address of the Kind container (where K8s is actually running)
  kind_container_ip=$(docker exec "$container_id" bash -c "docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' $kind_container 2>/dev/null" 2>/dev/null || echo "")

  if [ -z "$kind_container_ip" ]; then
    echo -e "${YELLOW}Could not determine Kind container IP${NC}"
    return 1
  fi

  # Direct access to the Kind container (most reliable method)
  echo -e "${BLUE}Checking service at Kind container ${kind_container} (${kind_container_ip}:$port)${NC}"
  if ! docker exec "$container_id" bash -c "nc -z $kind_container_ip $port 2>/dev/null"; then
    echo -e "${YELLOW}Port $port is not listening on Kind container${NC}"
    return 1
  fi

  echo -e "${YELLOW}Port $port is accessible on Kind container, trying to get content...${NC}"
  local response
  response=$(docker exec "$container_id" bash -c "curl -s --connect-timeout 5 --max-time 10 http://${kind_container_ip}:$port")

  # More strict flag detection - require exact flag text and verify it's not part of an error message
  if [ -z "$response" ]; then
    echo -e "${YELLOW}Empty response from port $port${NC}"
    return 1
  fi

  # Require exact flag match with word boundaries and not part of a longer string
  if echo "$response" | grep -q "^$expected_flag$" || echo "$response" | grep -q "^.*$expected_flag.*$"; then
    # Additional verification - make sure we don't have error terms in the response
    if echo "$response" | grep -qi "error\|exception\|failed\|denied"; then
      echo -e "${YELLOW}Response contains error message with flag-like text. Not counting as success.${NC}"
      echo -e "${GRAY}$response${NC}"
      return 1
    fi

    # Verify we can consistently get the flag (avoid transient positives)
    echo -e "${YELLOW}Found potential flag, verifying with second request...${NC}"
    local second_response
    second_response=$(docker exec "$container_id" bash -c "curl -s --connect-timeout 5 --max-time 10 http://${kind_container_ip}:$port")

    if echo "$second_response" | grep -q "$expected_flag"; then
      echo -e "${GREEN}Found flag via Kind container and verified with second request!${NC}"
      return 0
    else
      echo -e "${YELLOW}Could not verify flag with second request. First response might have been transient.${NC}"
      return 1
    fi
  else
    echo -e "${YELLOW}Kind container port $port returned incorrect content:${NC}"
    echo -e "${GRAY}$response${NC}"
    return 1
  fi
}

# Find the sandbox container ID
find_sandbox_container() {
  # If TARGET_HOST is set and valid, use it directly
  if [ -n "$TARGET_HOST" ] && docker ps --format '{{.Names}}' | grep -q "^${TARGET_HOST}$"; then
    echo "$TARGET_HOST"
    return 0
  fi

  # Fallback to pattern matching if the explicit name isn't found
  # Try different naming patterns that Docker Compose might use
  local container_id

  container_id=$(docker ps | grep -E "(k8s-sandbox|vibectl.*sandbox|sandbox)" | grep -v "poller" | awk '{print $1}' | head -1)

  if [ -z "$container_id" ]; then
    # If no container ID found, try to get container name
    container_id=$(docker ps --format '{{.Names}}' | grep -E "(k8s-sandbox|vibectl.*sandbox|sandbox)" | grep -v "poller" | head -1)

    if [ -z "$container_id" ]; then
      echo "Error: Could not find sandbox container"
      return 1
    fi
  fi

  echo "$container_id"
}

# Update status for overseer
update_status() {
  local all_complete=$1

  # Create a JSON object with the current state
  local json_data='{'
  json_data+='"last_updated": "'$(date -Iseconds)'",'
  json_data+='"verification_count": '$VERIFICATION_COUNT','

  # Add status for each port
  for port in $PORT_1 $PORT_2 $PORT_3; do
    local active="${FLAGS_ACTIVE[$port]}"
    local found="${FLAGS_FOUND[$port]}"
    local success_count="${PORT_SUCCESS_COUNT[$port]}"
    json_data+='"port_'$port'_active": '$active','
    json_data+='"port_'$port'_found": '$found','
    json_data+='"port_'$port'_success_count": '$success_count','
  done

  # Add all_complete flag
  json_data+='"all_complete": '$all_complete
  json_data+='}'

  # Write to status file
  echo "$json_data" > "$POLLER_STATUS_FILE" 2>/dev/null || echo -e "${YELLOW}⚠️ Could not write to status file ${POLLER_STATUS_FILE}${NC}"
}

# Wait for the sandbox to be ready
echo -e "${YELLOW}Waiting for sandbox Kubernetes cluster to be ready...${NC}"

# Wait for sandbox container to be ready
while ! docker ps | grep -E "(k8s-sandbox|vibectl.*sandbox|sandbox)" | grep -v "poller" > /dev/null; do
  echo -e "${YELLOW}Waiting for sandbox container to start...${NC}"
  sleep 5
done

echo -e "${GREEN}Sandbox container is running! Starting to check for services...${NC}"

# Initialize check counter
CHECK_COUNT=0

# Main polling loop - check services and report status, also check for completion signal
while true; do
  # Check if the challenge has been completed (by the overseer)
  COMPLETION_FILE="$STATUS_DIR/challenge_complete.json"
  if [ -f "$COMPLETION_FILE" ]; then
    echo -e "${GREEN}🏆 Challenge completion detected! Poller exiting gracefully...${NC}"
    print_status
    exit 0
  fi

  # Only display status every 3 checks to reduce noise
  if [ $CHECK_COUNT -eq 0 ] || [ $((CHECK_COUNT % 3)) -eq 0 ]; then
    print_status
  fi
  CHECK_COUNT=$((CHECK_COUNT + 1))

  # Check all active ports
  for port in $PORT_1 $PORT_2 $PORT_3; do
    if [[ "${FLAGS_ACTIVE[$port]}" == "true" ]] && [[ "${FLAGS_FOUND[$port]}" != "true" ]]; then
      if check_service "$port"; then
        # Increment success count for this port
        PORT_SUCCESS_COUNT[$port]=$((PORT_SUCCESS_COUNT[$port] + 1))
        echo -e "${GREEN}Port $port check ${PORT_SUCCESS_COUNT[$port]}/${VERIFICATION_COUNT} successful${NC}"

        # Check if we've reached the verification threshold
        if [ "${PORT_SUCCESS_COUNT[$port]}" -ge "$VERIFICATION_COUNT" ]; then
          echo -e "${GREEN}FLAG for port $port VERIFIED! (${PORT_SUCCESS_COUNT[$port]}/${VERIFICATION_COUNT}) 🎉${NC}"
          FLAGS_FOUND[$port]=true
          print_status
        fi
      else
        # Reset counter on failure
        if [ -n "${PORT_SUCCESS_COUNT[$port]}" ] && [ "${PORT_SUCCESS_COUNT[$port]}" -gt 0 ]; then
          echo -e "${YELLOW}Reset port $port check count after failure${NC}"
          PORT_SUCCESS_COUNT[$port]=0
        fi
      fi
    fi
  done

  # Check if all active challenges are complete
  ALL_COMPLETE=true
  for port in $PORT_1 $PORT_2 $PORT_3; do
    if [[ "${FLAGS_ACTIVE[$port]}" == "true" ]] && [[ "${FLAGS_FOUND[$port]}" != "true" ]]; then
      ALL_COMPLETE=false
      break
    fi
  done

  # Update status file for the overseer
  update_status $ALL_COMPLETE

  # Wait before next check - check for completion file more frequently
  for i in {1..3}; do
    # Check for completion every 5 seconds during the wait
    sleep 5
    if [ -f "$STATUS_DIR/challenge_complete.json" ]; then
      echo -e "${GREEN}🏆 Challenge completion detected! Poller exiting gracefully...${NC}"
      print_status
      exit 0
    fi
  done
done
