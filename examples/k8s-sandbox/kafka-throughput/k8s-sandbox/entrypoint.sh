#!/bin/bash
set -euo pipefail

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
export KAFKA_CLUSTER_ID_CM="kafka-cluster-id-config" # Define the ConfigMap name

# Status files
mkdir -p "${STATUS_DIR}"
PHASE1_COMPLETE="${STATUS_DIR}/phase1_k8s_kafka_setup_complete"
PHASE2_COMPLETE="${STATUS_DIR}/phase2_vibectl_setup_complete"
KAFKA_READY_FILE="${STATUS_DIR}/kafka_ready"
SHUTDOWN_FILE="${STATUS_DIR}/shutdown"

# --- Functions ---

function setup_k3d_cluster() {
    echo "🔧 Setting up K3d cluster '${K3D_CLUSTER_NAME}'..."

    # Check if cluster exists
    if ! k3d cluster list | grep -q -w "${K3D_CLUSTER_NAME}"; then
        echo "🤔 Creating new cluster '${K3D_CLUSTER_NAME}' on network 'kafka-throughput_kafka-demo-network'..."
        # Add memory reservation arguments and specify the Docker network
        K3D_CREATE_LOG="/tmp/k3d_create.log"
        echo "Attempting: k3d cluster create \"${K3D_CLUSTER_NAME}\" \
             --network kafka-throughput_kafka-demo-network \
             --k3s-arg '--kubelet-arg=kube-reserved=memory=1Gi@server:*' \
             --k3s-arg '--kubelet-arg=system-reserved=memory=1Gi@server:*'"
        if ! k3d cluster create "${K3D_CLUSTER_NAME}" \
             --network kafka-throughput_kafka-demo-network \
             --k3s-arg '--kubelet-arg=kube-reserved=memory=1Gi@server:*' \
             --k3s-arg '--kubelet-arg=system-reserved=memory=1Gi@server:*' > "${K3D_CREATE_LOG}" 2>&1; then
            echo "❌ Error: Failed to create K3d cluster '${K3D_CLUSTER_NAME}' on the specified network with memory limits." >&2
            echo "--- k3d cluster create log (${K3D_CREATE_LOG}) ---" >&2
            cat "${K3D_CREATE_LOG}" >&2
            echo "--------------------------------------------------" >&2
            exit 1
        fi
        echo "--- k3d cluster create log (${K3D_CREATE_LOG}) ---"
        cat "${K3D_CREATE_LOG}"
        echo "--------------------------------------------------"
        # Important: Get kubeconfig *after* cluster is created and on the network
        k3d kubeconfig merge "${K3D_CLUSTER_NAME}" --kubeconfig-merge-default --kubeconfig-switch-context
        echo "✅ K3d cluster '${K3D_CLUSTER_NAME}' created and context set."
    else
        echo "✅ Using existing cluster '${K3D_CLUSTER_NAME}'"
        k3d kubeconfig merge "${K3D_CLUSTER_NAME}" --kubeconfig-merge-default --kubeconfig-switch-context

        # Clean up the kafka namespace if it exists
        echo "🧹 Cleaning up kafka namespace..."
        if kubectl get namespace "${KAFKA_NAMESPACE}" &>/dev/null; then
            kubectl delete namespace "${KAFKA_NAMESPACE}" --wait=false
            echo "⏳ Waiting for namespace cleanup..."
            # Wait for namespace to be gone or timeout
            for i in {1..30}; do
                if ! kubectl get namespace "${KAFKA_NAMESPACE}" &>/dev/null; then
                    echo "✅ Namespace cleanup complete"
                    break
                fi
                if [ $i -eq 30 ]; then
                    echo "⚠️ Warning: Namespace cleanup timed out, but continuing anyway"
                fi
                sleep 1
            done
        fi
    fi
}

