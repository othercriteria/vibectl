#!/usr/bin/env bash
set -e

echo "🔍 Starting Chaos Monkey Service Poller"
echo "👀 Monitoring Kubernetes cluster health"

# Set color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color

# Configuration
POLL_INTERVAL_SECONDS=${POLL_INTERVAL_SECONDS:-15}
DELAY_SECONDS=${DELAY_SECONDS:-15}

# Set up kubeconfig
export KUBECONFIG=/config/kube/config

# Verify kubeconfig exists
if [ ! -f "$KUBECONFIG" ]; then
  echo -e "${RED}ERROR: Kubeconfig not found at $KUBECONFIG${NC}"
  echo -e "${YELLOW}Waiting for kubeconfig to become available...${NC}"

  # Wait for kubeconfig to appear before failing
  for i in {1..30}; do
    if [ -f "$KUBECONFIG" ]; then
      echo -e "${GREEN}Kubeconfig found after waiting!${NC}"
      break
    fi
    echo -n "."
    sleep 5
    if [ $i -eq 30 ]; then
      echo -e "${RED}ERROR: Kubeconfig still not available after waiting. Exiting.${NC}"
      exit 1
    fi
  done
fi

echo -e "${GREEN}Using kubeconfig at $KUBECONFIG${NC}"

# Function to print status
print_status() {
  echo -e "${BLUE}=== Chaos Monkey Cluster Status ===${NC}"

  if kubectl get nodes &>/dev/null; then
    echo -e "Kubernetes Cluster: ${GREEN}AVAILABLE ✅${NC}"
  else
    echo -e "Kubernetes Cluster: ${RED}UNAVAILABLE ❌${NC}"
  fi

  # Get pod status
  echo -e "\n${BLUE}Pod Status:${NC}"
  kubectl get pods -A | grep -v "kube-system" || echo -e "${YELLOW}No pods found outside kube-system namespace${NC}"

  echo -e "${BLUE}===================================${NC}"
}

# Main polling loop - check cluster health and report status
echo -e "${YELLOW}Waiting for initial delay of ${DELAY_SECONDS} seconds...${NC}"
sleep $DELAY_SECONDS

echo -e "${GREEN}Starting to monitor cluster health...${NC}"

# Initialize check counter
CHECK_COUNT=0

while true; do
  # Only display full status every 3 checks to reduce noise
  if [ $CHECK_COUNT -eq 0 ] || [ $((CHECK_COUNT % 3)) -eq 0 ]; then
    print_status
  else
    # Simple check on off-cycles
    if kubectl get nodes &>/dev/null; then
      echo -e "${GREEN}Kubernetes cluster is healthy${NC}"
    else
      echo -e "${RED}Kubernetes cluster appears to be down!${NC}"
      print_status
    fi
  fi

  CHECK_COUNT=$((CHECK_COUNT + 1))

  # Wait before next check
  sleep $POLL_INTERVAL_SECONDS
done
