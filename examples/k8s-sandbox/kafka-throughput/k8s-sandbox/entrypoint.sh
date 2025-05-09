#!/bin/bash
set -euo pipefail

echo "Testing Docker socket connection..."
if ! docker ps > /dev/null 2>&1; then
  echo "Error: Cannot access Docker socket. Check that the volume mount and group permissions are correct." >&2
  exit 1
fi
echo "Docker socket connection successful."

echo "🚀 Starting Kafka Demo Sandbox Entrypoint..."

# Environment variables from compose.yml
# K3D_CLUSTER_NAME, STATUS_DIR, VIBECTL_MODEL, etc.

# --- Configuration ---
export KUBECONFIG="/home/sandbox/.kube/config"
export KAFKA_MANIFEST="/home/sandbox/manifests/kafka-kraft.yaml"
export KAFKA_NAMESPACE="kafka"
export KAFKA_SERVICE="kafka-service"
export KAFKA_PORT=9092
export KAFKA_STATEFULSET="kafka-controller"
export KAFKA_REPLICAS=1 # Assuming 1 replica for KRaft initially
export KAFKA_CLUSTER_ID_CM="kafka-cluster-id" # Define the ConfigMap name
export TARGET_LATENCY_MS="10.0" # Assuming a default value

# Status files
mkdir -p "${STATUS_DIR}"
PHASE1_COMPLETE="${STATUS_DIR}/phase1_k8s_kafka_setup_complete"
PHASE2_COMPLETE="${STATUS_DIR}/phase2_vibectl_setup_complete"
KAFKA_READY_FILE="${STATUS_DIR}/kafka_ready"
LATENCY_FILE="${STATUS_DIR}/latency.txt"
SHUTDOWN_FILE="${STATUS_DIR}/shutdown"

# --- Cleanup Function and Trap ---
function cleanup_k3d_cluster_on_exit() {
    echo "🚪 EXIT TRAP: Cleaning up k3d cluster '${K3D_CLUSTER_NAME:-unknown_cluster}'..."
    if [ -n "${K3D_CLUSTER_NAME:-}" ]; then
        if command -v k3d &> /dev/null; then
            echo "Attempting to delete k3d cluster '${K3D_CLUSTER_NAME}'..."
            # Give k3d a timeout to avoid hanging the exit trap indefinitely
            # Using a subshell with timeout for the k3d command
            ( timeout 30s k3d cluster delete "${K3D_CLUSTER_NAME}" ) || \
                echo "⚠️ Warning: 'k3d cluster delete ${K3D_CLUSTER_NAME}' failed, timed out, or cluster was already gone. Continuing shutdown." >&2
            
            # Additional forceful cleanup of related Docker resources if k3d failed or missed something
            # This is a best-effort and might be redundant if k3d delete is successful.
            echo "Performing best-effort Docker resource cleanup for '${K3D_CLUSTER_NAME}'..."
            K3D_CONTAINER_PATTERN="k3d-${K3D_CLUSTER_NAME}-"
            if docker ps -a --filter "name=${K3D_CONTAINER_PATTERN}" -q | grep -q .; then
                docker ps -a --filter "name=${K3D_CONTAINER_PATTERN}" -q | xargs --no-run-if-empty docker stop -t 5 || echo "⚠️ Warning: Failed to stop one or more k3d containers for ${K3D_CLUSTER_NAME}." >&2
                docker ps -a --filter "name=${K3D_CONTAINER_PATTERN}" -q | xargs --no-run-if-empty docker rm -f || echo "⚠️ Warning: Failed to remove one or more k3d containers for ${K3D_CLUSTER_NAME}." >&2
            fi
            # Attempt to remove the network if it exists and is empty
            if docker network inspect "k3d-${K3D_CLUSTER_NAME}" >/dev/null 2>&1; then
                # Check if network has active endpoints (should be none if containers are gone)
                if ! docker network inspect "k3d-${K3D_CLUSTER_NAME}" | jq -e '.[0].Containers | length == 0'; then
                     echo "⚠️ Warning: Network 'k3d-${K3D_CLUSTER_NAME}' still has active endpoints. Skipping direct removal." >&2
                else
                    docker network rm "k3d-${K3D_CLUSTER_NAME}" || echo "⚠️ Warning: Failed to remove network 'k3d-${K3D_CLUSTER_NAME}'. It might be in use or already gone." >&2
                fi
            fi
        else
            echo "⚠️ Warning: k3d command not found in EXIT TRAP. Cannot delete cluster." >&2
        fi
    else
        echo "⚠️ Warning: K3D_CLUSTER_NAME not set in EXIT TRAP. Cannot determine which cluster to delete." >&2
    fi
    echo "🚪 EXIT TRAP: Cleanup attempt finished."
}
trap cleanup_k3d_cluster_on_exit EXIT SIGINT SIGTERM