function patch_kubeconfig() {
    echo "🔧 Patching kubeconfig..."
    mkdir -p /home/sandbox/.kube

    # Get original kubeconfig from k3d (after it has been placed on the correct network)
    k3d kubeconfig get "${K3D_CLUSTER_NAME}" > "${KUBECONFIG}.orig"

    echo "--- Original Kubeconfig from k3d (${KUBECONFIG}.orig) ---"
    cat "${KUBECONFIG}.orig"
    echo "------------------------------------------------------"

    # The k3d server/loadbalancer internal hostname. k3d typically names it k3d-<clustername>-serverlb
    # The k3s API typically runs on port 6443 inside the cluster/network.
    local K3D_INTERNAL_LB_HOST="k3d-${K3D_CLUSTER_NAME}-serverlb"
    local K3D_INTERNAL_API_PORT="6443"

    # The SERVER_URL from the original kubeconfig might be https://0.0.0.0:<mapped_port> or already an internal name.
    # We will explicitly set it to use the k3d load balancer's internal Docker DNS name and standard K8s API port.
    NEW_SERVER_URL="https://${K3D_INTERNAL_LB_HOST}:${K3D_INTERNAL_API_PORT}"
    echo "Patching kubeconfig to use server: ${NEW_SERVER_URL} and skip TLS verify"

    # Create a new kubeconfig with the patched server URL and insecure-skip-tls-verify
    awk -v new_url="${NEW_SERVER_URL}" \
        '/server:/ {
            print "    server: " new_url;
            print "    insecure-skip-tls-verify: true"; # Add/ensure skip TLS
            next;
        }
        /certificate-authority-data:/ { next; } # Remove CA data as we are skipping verification
        /insecure-skip-tls-verify:/ { next; } # Remove old insecure-skip-tls-verify if present
        { print; }
    ' "${KUBECONFIG}.orig" > "${KUBECONFIG}"

    if ! kubectl --kubeconfig "${KUBECONFIG}" config view &>/dev/null; then
        echo "❌ Error: Generated kubeconfig is invalid" >&2
        echo "Generated kubeconfig contents:" >&2
        cat "${KUBECONFIG}" >&2
        exit 1
    fi

    rm "${KUBECONFIG}.orig"
    chmod 600 "${KUBECONFIG}"
    chown sandbox:sandbox "${KUBECONFIG}"

    echo "✅ Kubeconfig patched successfully"

    # Copy to shared volume
    cp "${KUBECONFIG}" "${STATUS_DIR}/k3d_kubeconfig"
    chmod 644 "${STATUS_DIR}/k3d_kubeconfig"
}

function wait_for_k8s_ready() {
    echo "⏳ Waiting for Kubernetes cluster to be ready..."
    # Define K3D_INTERNAL_API_PORT here or ensure it's globally available if set in patch_kubeconfig
    local K3D_INTERNAL_API_PORT="6443" # Standard K8s API port

    for i in {1..30}; do
        echo "DEBUG: Attempting: kubectl --kubeconfig ${KUBECONFIG} cluster-info (Attempt ${i}/30)"
        # Remove &>/dev/null to see kubectl's output/error
        if kubectl --kubeconfig "${KUBECONFIG}" cluster-info; then
            echo "✅ Kubernetes cluster is ready! (kubectl cluster-info succeeded)"
            return 0
        else
            echo "DEBUG: kubectl cluster-info failed. Last exit code: $?"
            # Use the defined K3D_INTERNAL_API_PORT for the curl command
            echo "DEBUG: Trying curl to https://k3d-${K3D_CLUSTER_NAME}-serverlb:${K3D_INTERNAL_API_PORT}/version for more details..."
            if curl -kv "https://k3d-${K3D_CLUSTER_NAME}-serverlb:${K3D_INTERNAL_API_PORT}/version"; then
                echo "DEBUG: curl to https://k3d-${K3D_CLUSTER_NAME}-serverlb:${K3D_INTERNAL_API_PORT}/version succeeded. API seems partially responsive."
                # Even if curl works, we wait for kubectl cluster-info to be sure.
            else
                echo "DEBUG: curl to https://k3d-${K3D_CLUSTER_NAME}-serverlb:${K3D_INTERNAL_API_PORT}/version also failed. Last exit code: $?"
            fi
        fi
        echo "Waiting for Kubernetes API... (Attempt ${i}/30 failed, sleeping 2s)"
        sleep 2
    done
    echo "❌ Error: Kubernetes cluster did not become ready within timeout." >&2
    kubectl --kubeconfig "${KUBECONFIG}" cluster-info # Try one last time and show output
    echo "--- Kubeconfig contents (${KUBECONFIG}) ---" >&2
    cat "${KUBECONFIG}" >&2
    echo "-----------------------------------------" >&2
    exit 1
}

