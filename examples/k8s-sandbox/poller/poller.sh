#!/usr/bin/env bash
set -e

echo "🔍 Starting CTF Challenge Poller Service"
echo "👀 Watching for challenge completion on $TARGET_HOST"

# TODO: Future Improvements
# - Extend poller to check for more detailed aspects of the solution:
#   - Verify replicas count for challenge 2
#   - Verify ConfigMap implementation for challenge 3
#   - Add more advanced metrics (response time, etc.)
#   - Support websocket for real-time status updates

# Initialize flags
FLAG1_FOUND=false
FLAG2_FOUND=false
FLAG3_FOUND=false

# Set color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print status
print_status() {
  echo -e "${BLUE}=== CTF Challenge Status ===${NC}"

  if $FLAG1_FOUND; then
    echo -e "Challenge 1: ${GREEN}COMPLETED ✅${NC}"
  else
    echo -e "Challenge 1: ${RED}PENDING ❌${NC}"
  fi

  if $FLAG2_FOUND; then
    echo -e "Challenge 2: ${GREEN}COMPLETED ✅${NC}"
  else
    echo -e "Challenge 2: ${RED}PENDING ❌${NC}"
  fi

  if $FLAG3_FOUND; then
    echo -e "Challenge 3: ${GREEN}COMPLETED ✅${NC}"
  else
    echo -e "Challenge 3: ${RED}PENDING ❌${NC}"
  fi

  echo -e "${BLUE}=========================${NC}"
}

# Wait for the sandbox to be ready
echo -e "${YELLOW}Waiting for sandbox Kubernetes cluster to be ready...${NC}"
until curl -s --connect-timeout 2 "http://$TARGET_HOST:$PORT_1" -o /dev/null -w '' 2>/dev/null || \
      curl -s --connect-timeout 2 "http://$TARGET_HOST:$PORT_2" -o /dev/null -w '' 2>/dev/null || \
      curl -s --connect-timeout 2 "http://$TARGET_HOST:$PORT_3" -o /dev/null -w '' 2>/dev/null
do
  echo -e "${YELLOW}Sandbox services not ready yet, waiting...${NC}"
  sleep 5
done

echo -e "${GREEN}Sandbox Kubernetes cluster is up! Starting to poll...${NC}"

# Main polling loop
while true; do
  print_status

  # Check challenges safely with generous timeout
  if ! $FLAG1_FOUND; then
    RESPONSE=$(curl -s --connect-timeout 5 --max-time 10 "http://$TARGET_HOST:$PORT_1" || echo "")
    if echo "$RESPONSE" | grep -q "$EXPECTED_FLAG_1"; then
      echo -e "${GREEN}FLAG 1 FOUND! 🎉${NC}"
      FLAG1_FOUND=true
    fi
  fi

  if ! $FLAG2_FOUND; then
    RESPONSE=$(curl -s --connect-timeout 5 --max-time 10 "http://$TARGET_HOST:$PORT_2" || echo "")
    if echo "$RESPONSE" | grep -q "$EXPECTED_FLAG_2"; then
      echo -e "${GREEN}FLAG 2 FOUND! 🎉${NC}"
      FLAG2_FOUND=true
    fi
  fi

  if ! $FLAG3_FOUND; then
    RESPONSE=$(curl -s --connect-timeout 5 --max-time 10 "http://$TARGET_HOST:$PORT_3" || echo "")
    if echo "$RESPONSE" | grep -q "$EXPECTED_FLAG_3"; then
      echo -e "${GREEN}FLAG 3 FOUND! 🎉${NC}"
      FLAG3_FOUND=true
    fi
  fi

  # Check if all challenges are complete
  if $FLAG1_FOUND && $FLAG2_FOUND && $FLAG3_FOUND; then
    echo -e "${GREEN}🏆 ALL CTF CHALLENGES COMPLETED! 🏆${NC}"
    echo -e "${GREEN}Congratulations! The vibectl autonomous mode has successfully completed all tasks!${NC}"
    exit 0
  fi

  # Wait before next check
  sleep 15
done