# --- Functions ---

# Reusable function from Bootstrap demo
function setup_k3d_cluster() {
    echo "🔧 Checking for existing K3d cluster '${K3D_CLUSTER_NAME}'..."
    if k3d cluster list | grep -q -w "${K3D_CLUSTER_NAME}"; then
        echo "🗑️ Found existing cluster '${K3D_CLUSTER_NAME}'. Attempting to delete it forcefully..."

        # 1. Try k3d delete
        if ! k3d cluster delete "${K3D_CLUSTER_NAME}"; then
            echo "⚠️ Warning: 'k3d cluster delete' command failed or reported issues. Proceeding with manual cleanup." >&2
        else
            echo "✅ 'k3d cluster delete' command initiated for '${K3D_CLUSTER_NAME}'."
        fi

        # Give things a moment
        echo "⏳ Waiting 2 seconds after k3d delete attempt..."
        sleep 2

        # 2. Manual container stop/remove
        K3D_CONTAINER_PATTERN="k3d-${K3D_CLUSTER_NAME}-"
        echo "🧹 Forcefully stopping/removing any remaining Docker containers matching '${K3D_CONTAINER_PATTERN}'..."
        if docker ps -a --filter "name=${K3D_CONTAINER_PATTERN}" -q | grep -q .; then
            docker ps -a --filter "name=${K3D_CONTAINER_PATTERN}" -q | xargs --no-run-if-empty docker stop -t 2 || echo "⚠️ Warning: Failed to stop one or more containers gracefully. Attempting force remove..." >&2
            sleep 2 # Brief pause after stop attempt
            docker ps -a --filter "name=${K3D_CONTAINER_PATTERN}" -q | xargs --no-run-if-empty docker rm -f || echo "⚠️ Warning: Failed to forcefully remove one or more containers." >&2
        else
            echo "No containers found matching '${K3D_CONTAINER_PATTERN}'."
        fi

        # Step 3 (was 4): Wait and verify cluster is gone from k3d list
        echo "⏳ Verifying cluster removal via 'k3d cluster list' (waiting up to 30 seconds)..."
        ATTEMPTS=0
        MAX_ATTEMPTS=10 # 10 attempts * 2 seconds = 20 seconds
        CLUSTER_GONE=false
        while [ $ATTEMPTS -lt $MAX_ATTEMPTS ]; do
            if ! k3d cluster list | grep -q -w "${K3D_CLUSTER_NAME}"; then
                CLUSTER_GONE=true
                break
            fi
            echo "    Cluster still listed, waiting 2 more seconds... (${ATTEMPTS}/${MAX_ATTEMPTS})"
            sleep 2
            ATTEMPTS=$((ATTEMPTS + 1))
        done

        if [ "$CLUSTER_GONE" = true ]; then
            echo "✅ Cluster '${K3D_CLUSTER_NAME}' successfully removed according to 'k3d cluster list'."
        else
            echo "❌ Error: Cluster '${K3D_CLUSTER_NAME}' still exists according to 'k3d cluster list' after deletion attempts and timeout. Manual intervention required." >&2
            k3d cluster list >&2 # Show what k3d sees
            exit 1
        fi

    fi # End of if cluster existed

    # Step 4 (was 5): Create cluster
    echo "🤔 Creating new cluster '${K3D_CLUSTER_NAME}'..."
    # Note: No --network flag here anymore based on previous findings
    if ! k3d cluster create "${K3D_CLUSTER_NAME}"; then
        echo "❌ Error: Failed to create K3d cluster '${K3D_CLUSTER_NAME}'." >&2
        k3d cluster list >&2
        exit 1
    fi
    echo "✅ K3d cluster '${K3D_CLUSTER_NAME}' created successfully!"
    # Ensure kubectl context is set correctly after create
    k3d kubeconfig merge "${K3D_CLUSTER_NAME}" --kubeconfig-merge-default --kubeconfig-switch-context
    echo "✅ Switched kubectl context to '${K3D_CLUSTER_NAME}'."
}

