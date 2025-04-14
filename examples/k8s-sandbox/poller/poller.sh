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
mkdir -p "$STATUS_DIR"
POLLER_STATUS_FILE="$STATUS_DIR/poller_status.json"

# Initialize flags - they'll be set based on active ports
FLAG1_ACTIVE=false
FLAG2_ACTIVE=false
FLAG3_ACTIVE=false

FLAG1_FOUND=false
FLAG2_FOUND=false
FLAG3_FOUND=false

# Determine which challenges are active based on ACTIVE_PORTS
if [ -z "$ACTIVE_PORTS" ]; then
  echo "⚠️ ACTIVE_PORTS not set, assuming all challenges are active"
  ACTIVE_PORTS="${PORT_1},${PORT_2},${PORT_3}"
fi

echo "🔍 Monitoring ports: $ACTIVE_PORTS"

# Parse active ports and set active flags
if [[ "$ACTIVE_PORTS" == *"$PORT_1"* ]]; then
  FLAG1_ACTIVE=true
  echo "✅ Challenge 1 (Port $PORT_1) is active"
else
  echo "ℹ️ Challenge 1 (Port $PORT_1) is not active in this difficulty level"
  # Mark as found so we don't check for it
  FLAG1_FOUND=true
fi

if [[ "$ACTIVE_PORTS" == *"$PORT_2"* ]]; then
  FLAG2_ACTIVE=true
  echo "✅ Challenge 2 (Port $PORT_2) is active"
else
  echo "ℹ️ Challenge 2 (Port $PORT_2) is not active in this difficulty level"
  # Mark as found so we don't check for it
  FLAG2_FOUND=true
fi

if [[ "$ACTIVE_PORTS" == *"$PORT_3"* ]]; then
  FLAG3_ACTIVE=true
  echo "✅ Challenge 3 (Port $PORT_3) is active"
else
  echo "ℹ️ Challenge 3 (Port $PORT_3) is not active in this difficulty level"
  # Mark as found so we don't check for it
  FLAG3_FOUND=true
fi

# Function to print status
print_status() {
  echo -e "${BLUE}=== CTF Challenge Status ===${NC}"

  if ! $FLAG1_ACTIVE; then
    echo -e "Challenge 1: ${GRAY}NOT ACTIVE${NC}"
  elif $FLAG1_FOUND; then
    echo -e "Challenge 1: ${GREEN}COMPLETED ✅${NC}"
  else
    echo -e "Challenge 1: ${RED}PENDING ❌${NC}"
  fi

  if ! $FLAG2_ACTIVE; then
    echo -e "Challenge 2: ${GRAY}NOT ACTIVE${NC}"
  elif $FLAG2_FOUND; then
    echo -e "Challenge 2: ${GREEN}COMPLETED ✅${NC}"
  else
    echo -e "Challenge 2: ${RED}PENDING ❌${NC}"
  fi

  if ! $FLAG3_ACTIVE; then
    echo -e "Challenge 3: ${GRAY}NOT ACTIVE${NC}"
  elif $FLAG3_FOUND; then
    echo -e "Challenge 3: ${GREEN}COMPLETED ✅${NC}"
  else
    echo -e "Challenge 3: ${RED}PENDING ❌${NC}"
  fi

  echo -e "${BLUE}=========================${NC}"
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

# Function to check if the service is ready
check_service() {
  local port=$1
  local expected_flag=$2
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

# Update status for overseer
update_status() {
  local all_complete=$1

  # Create status JSON with current state
  cat > "$POLLER_STATUS_FILE" << EOF
{
  "last_updated": "$(date -Iseconds)",
  "flag1_active": $FLAG1_ACTIVE,
  "flag1_found": $FLAG1_FOUND,
  "flag2_active": $FLAG2_ACTIVE,
  "flag2_found": $FLAG2_FOUND,
  "flag3_active": $FLAG3_ACTIVE,
  "flag3_found": $FLAG3_FOUND,
  "all_complete": $all_complete
}
EOF
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

  # Check active challenges
  if $FLAG1_ACTIVE && ! $FLAG1_FOUND; then
    if check_service "$PORT_1" "$EXPECTED_FLAG_1"; then
      echo -e "${GREEN}FLAG 1 FOUND! 🎉${NC}"
      FLAG1_FOUND=true
      print_status
    fi
  fi

  if $FLAG2_ACTIVE && ! $FLAG2_FOUND; then
    if check_service "$PORT_2" "$EXPECTED_FLAG_2"; then
      echo -e "${GREEN}FLAG 2 FOUND! 🎉${NC}"
      FLAG2_FOUND=true
      print_status
    fi
  fi

  if $FLAG3_ACTIVE && ! $FLAG3_FOUND; then
    if check_service "$PORT_3" "$EXPECTED_FLAG_3"; then
      echo -e "${GREEN}FLAG 3 FOUND! 🎉${NC}"
      FLAG3_FOUND=true
      print_status
    fi
  fi

  # Check if all active challenges are complete
  ALL_COMPLETE=true
  if $FLAG1_ACTIVE && ! $FLAG1_FOUND; then ALL_COMPLETE=false; fi
  if $FLAG2_ACTIVE && ! $FLAG2_FOUND; then ALL_COMPLETE=false; fi
  if $FLAG3_ACTIVE && ! $FLAG3_FOUND; then ALL_COMPLETE=false; fi

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
