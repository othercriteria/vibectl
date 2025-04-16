#!/bin/bash
set -eo pipefail

echo "🔍 Starting CTF Challenge Overseer"
echo "👑 Coordinating the sandbox environment and monitoring challenge status"

# Locations
CONFIG_SCRIPT="/usr/local/bin/config/challenge-config.sh"
STATUS_DIR=${STATUS_DIR:-"/tmp/status"}
CONFIG_JSON="${STATUS_DIR}/challenge_config.json"
POLLER_STATUS_FILE="${STATUS_DIR}/poller_status.json"

# Run the configuration script to generate the JSON config
echo "Generating challenge configuration"
mkdir -p "${STATUS_DIR}"
source "${CONFIG_SCRIPT}"

# Load parameters from the generated JSON config
RUNTIME_MINUTES=$(jq -r '.runtime_minutes' "${CONFIG_JSON}")
VERIFICATION_COUNT=$(jq -r '.verification_count' "${CONFIG_JSON}")
CHALLENGE_DIFFICULTY=$(jq -r '.challenge_difficulty' "${CONFIG_JSON}")
ACTIVE_PORTS=$(jq -r '.active_ports[]' "${CONFIG_JSON}" | tr '\n' ',' | sed 's/,$//')

echo "Overseer initialized with:"
echo "  - Runtime: ${RUNTIME_MINUTES} minutes"
echo "  - Verification count: ${VERIFICATION_COUNT}"
echo "  - Difficulty: ${CHALLENGE_DIFFICULTY}"
echo "  - Active ports: ${ACTIVE_PORTS}"

# Calculate end time
END_TIME=$(date -d "+${RUNTIME_MINUTES} minutes" +%s)

# Record start time
START_TIME=$(date +%s)
echo "Challenge started at $(date)"

# Report progress
while true; do
  CURRENT_TIME=$(date +%s)

  # Check if the poller has detected successful service verification
  if [[ -f "${POLLER_STATUS_FILE}" ]]; then
    # Extract verification information from poller status
    ALL_COMPLETE=$(jq -r '.all_complete' "${POLLER_STATUS_FILE}")

    # Display verification status for each active port
    echo "Verification progress:"
    for PORT in $(jq -r '.active_ports[]' "${CONFIG_JSON}"); do
      PORT_SUCCESS=$(jq -r ".port_${PORT}_success_count // 0" "${POLLER_STATUS_FILE}")
      echo "  Port ${PORT}: ${PORT_SUCCESS}/${VERIFICATION_COUNT}"
    done

    if [[ "${ALL_COMPLETE}" == "true" ]]; then
      echo "All services have been verified!"
      SERVICES_VERIFIED=true
    else
      echo "Waiting for service verification..."
      SERVICES_VERIFIED=false
    fi
  else
    echo "Waiting for poller to start..."
    SERVICES_VERIFIED=false
  fi

  # Calculate remaining time
  REMAINING_SECONDS=$((END_TIME - CURRENT_TIME))
  REMAINING_MINUTES=$((REMAINING_SECONDS / 60))

  # Check if we've reached the end time or if all services are verified and we've run for the minimum time
  if [[ $CURRENT_TIME -ge $END_TIME ]]; then
    echo "Maximum runtime reached. Shutting down..."
    exit 0
  elif [[ "${SERVICES_VERIFIED}" == "true" ]]; then
    # Calculate minimum runtime in seconds (25% of total runtime)
    MIN_RUNTIME_SECONDS=$((START_TIME + (RUNTIME_MINUTES * 60 / 4)))

    if [[ $CURRENT_TIME -ge $MIN_RUNTIME_SECONDS ]]; then
      echo "All services verified and minimum runtime reached. Shutting down..."
      exit 0
    else
      MINS_TO_MIN_RUNTIME=$(( (MIN_RUNTIME_SECONDS - CURRENT_TIME) / 60 ))
      echo "All services verified! Continuing for at least ${MINS_TO_MIN_RUNTIME} more minutes to meet minimum runtime."
    fi
  fi

  echo "Time remaining: ${REMAINING_MINUTES} minutes"
  sleep 30
done
