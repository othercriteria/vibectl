#!/usr/bin/env bash
set -e

echo "🔍 Starting CTF Challenge Poller Service"
echo "👀 Watching for challenge completion on $TARGET_HOST"

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

# Wait for the sandbox to be ready
echo -e "${YELLOW}Waiting for sandbox Kubernetes cluster to be ready...${NC}"

# Wait for the sandbox container to be ready based on the healthcheck
# This is different than waiting for the services to be up
SANDBOX_READY=false
while ! $SANDBOX_READY; do
  echo -e "${YELLOW}Checking if sandbox container is ready...${NC}"

  # Try to ping the target host to check if it's up
  if ping -c 1 "$TARGET_HOST" >/dev/null 2>&1; then
    echo -e "${GREEN}Sandbox container is reachable!${NC}"
    SANDBOX_READY=true
  else
    echo -e "${YELLOW}Sandbox container not ready yet, waiting...${NC}"
    sleep 5
  fi
done

echo -e "${GREEN}Sandbox is up! Starting to poll for services...${NC}"

# Main polling loop
while true; do
  print_status

  # Check only active challenges with generous timeout
  if $FLAG1_ACTIVE && ! $FLAG1_FOUND; then
    RESPONSE=$(curl -s --connect-timeout 5 --max-time 10 "http://$TARGET_HOST:$PORT_1" || echo "")
    if echo "$RESPONSE" | grep -q "$EXPECTED_FLAG_1"; then
      echo -e "${GREEN}FLAG 1 FOUND! 🎉${NC}"
      FLAG1_FOUND=true
    fi
  fi

  if $FLAG2_ACTIVE && ! $FLAG2_FOUND; then
    RESPONSE=$(curl -s --connect-timeout 5 --max-time 10 "http://$TARGET_HOST:$PORT_2" || echo "")
    if echo "$RESPONSE" | grep -q "$EXPECTED_FLAG_2"; then
      echo -e "${GREEN}FLAG 2 FOUND! 🎉${NC}"
      FLAG2_FOUND=true
    fi
  fi

  if $FLAG3_ACTIVE && ! $FLAG3_FOUND; then
    RESPONSE=$(curl -s --connect-timeout 5 --max-time 10 "http://$TARGET_HOST:$PORT_3" || echo "")
    if echo "$RESPONSE" | grep -q "$EXPECTED_FLAG_3"; then
      echo -e "${GREEN}FLAG 3 FOUND! 🎉${NC}"
      FLAG3_FOUND=true
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
