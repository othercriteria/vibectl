#!/usr/bin/env bash
set -e

echo "🔍 Starting Chaos Monkey Service Poller"
echo "👀 Monitoring service availability in the Kind cluster"

# Set color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color

# Configuration
POLL_INTERVAL_SECONDS=${POLL_INTERVAL_SECONDS:-15}
NODE_PORT_1=30001
NODE_PORT_2=30002
NODE_PORT_3=30003
VERIFICATION_COUNT=2

# Initialize tracking variables
declare -A SERVICE_ACTIVE
declare -A SERVICE_FOUND
declare -A SERVICE_SUCCESS_COUNT

# Initialize all services as active but not found
for port in $NODE_PORT_1 $NODE_PORT_2 $NODE_PORT_3; do
  SERVICE_ACTIVE[$port]=true
  SERVICE_FOUND[$port]=false
  SERVICE_SUCCESS_COUNT[$port]=0
done

# Function to print status
print_status() {
  echo -e "${BLUE}=== Chaos Monkey Service Status ===${NC}"

  for port in $NODE_PORT_1 $NODE_PORT_2 $NODE_PORT_3; do
    if [[ "${SERVICE_FOUND[$port]}" == "true" ]]; then
      echo -e "Port $port: ${GREEN}AVAILABLE ✅ (${SERVICE_SUCCESS_COUNT[$port]}/${VERIFICATION_COUNT})${NC}"
    else
      echo -e "Port $port: ${RED}UNAVAILABLE ❌ (${SERVICE_SUCCESS_COUNT[$port]}/${VERIFICATION_COUNT})${NC}"
    fi
  done

  echo -e "${BLUE}===================================${NC}"
}

# Find the sandbox container ID
find_sandbox_container() {
  # Try direct name match first
  if docker ps --format '{{.Names}}' | grep -q "^chaos-monkey-k8s-sandbox$"; then
    echo "chaos-monkey-k8s-sandbox"
    return 0
  fi

  # Fallback to pattern matching if the explicit name isn't found
  local container_id
  container_id=$(docker ps | grep -E "chaos-monkey-k8s-sandbox" | grep -v "poller" | awk '{print $1}' | head -1)

  if [ -z "$container_id" ]; then
    # Try with container names
    container_id=$(docker ps --format '{{.Names}}' | grep -E "chaos-monkey-k8s-sandbox" | grep -v "poller" | head -1)

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
  local container_id

  container_id=$(find_sandbox_container) || return 1

  # Check if docker exec command works
  if ! docker exec "$container_id" echo "Connection test" >/dev/null 2>&1; then
    echo -e "${RED}Cannot connect to sandbox container.${NC}"
    return 1
  fi

  # Get the Kind container ID (direct access to nodes)
  local kind_container="chaos-monkey-control-plane"
  local kind_container_ip

  # Get the IP address of the Kind container (where K8s is actually running)
  kind_container_ip=$(docker exec "$container_id" bash -c "docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' $kind_container 2>/dev/null" 2>/dev/null || echo "")

  if [ -z "$kind_container_ip" ]; then
    echo -e "${YELLOW}Could not determine Kind container IP${NC}"
    return 1
  fi

  # Direct access to the Kind container
  echo -e "${BLUE}Checking service at Kind container ${kind_container} (${kind_container_ip}:$port)${NC}"
  if ! docker exec "$container_id" bash -c "nc -z $kind_container_ip $port 2>/dev/null"; then
    echo -e "${YELLOW}Port $port is not listening on Kind container${NC}"
    return 1
  fi

  echo -e "${YELLOW}Port $port is accessible on Kind container, trying to get content...${NC}"
  local response
  response=$(docker exec "$container_id" bash -c "curl -s --connect-timeout 5 --max-time 10 http://${kind_container_ip}:$port")

  if [ -z "$response" ]; then
    echo -e "${YELLOW}Empty response from port $port${NC}"
    return 1
  fi

  # Verify we can consistently get a response
  echo -e "${YELLOW}Received response, verifying with second request...${NC}"
  local second_response
  second_response=$(docker exec "$container_id" bash -c "curl -s --connect-timeout 5 --max-time 10 http://${kind_container_ip}:$port")

  if [ -n "$second_response" ]; then
    echo -e "${GREEN}Service on port $port is accessible and returns content!${NC}"
    # Display truncated response for information
    echo -e "${GRAY}Response: ${second_response:0:100}...${NC}"
    return 0
  else
    echo -e "${YELLOW}Could not verify with second request. First response might have been transient.${NC}"
    return 1
  fi
}