function ensure_kafka_cluster_id_cm() {
    echo "🔧 Ensuring Kafka Cluster ID is available and ConfigMap (${KAFKA_CLUSTER_ID_CM}) exists..."
    local CLUSTER_ID_FILE_PATH="${STATUS_DIR}/kafka_cluster_id.txt"
    local KAFKA_CLUSTER_ID_VALUE=""

    if [ -f "${CLUSTER_ID_FILE_PATH}" ]; then
        KAFKA_CLUSTER_ID_VALUE=$(cat "${CLUSTER_ID_FILE_PATH}")
        echo "🔑 Using existing Kafka Cluster ID from ${CLUSTER_ID_FILE_PATH}: ${KAFKA_CLUSTER_ID_VALUE}"
    else
        echo "🤔 Kafka Cluster ID file not found at ${CLUSTER_ID_FILE_PATH}. Generating new ID..."
        if command -v python3 &> /dev/null; then
            KAFKA_CLUSTER_ID_VALUE=$(python3 -c "import uuid; print(uuid.uuid4())")
        elif command -v python &> /dev/null; then
            KAFKA_CLUSTER_ID_VALUE=$(python -c "import uuid; print uuid.uuid4()") # Python 2 fallback
        else
            echo "❌ Error: Cannot generate UUID for Kafka Cluster ID. Python 3 or Python not found." >&2
            exit 1
        fi

        if [ -z "${KAFKA_CLUSTER_ID_VALUE}" ]; then
            echo "❌ Error: Failed to generate Kafka Cluster ID using Python." >&2
            exit 1
        fi
        echo "${KAFKA_CLUSTER_ID_VALUE}" > "${CLUSTER_ID_FILE_PATH}"
        # Ensure file is group-writable for potential access from other tools/users if needed, though primarily for persistence.
        chmod 664 "${CLUSTER_ID_FILE_PATH}"
        echo "✅ Generated and saved new Kafka Cluster ID to ${CLUSTER_ID_FILE_PATH}: ${KAFKA_CLUSTER_ID_VALUE}"
    fi

    # Ensure ConfigMap exists or create it
    if ! kubectl get configmap "${KAFKA_CLUSTER_ID_CM}" -n "${KAFKA_NAMESPACE}" >/dev/null 2>&1; then
        echo "Creating Kafka Cluster ID ConfigMap (${KAFKA_CLUSTER_ID_CM})..."
        if ! kubectl create configmap "${KAFKA_CLUSTER_ID_CM}" -n "${KAFKA_NAMESPACE}" --from-literal=clusterId="${KAFKA_CLUSTER_ID_VALUE}"; then
            echo "❌ Error: Failed to create Kafka Cluster ID ConfigMap '${KAFKA_CLUSTER_ID_CM}'." >&2
            exit 1
        fi
        echo "✅ Kafka Cluster ID ConfigMap created."
    else
        # Optional: Update existing ConfigMap if ID changed? For now, assume if CM exists, it's correct or will be handled by re-applying manifests.
        echo "✅ Kafka Cluster ID ConfigMap (${KAFKA_CLUSTER_ID_CM}) already exists."
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
        CPU_LIMIT="${K8S_SANDBOX_CPU_LIMIT}"
        MEM_LIMIT="${K8S_SANDBOX_MEM_LIMIT}"
        LATENCY_TARGET="${TARGET_LATENCY_MS}"

        echo "K8S_SANDBOX_CPU_LIMIT: '${CPU_LIMIT}'"
        echo "K8S_SANDBOX_MEM_LIMIT: '${MEM_LIMIT}'"
        echo "TARGET_LATENCY_MS: '${LATENCY_TARGET}'"

        # Perform substitutions using sed - pipe cat through multiple sed commands
        SUBSTITUTED_CONTENT=$(cat "${INSTRUCTIONS_FILE_PATH}" | \
            sed "s|\${K8S_SANDBOX_CPU_LIMIT}|${CPU_LIMIT}|g" | \
            sed "s|\${K8S_SANDBOX_MEM_LIMIT}|${MEM_LIMIT}|g" | \
            sed "s|\${TARGET_LATENCY_MS}|${LATENCY_TARGET}|g"
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

    # Create fresh kafka namespace
    echo "🔧 Creating kafka namespace..."
    kubectl create namespace "${KAFKA_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

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
