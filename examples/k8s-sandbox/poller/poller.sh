#!/usr/bin/env bash
set -e

# TODO: Rewrite poller in Python
# This bash script has grown complex and would benefit from being rewritten in Python:
# - Better error handling
# - Cleaner code organization with classes
# - Better container/k8s API interaction
# - Simpler implementation of the detection logic
# - More robust handling of container inspection

echo "🔍 Starting CTF Challenge Poller Service"
echo "👀 Watching for challenge completion in the sandbox container"

# Ensure Docker socket has proper permissions
if [ ! -w "/var/run/docker.sock" ]; then
  echo "⚠️ Docker socket not writable, applying fix..."
  chmod 666 /var/run/docker.sock || true
fi

# Initialize flags - they'll be set to false or disabled based on active ports
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

# Set color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color

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

  # Try to get just the container ID using various patterns
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
  if echo "$response" | grep -q "$expected_flag"; then
    echo -e "${GREEN}Found flag via Kind container!${NC}"
    return 0
  else
    echo -e "${YELLOW}Kind container port $port returned incorrect content:${NC}"
    echo -e "${GRAY}$response${NC}"
    return 1
  fi
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

# Main polling loop
while true; do
  # Only display status every 2 checks to reduce noise (except the first check)
  if [ $CHECK_COUNT -eq 0 ] || [ $((CHECK_COUNT % 2)) -eq 0 ]; then
    print_status
  fi
  CHECK_COUNT=$((CHECK_COUNT + 1))

  # Check only active challenges
  if $FLAG1_ACTIVE && ! $FLAG1_FOUND; then
    if check_service "$PORT_1" "$EXPECTED_FLAG_1"; then
      echo -e "${GREEN}FLAG 1 FOUND! 🎉${NC}"
      FLAG1_FOUND=true
      print_status  # Always print status when finding a flag
    fi
  fi

  if $FLAG2_ACTIVE && ! $FLAG2_FOUND; then
    if check_service "$PORT_2" "$EXPECTED_FLAG_2"; then
      echo -e "${GREEN}FLAG 2 FOUND! 🎉${NC}"
      FLAG2_FOUND=true
      print_status  # Always print status when finding a flag
    fi
  fi

  if $FLAG3_ACTIVE && ! $FLAG3_FOUND; then
    if check_service "$PORT_3" "$EXPECTED_FLAG_3"; then
      echo -e "${GREEN}FLAG 3 FOUND! 🎉${NC}"
      FLAG3_FOUND=true
      print_status  # Always print status when finding a flag
    fi
  fi

  # Check if all active challenges are complete
  COMPLETED=true
  if $FLAG1_ACTIVE && ! $FLAG1_FOUND; then COMPLETED=false; fi
  if $FLAG2_ACTIVE && ! $FLAG2_FOUND; then COMPLETED=false; fi
  if $FLAG3_ACTIVE && ! $FLAG3_FOUND; then COMPLETED=false; fi

  if $COMPLETED; then
    echo -e "${GREEN}🏆 ALL ACTIVE CTF CHALLENGES COMPLETED! 🏆${NC}"
    echo -e "${GREEN}Congratulations! The vibectl autonomous mode has successfully completed all tasks!${NC}"
    exit 0
  fi

  # Wait before next check
  sleep 15
done