# Reusable function from Bootstrap demo (adapted path)
function patch_kubeconfig() {
    echo "🔧 Patching kubeconfig..."
    mkdir -p /home/sandbox/.kube
    echo "Using kubeconfig at: ${KUBECONFIG}"
    k3d kubeconfig get "${K3D_CLUSTER_NAME}" > "${KUBECONFIG}.orig" # Save original

    CURRENT_SERVER_URL=$(grep 'server:' "${KUBECONFIG}.orig" | awk '{print $2}')
    echo "Original server URL from k3d: ${CURRENT_SERVER_URL}"

    if [[ -z "$CURRENT_SERVER_URL" ]]; then
        echo "❌ Error: Could not extract server URL from k3d kubeconfig." >&2; cat "${KUBECONFIG}.orig" >&2; exit 1
    fi

    EXTRACTED_PORT=$(echo "$CURRENT_SERVER_URL" | sed -E 's#^https://(0\.0\.0\.0|127\.0\.0\.1):##')
    if [[ -z "$EXTRACTED_PORT" ]] || [[ "$EXTRACTED_PORT" == "$CURRENT_SERVER_URL" ]]; then
        echo "❌ Error: Could not extract port from server URL: ${CURRENT_SERVER_URL}." >&2; exit 1
    fi
    echo "Extracted host port: ${EXTRACTED_PORT}"

    # Attempt to get the gateway IP (host IP on the container's network)
    GATEWAY_IP=$(ip route | awk '/default via/ {print $3}' | head -n 1) # head -n 1 in case of multiple default routes
    if [[ -z "$GATEWAY_IP" ]]; then
        echo "⚠️ Warning: Could not determine gateway IP. Falling back to host.docker.internal." >&2
        # If gateway IP fails, host.docker.internal is already configured by extra_hosts as a fallback.
        # So we can proceed with host.docker.internal which might work in some environments
        # or if the direct gateway IP method has issues.
        NEW_HOST_IP="host.docker.internal"
    else
        echo "Found gateway IP: ${GATEWAY_IP}"
        NEW_HOST_IP="${GATEWAY_IP}"
    fi

    NEW_SERVER_URL="https://${NEW_HOST_IP}:${EXTRACTED_PORT}"
    echo "Attempting to patch kubeconfig to use server: ${NEW_SERVER_URL}"

    awk -v new_url="${NEW_SERVER_URL}" \
        '{ if ($1 == "server:") { print "    server: " new_url } else { print } }' \
        "${KUBECONFIG}.orig" > "${KUBECONFIG}.tmp"
    awk '/server: /{print; print "    insecure-skip-tls-verify: true"; next} !/certificate-authority-data/' \
        "${KUBECONFIG}.tmp" > "${KUBECONFIG}"
    rm "${KUBECONFIG}.tmp" "${KUBECONFIG}.orig"

    chmod 600 "${KUBECONFIG}"
    chown sandbox:sandbox "${KUBECONFIG}"
    echo "✅ Kubeconfig patched to use ${NEW_SERVER_URL}."
    echo "Final Kubeconfig server line:"; grep 'server:' "${KUBECONFIG}" || true

    wait_for_k8s_ready

    # Copy the patched kubeconfig to the shared status volume for other services
    echo "📋 Copying patched kubeconfig to ${STATUS_DIR}/k3d_kubeconfig for other services..."
    if [ -f "${KUBECONFIG}" ]; then
        cp "${KUBECONFIG}" "${STATUS_DIR}/k3d_kubeconfig"
        chmod 644 "${STATUS_DIR}/k3d_kubeconfig" # Ensure it's readable
        echo "✅ Kubeconfig copied."
    else
        echo "❌ Error: Patched kubeconfig ${KUBECONFIG} not found after setup." >&2
        # Decide if this is fatal or just a warning
        # exit 1 # Uncomment if this should be fatal
    fi

    deploy_kafka
    wait_for_kafka_ready
}