# Wait for the sandbox to be ready
echo -e "${YELLOW}Waiting for sandbox Kubernetes cluster to be ready...${NC}"

# Wait for sandbox container to be ready
while ! docker ps | grep -E "chaos-monkey-k8s-sandbox" | grep -v "poller" > /dev/null; do
  echo -e "${YELLOW}Waiting for sandbox container to start...${NC}"
  sleep 5
done

echo -e "${GREEN}Sandbox container is running! Starting to check for services...${NC}"

# Initialize check counter
CHECK_COUNT=0

# Main polling loop - check services and report status
while true; do
  # Only display status every 3 checks to reduce noise
  if [ $CHECK_COUNT -eq 0 ] || [ $((CHECK_COUNT % 3)) -eq 0 ]; then
    print_status
  fi
  CHECK_COUNT=$((CHECK_COUNT + 1))

  # Check all ports
  for port in $NODE_PORT_1 $NODE_PORT_2 $NODE_PORT_3; do
    if [[ "${SERVICE_FOUND[$port]}" != "true" ]]; then
      if check_service "$port"; then
        # Increment success count for this port
        SERVICE_SUCCESS_COUNT[$port]=$((SERVICE_SUCCESS_COUNT[$port] + 1))
        echo -e "${GREEN}Port $port check ${SERVICE_SUCCESS_COUNT[$port]}/${VERIFICATION_COUNT} successful${NC}"

        # Check if we've reached the verification threshold
        if [ "${SERVICE_SUCCESS_COUNT[$port]}" -ge "$VERIFICATION_COUNT" ]; then
          echo -e "${GREEN}Service on port $port VERIFIED AVAILABLE! (${SERVICE_SUCCESS_COUNT[$port]}/${VERIFICATION_COUNT}) 🎉${NC}"
          SERVICE_FOUND[$port]=true
          print_status
        fi
      else
        # Reset counter on failure
        if [ -n "${SERVICE_SUCCESS_COUNT[$port]}" ] && [ "${SERVICE_SUCCESS_COUNT[$port]}" -gt 0 ]; then
          echo -e "${YELLOW}Reset port $port check count after failure${NC}"
          SERVICE_SUCCESS_COUNT[$port]=0
        fi
      fi
    else
      # Periodically check ports that are already found to ensure they're still available
      if [ $((CHECK_COUNT % 10)) -eq 0 ]; then
        echo -e "${BLUE}Verifying continued availability of port $port...${NC}"
        if ! check_service "$port"; then
          echo -e "${RED}WARNING: Previously available service on port $port is no longer available!${NC}"
          SERVICE_FOUND[$port]=false
          SERVICE_SUCCESS_COUNT[$port]=0
          print_status
        fi
      fi
    fi
  done

  # Check if all services are found
  ALL_FOUND=true
  for port in $NODE_PORT_1 $NODE_PORT_2 $NODE_PORT_3; do
    if [[ "${SERVICE_FOUND[$port]}" != "true" ]]; then
      ALL_FOUND=false
      break
    fi
  done

  if [ "$ALL_FOUND" = true ]; then
    echo -e "${GREEN}🎉 All services are available and verified!${NC}"
  fi

  # Wait before next check
  sleep $POLL_INTERVAL_SECONDS
done
