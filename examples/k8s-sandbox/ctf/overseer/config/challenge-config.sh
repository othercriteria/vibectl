#!/usr/bin/env bash
# challenge-config.sh - Central configuration for CTF challenges
# This file defines the challenge parameters used by all components

# Status directory for sharing data between containers
STATUS_DIR=${STATUS_DIR:-"/tmp/status"}

# Challenge difficulty and port configuration
CHALLENGE_DIFFICULTY=${CHALLENGE_DIFFICULTY:-easy}
NODE_PORT_1=${NODE_PORT_1:-30001}
NODE_PORT_2=${NODE_PORT_2:-30002}
NODE_PORT_3=${NODE_PORT_3:-30003}

# Expected flags
EXPECTED_FLAG_1="CTF-FLAG-1: K8S_MASTER"
EXPECTED_FLAG_2="CTF-FLAG-2: VIBECTL_PRO"
EXPECTED_FLAG_3="CTF-FLAG-3: CHALLENGE_COMPLETE"

# Create a configuration JSON file that can be used by all components
CONFIG_JSON="${STATUS_DIR}/challenge_config.json"
mkdir -p "${STATUS_DIR}"

# Create the base configuration as a JSON object
cat > "${CONFIG_JSON}" << EOF
{
  "challenge_difficulty": "${CHALLENGE_DIFFICULTY}",
  "ports": {
    "${NODE_PORT_1}": {
      "expected_flag": "${EXPECTED_FLAG_1}"
    },
    "${NODE_PORT_2}": {
      "expected_flag": "${EXPECTED_FLAG_2}"
    },
    "${NODE_PORT_3}": {
      "expected_flag": "${EXPECTED_FLAG_3}"
    }
  },
  "verification_count": 2,
  "runtime_minutes": 20,
  "poll_interval_seconds": 10,
  "active_ports": []
}
EOF

# Generate the active_ports array based on difficulty
if [[ "${CHALLENGE_DIFFICULTY}" == "easy" ]]; then
  # Fix: Properly format NODE_PORT_1 as a numerical array element
  jq ".active_ports = [${NODE_PORT_1}]" "${CONFIG_JSON}" > "${CONFIG_JSON}.tmp" && mv "${CONFIG_JSON}.tmp" "${CONFIG_JSON}"

  # Add challenge text
  jq --arg text "Your goal is to complete this task:

  1. Create a service that returns \"${EXPECTED_FLAG_1}\" text when accessed
  on port ${NODE_PORT_1}. You can use any approach you think is best (pod, deployment, etc.)." \
  '.challenge_text = $text' "${CONFIG_JSON}" > "${CONFIG_JSON}.tmp" && mv "${CONFIG_JSON}.tmp" "${CONFIG_JSON}"

elif [[ "${CHALLENGE_DIFFICULTY}" == "medium" ]]; then
  # Fix: Properly format as an array of numbers
  jq ".active_ports = [${NODE_PORT_1}, ${NODE_PORT_2}]" "${CONFIG_JSON}" > "${CONFIG_JSON}.tmp" && mv "${CONFIG_JSON}.tmp" "${CONFIG_JSON}"

  # Add challenge text
  jq --arg text "Your goal is to complete these tasks:

  1. Create a service that returns \"${EXPECTED_FLAG_1}\" text when accessed
  on port ${NODE_PORT_1}. You can use any approach you think is best (pod, deployment, etc.).

  2. Create a service that returns \"${EXPECTED_FLAG_2}\" text when accessed
  on port ${NODE_PORT_2}. Make sure this service is resilient and can handle load
  (hint: multiple replicas)." \
  '.challenge_text = $text' "${CONFIG_JSON}" > "${CONFIG_JSON}.tmp" && mv "${CONFIG_JSON}.tmp" "${CONFIG_JSON}"

else
  # Default to hard
  # Fix: Properly format as an array of numbers
  jq ".active_ports = [${NODE_PORT_1}, ${NODE_PORT_2}, ${NODE_PORT_3}]" "${CONFIG_JSON}" > "${CONFIG_JSON}.tmp" && mv "${CONFIG_JSON}.tmp" "${CONFIG_JSON}"

  # Add challenge text
  jq --arg text "Your goal is to complete these tasks:

  1. Create a service that returns \"${EXPECTED_FLAG_1}\" text when accessed
  on port ${NODE_PORT_1}. You can use any approach you think is best (pod, deployment, etc.).

  2. Create a service that returns \"${EXPECTED_FLAG_2}\" text when accessed
  on port ${NODE_PORT_2}. Make sure this service is resilient and can handle load
  (hint: multiple replicas).

  3. Create a service that returns \"${EXPECTED_FLAG_3}\" text when accessed
  on port ${NODE_PORT_3}. For this service, use a ConfigMap to store the flag text." \
  '.challenge_text = $text' "${CONFIG_JSON}" > "${CONFIG_JSON}.tmp" && mv "${CONFIG_JSON}.tmp" "${CONFIG_JSON}"
fi

# Correctly escape the challenge text for shell inclusion
CHALLENGE_TEXT_ESCAPED=$(jq -r '.challenge_text' "${CONFIG_JSON}" | sed 's/"/\\"/g')

# For backward compatibility, generate a shell script with the needed variables
cat > "${STATUS_DIR}/challenge_config.sh" << EOF
#!/usr/bin/env bash
# Generated challenge configuration $(date -Iseconds)
# This file is generated for backward compatibility

# Load from JSON
CHALLENGE_DIFFICULTY="$(jq -r '.challenge_difficulty' "${CONFIG_JSON}")"
ACTIVE_PORTS="$(jq -r '.active_ports | join(",")' "${CONFIG_JSON}")"
NODE_PORT_1=${NODE_PORT_1}
NODE_PORT_2=${NODE_PORT_2}
NODE_PORT_3=${NODE_PORT_3}
EXPECTED_FLAG_1="${EXPECTED_FLAG_1}"
EXPECTED_FLAG_2="${EXPECTED_FLAG_2}"
EXPECTED_FLAG_3="${EXPECTED_FLAG_3}"
VERIFICATION_COUNT=$(jq -r '.verification_count' "${CONFIG_JSON}")
RUNTIME_MINUTES=$(jq -r '.runtime_minutes' "${CONFIG_JSON}")
POLL_INTERVAL_SECONDS=$(jq -r '.poll_interval_seconds' "${CONFIG_JSON}")

# Challenge text (properly escaped for shell)
CHALLENGE_TEXT="${CHALLENGE_TEXT_ESCAPED}"
EOF

chmod +x "${STATUS_DIR}/challenge_config.sh"
echo "Configuration generated with mode: ${CHALLENGE_DIFFICULTY}"
echo "Configuration written to ${CONFIG_JSON}"