# Reusable function from Bootstrap demo
function wait_for_k8s_ready() {
    echo "⏳ Waiting for Kubernetes cluster to be ready (using ${KUBECONFIG})..."
    for i in {1..60}; do # Increased timeout slightly
        # Capture stderr to see potential errors
        KCTL_OUTPUT=$(kubectl --kubeconfig "${KUBECONFIG}" cluster-info 2>&1)
        KCTL_EXIT_CODE=$?

        if [ $KCTL_EXIT_CODE -eq 0 ]; then
            echo "✅ Kubernetes cluster is ready!"
            kubectl --kubeconfig "${KUBECONFIG}" get nodes # Show nodes
            return 0
        fi

        # If failed, print the error output before retrying
        echo "Waiting for Kubernetes API... (${i}/60) Exit code: ${KCTL_EXIT_CODE}"
        echo "kubectl cluster-info output:"
        echo "${KCTL_OUTPUT}" # Print captured output
        echo "---"

        if [ $i -eq 60 ]; then
            echo "❌ Error: Kubernetes cluster did not become ready within the timeout period."
            k3d cluster list # Show k3d's view
            # Try getting nodes again with error output
            echo "Final attempt to get nodes:"
            kubectl --kubeconfig "${KUBECONFIG}" get nodes
            exit 1
        fi
        sleep 2
    done
}

function ensure_kafka_cluster_id_cm() {
    echo "🔧 Ensuring Kafka Cluster ID ConfigMap (${KAFKA_CLUSTER_ID_CM}) exists..."
    if kubectl get configmap "${KAFKA_CLUSTER_ID_CM}" -n "${KAFKA_NAMESPACE}" >/dev/null 2>&1; then
        echo "✅ Cluster ID ConfigMap already exists."
    else
        echo "🤔 Cluster ID ConfigMap not found. Creating it using generated ID..."
        # Get the generated ID from the environment variable passed by run.sh/compose
        if [ -z "${GENERATED_KAFKA_CLUSTER_ID:-}" ]; then
             echo "❌ Error: GENERATED_KAFKA_CLUSTER_ID environment variable is not set." >&2
             echo "   This should have been generated and passed by the run.sh script." >&2
             exit 1
        fi
        echo "🔑 Using pre-generated Kafka Cluster ID: ${GENERATED_KAFKA_CLUSTER_ID}"
        # Create the ConfigMap
        if ! kubectl create configmap "${KAFKA_CLUSTER_ID_CM}" -n "${KAFKA_NAMESPACE}" --from-literal=clusterId="${GENERATED_KAFKA_CLUSTER_ID}"; then
            echo "❌ Error: Failed to create Kafka Cluster ID ConfigMap." >&2
            exit 1
        fi
        echo "✅ Cluster ID ConfigMap created."
    fi
}

function deploy_kafka() {
    echo "🔧 Creating Kafka namespace: ${KAFKA_NAMESPACE}..."
    kubectl create namespace ${KAFKA_NAMESPACE} --dry-run=client -o yaml | kubectl apply -f - || echo "Namespace ${KAFKA_NAMESPACE} likely already exists or failed to create."

    # Get container IP for the advertised listener
    # If KAFKA_ADVERTISED_HOST is not set in environment, get it from container IP
    # Force advertised listener to be the k8s-sandbox hostname, which is reachable
    # on the docker network by the producer/consumer containers.
    # The internal listener within k8s/kafka will still work.
    export KAFKA_ADVERTISED_HOST="k8s-sandbox"
    echo "Setting KAFKA_ADVERTISED_HOST to 'k8s-sandbox' for external reachability."

    # Replace the advertised.listeners placeholder in the manifest
    TMP_MANIFEST="/tmp/kafka-kraft.yaml"
    cat "${KAFKA_MANIFEST}" | sed "s|\${KAFKA_ADVERTISED_HOST}|${KAFKA_ADVERTISED_HOST}|g" > "${TMP_MANIFEST}"

    # Ensure the cluster ID exists BEFORE applying the main manifest
    ensure_kafka_cluster_id_cm

    echo "🔧 Applying Kafka manifest: ${TMP_MANIFEST}... (always apply to pick up changes)"
    if ! kubectl apply -f "${TMP_MANIFEST}" -n ${KAFKA_NAMESPACE}; then
        echo "❌ Error: Failed to apply Kafka manifest ${TMP_MANIFEST}."
        exit 1
    fi
    echo "✅ Kafka manifest applied."
}

function wait_for_kafka_ready() {
    echo "⏳ Waiting for Kafka StatefulSet '${KAFKA_STATEFULSET}' to be ready..."
    if ! kubectl wait --for=condition=ready pod -l app=kafka -n ${KAFKA_NAMESPACE} --timeout=5m; then
    # Fallback: Check rollout status if `wait --for=condition=ready pod` fails (might happen with complex readiness probes)
    # if ! kubectl rollout status statefulset/${KAFKA_STATEFULSET} -n ${KAFKA_NAMESPACE} --timeout=5m; then
        echo "❌ Error: Kafka StatefulSet did not become ready within the timeout period."
        echo "Debugging Kafka pods:"
        kubectl get pods -n ${KAFKA_NAMESPACE}
        kubectl describe statefulset ${KAFKA_STATEFULSET} -n ${KAFKA_NAMESPACE}
        # Try describing a pod
        kubectl describe pod/${KAFKA_STATEFULSET}-0 -n ${KAFKA_NAMESPACE} || true
        exit 1
    fi
    echo "✅ Kafka is ready!"
}

# Adapted from Bootstrap demo
function setup_vibectl() {
    echo "🔧 Installing vibectl..."
    # Assuming source is mounted at /home/sandbox/vibectl-src
    if [ -d "/home/sandbox/vibectl-src" ]; then
        echo "Installing vibectl from source directory..."
        cd /home/sandbox/vibectl-src
        if ! pip install -e .; then
            echo "❌ Error: Failed to install vibectl from source."
            exit 1
        fi
        echo "✅ vibectl installed from source"
        cd - >/dev/null
    else
        echo "❌ Error: vibectl source directory not found at /home/sandbox/vibectl-src" >&2
        echo "Make sure the volume is mounted correctly in compose.yml" >&2
        exit 1
    fi

    if ! command -v vibectl &> /dev/null; then
        echo "❌ Error: vibectl command not found after installation." >&2
        exit 1
    fi
    echo "Vibectl version: $(vibectl --version)"

    echo "🔧 Configuring vibectl..."

    # Ensure API key is set (required for LLM functionality)
    if [ -z "${VIBECTL_ANTHROPIC_API_KEY:-}" ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
        echo "Error: No API key provided. Please set VIBECTL_ANTHROPIC_API_KEY." >&2
        exit 1
    fi
    if [ -z "${VIBECTL_ANTHROPIC_API_KEY:-}" ] && [ -n "${ANTHROPIC_API_KEY:-}" ]; then
        export VIBECTL_ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}"
    fi

    echo "Configuring vibectl LLM API key..."
    LLM_KEYS_PATH=$(llm keys path 2>/dev/null)
    if [ -z "$LLM_KEYS_PATH" ]; then
        echo "Error: Could not determine keys path from llm tool." >&2
        # Fallback or debugging info
        echo "Attempting to find llm path manually: $(which llm || echo 'not found')" >&2
        echo "Python path: $(which python3 || echo 'not found')" >&2
        echo "Installed packages:" >&2
        pip list >&2
        # Do not exit here, as API key might be set via env var directly for vibectl
    else
        echo "LLM keys path: $LLM_KEYS_PATH"
        mkdir -p "$(dirname "$LLM_KEYS_PATH")"

        # Write the keys file directly (used by llm CLI, vibectl also checks env vars)
        # vibectl itself will prioritize VIBECTL_ANTHROPIC_API_KEY if set.
cat > "$LLM_KEYS_PATH" << EOF
{
  "anthropic": "${VIBECTL_ANTHROPIC_API_KEY}"
}
EOF
        chmod 600 "$LLM_KEYS_PATH"
        echo "LLM API key configured for llm CLI via keys file."
    fi

    echo "Setting custom instructions for vibectl..."
    INSTRUCTIONS_FILE_PATH="/home/sandbox/vibectl_instructions.txt"
    if [ -f "${INSTRUCTIONS_FILE_PATH}" ]; then
        echo "--- Debug: Instructions Substitution (using sed) ---"
        # Get values, applying defaults if env vars are empty/unset
        CPU_LIMIT="${K8S_SANDBOX_CPU_LIMIT:-4.0}"
        MEM_LIMIT="${K8S_SANDBOX_MEM_LIMIT:-4G}"
        LATENCY_TARGET="${TARGET_LATENCY_MS:-10.0}"

        echo "K8S_SANDBOX_CPU_LIMIT: '${CPU_LIMIT}'"
        echo "K8S_SANDBOX_MEM_LIMIT: '${MEM_LIMIT}'"
        echo "TARGET_LATENCY_MS: '${LATENCY_TARGET}'"

        # Perform substitutions using sed - pipe cat through multiple sed commands
        SUBSTITUTED_CONTENT=$(cat "${INSTRUCTIONS_FILE_PATH}" | \
            sed "s|\${K8S_SANDBOX_CPU_LIMIT:-4.0}|${CPU_LIMIT}|g" | \
            sed "s|\${K8S_SANDBOX_MEM_LIMIT:-4G}|${MEM_LIMIT}|g" | \
            sed "s|\${TARGET_LATENCY_MS:-10.0}|${LATENCY_TARGET}|g"
        )

        if [ $? -ne 0 ]; then
            echo "❌ Error: sed substitution command failed! Falling back to raw instructions." >&2
            INSTRUCTIONS_CONTENT=$(cat "${INSTRUCTIONS_FILE_PATH}") # Fallback
        else
            echo "--- sed substituted content ---"
            echo "${SUBSTITUTED_CONTENT}"
            echo "--- end sed substituted content ---"
            INSTRUCTIONS_CONTENT="${SUBSTITUTED_CONTENT}"
        fi

        if ! vibectl config set custom_instructions "${INSTRUCTIONS_CONTENT}"; then
            echo "❌ Error: Failed to set custom instructions for vibectl." >&2
        else
            echo "✅ Custom instructions set from ${INSTRUCTIONS_FILE_PATH}."
        fi
        echo "--- End Debug: Instructions Substitution ---"
    else
        echo "⚠️ Warning: Instructions file not found at ${INSTRUCTIONS_FILE_PATH}. vibectl will run without them." >&2
    fi

    # Set other vibectl configurations as needed
    vibectl config set memory_max_chars 1000

    # Now set other vibectl configurations
    vibectl config set kubeconfig ${KUBECONFIG}
    vibectl config set kubectl_command kubectl
    vibectl config set show_memory true
    vibectl config set show_iterations true
    if [ "${VIBECTL_VERBOSE:-false}" = "true" ]; then
        echo "Verbose mode enabled: showing raw output and kubectl commands"
        vibectl config set show_raw_output true
        vibectl config set show_kubectl true
        export VIBECTL_TRACEBACK=1 # Enable tracebacks for debugging
    else
        vibectl config set show_raw_output false
        vibectl config set show_kubectl false
    fi

    # Use model provided by environment variable AFTER key is set
    if [ -n "${VIBECTL_MODEL:-}" ]; then
        vibectl config set model "${VIBECTL_MODEL}"
        echo "Vibectl model set to: ${VIBECTL_MODEL}"
    else
        echo "⚠️ VIBECTL_MODEL not set, using default model."
    fi

    echo "✅ vibectl configured."
}

function deploy_latency_reporter() {
    echo "🔧 Deploying latency reporter components..."
    # Apply RBAC first if it exists and is needed
    LATENCY_REPORTER_RBAC_MANIFEST="/home/sandbox/manifests/latency-reporter-rbac.yaml"
    if [ -f "${LATENCY_REPORTER_RBAC_MANIFEST}" ]; then
        if ! kubectl apply -f "${LATENCY_REPORTER_RBAC_MANIFEST}"; then
            echo "❌ Error: Failed to apply latency reporter RBAC manifest." >&2
            # Decide if this is fatal or a warning
        else
            echo "✅ Latency reporter RBAC manifest applied."
        fi
    else
        echo "ℹ️ Latency reporter RBAC manifest not found at ${LATENCY_REPORTER_RBAC_MANIFEST}, skipping."
    fi

    # Apply ConfigMap
    LATENCY_CM_MANIFEST="/home/sandbox/manifests/kafka-latency-cm.yaml"
    if ! kubectl apply -f "${LATENCY_CM_MANIFEST}"; then
        echo "❌ Error: Failed to apply latency ConfigMap manifest." >&2
        # Attempt to get logs or describe if it exists
        kubectl get configmap kafka-latency-metrics -n kafka -o yaml || true
        exit 1
    fi
    echo "✅ Latency ConfigMap applied."

    # Start the python reporter script in the background
    echo "🔧 Starting latency reporter script in background..."
    # Ensure STATUS_DIR is set for the script environment if needed
    # Make sure KUBECTL_CMD points to the right kubectl if not default
    # Export TARGET_LATENCY_MS for the reporter
    export STATUS_DIR KUBECTL_CMD="kubectl" CONFIGMAP_NAME CONFIGMAP_NAMESPACE CONFIGMAP_KEY CHECK_INTERVAL_S TARGET_LATENCY_MS
    nohup python /home/sandbox/latency-reporter.py > /tmp/latency-reporter.log 2>&1 &
    REPORTER_PID=$!
    echo "✅ Metrics reporter started in background (PID: $REPORTER_PID). Log: /tmp/latency-reporter.log"
    # Optional: Add trap to kill reporter PID on exit?
}

function run_vibectl_loop() {
    echo "🔄 Starting vibectl monitoring loop..."
    # Define log file path
    LOG_FILE="${STATUS_DIR}/vibectl_agent.log"

    vibectl memory set "Start by examining the existing Kafka setup." >> "${LOG_FILE}" 2>&1

    while true; do
        # Check for shutdown signal
        if [ -f "${SHUTDOWN_FILE}" ]; then
            echo "🛑 Shutdown signal received. Exiting loop."
            break
        fi

        echo "[Loop] Running vibectl auto (output to ${LOG_FILE})..." # Log before running
        # Run vibectl auto without limits or explicit memory updates.
        # Rely on vibectl's internal logic and instructions to handle metrics.
        if ! vibectl auto "Proceed with the next step. If there's no obvious next step, check the kafka-latency-metrics ConfigMap in the 'kafka' namespace." >> "${LOG_FILE}" 2>&1; then
            echo "⚠️ Warning: vibectl auto command failed. Check ${LOG_FILE}. Continuing loop." >&2
            # Also log the failure message to the file itself
            echo "[Loop] ⚠️ vibectl auto command failed." >> "${LOG_FILE}" 2>&1
        else
            # Optional: Add a success log message if needed
            echo "[Loop] vibectl auto completed successfully." >> "${LOG_FILE}" 2>&1
        fi

        # Sleep for a longer interval as vibectl auto now runs potentially longer tasks
        echo "[Loop] Sleeping for 60 seconds..."
        sleep 60
    done
}

# --- Main Execution ---

if [ -f "$PHASE1_COMPLETE" ]; then
    echo "[INFO] Phase 1 (k8s, Kafka, Port Forward) already complete. Re-establishing port forward via Python manager..."
    # Ensure necessary env vars are exported for the python script if it's re-run
    export KUBECTL_CMD KAFKA_NAMESPACE KAFKA_SERVICE KAFKA_PORT KUBECTL_LOG_FILE="/tmp/kubectl-port-forward.log" # Ensure KUBECTL_LOG_FILE is set
    # Launch the Python port forward manager in the background
    echo "🔧 Launching Python port forward manager in background (re-entrant)..."
    nohup python3 /home/sandbox/port_forward_manager.py > /tmp/port_forward_manager_stdout.log 2>&1 &
    PF_MANAGER_PID=$!
    echo "✅ Python Port Forward Manager (re-entrant) started with PID: ${PF_MANAGER_PID}. Logs: /tmp/port_forward_manager_stdout.log and ${KUBECTL_LOG_FILE}"
    sleep 5 # Brief wait
    echo "✅ Phase 1 complete! Kafka is ready and port-forwarded (via Python manager)." > "${PHASE1_COMPLETE}"
else
    echo "[INFO] Starting Phase 1: K8s Cluster, Kafka Deployment, Port Forwarding via Python manager."
    setup_k3d_cluster
    patch_kubeconfig
    wait_for_k8s_ready

    # Copy the patched kubeconfig to the shared status volume for other services
    echo "📋 Copying patched kubeconfig to ${STATUS_DIR}/k3d_kubeconfig for other services..."
    if [ -f "${KUBECONFIG}" ]; then
        cp "${KUBECONFIG}" "${STATUS_DIR}/k3d_kubeconfig"
        chmod 644 "${STATUS_DIR}/k3d_kubeconfig" # Ensure it's readable
        echo "✅ Kubeconfig copied."
    else
        echo "❌ Error: Patched kubeconfig ${KUBECONFIG} not found after setup." >&2
    fi

    deploy_kafka
    wait_for_kafka_ready
    
    # Ensure necessary env vars are exported for the python script
    export KUBECTL_CMD KAFKA_NAMESPACE KAFKA_SERVICE KAFKA_PORT KUBECTL_LOG_FILE="/tmp/kubectl-port-forward.log"

    # Launch the Python port forward manager in the background
    echo "🔧 Launching Python port forward manager in background..."
    nohup python3 /home/sandbox/port_forward_manager.py > /tmp/port_forward_manager_stdout.log 2>&1 &
    PF_MANAGER_PID=$!
    echo "✅ Python Port Forward Manager started with PID: ${PF_MANAGER_PID}. Logs: /tmp/port_forward_manager_stdout.log and ${KUBECTL_LOG_FILE}"
    
    echo "⏳ Waiting 5 seconds for Python port forward manager to initialize..."
    sleep 5

    echo "Touching ${KAFKA_READY_FILE}..."
    touch "${KAFKA_READY_FILE}"
    sync 
    echo "✅ ${KAFKA_READY_FILE} touched and synced."

    echo "✅ Phase 1 complete! Kafka is ready and port-forwarded (via Python manager)." > "${PHASE1_COMPLETE}"
fi

if [ -f "$PHASE2_COMPLETE" ]; then
    echo "[INFO] Phase 2 (vibectl setup) already complete. Skipping."
else
    echo "[INFO] Starting Phase 2: Vibectl setup."
    setup_vibectl
    echo "✅ Phase 2 complete! Vibectl is ready." > "${PHASE2_COMPLETE}"
fi

# Deploy and start the latency reporter *after* K8s/Kafka/Vibectl setup is done
deploy_latency_reporter

# Start the main vibectl loop
run_vibectl_loop

echo "🏁 Sandbox finished."
