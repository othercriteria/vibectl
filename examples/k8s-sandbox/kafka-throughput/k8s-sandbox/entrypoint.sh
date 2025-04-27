#!/bin/bash
set -euo pipefail

echo "🚀 Starting Kafka Demo Sandbox Entrypoint..."

# Environment variables from compose.yml
# K3D_CLUSTER_NAME, STATUS_DIR, VIBECTL_MODEL, etc.

# --- Configuration ---
export KUBECONFIG="/home/sandbox/.kube/config"
export KAFKA_MANIFEST="/home/sandbox/kafka/kafka-kraft.yaml"
export KAFKA_NAMESPACE="kafka"
export KAFKA_SERVICE="kafka-service"
export KAFKA_PORT=9092
export KAFKA_STATEFULSET="kafka-controller"
export KAFKA_REPLICAS=1 # Assuming 1 replica for KRaft initially
export KAFKA_CLUSTER_ID_CM="kafka-cluster-id" # Define the ConfigMap name

# Status files
mkdir -p "${STATUS_DIR}"
PHASE1_COMPLETE="${STATUS_DIR}/phase1_k8s_kafka_setup_complete"
PHASE2_COMPLETE="${STATUS_DIR}/phase2_vibectl_setup_complete"
KAFKA_READY_FILE="${STATUS_DIR}/kafka_ready"
LATENCY_FILE="${STATUS_DIR}/latency.txt"
SHUTDOWN_FILE="${STATUS_DIR}/shutdown"

# --- Functions ---

# Reusable function from Bootstrap demo
function setup_k3d_cluster() {
    echo "🔧 Checking for existing K3d cluster '${K3D_CLUSTER_NAME}'..."
    if k3d cluster list | grep -q "${K3D_CLUSTER_NAME}"; then
        echo "✅ Found existing cluster '${K3D_CLUSTER_NAME}'. Reusing it."
        # Optionally, verify cluster health here if needed in the future.
        return 0 # Cluster already exists, no need to create
    else
        echo "🤔 Cluster '${K3D_CLUSTER_NAME}' not found. Creating it..."
        # Note: Add any specific k3d flags if needed (e.g., ports, agents)
        if ! k3d cluster create ${K3D_CLUSTER_NAME}; then
            echo "❌ Error: Failed to create K3d cluster."
            exit 1
        fi
        echo "✅ K3d cluster created successfully!"
    fi
}

# Reusable function from Bootstrap demo (adapted path)
function patch_kubeconfig() {
    echo "🔧 Patching kubeconfig..."
    mkdir -p /home/sandbox/.kube
    echo "Using kubeconfig at: ${KUBECONFIG}"
    k3d kubeconfig get ${K3D_CLUSTER_NAME} > ${KUBECONFIG}
    K3D_SERVERLB_NAME="k3d-${K3D_CLUSTER_NAME}-serverlb"
    K3D_SERVERLB_IP=$(docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$K3D_SERVERLB_NAME")
    if [ -n "$K3D_SERVERLB_IP" ]; then
      sed -i "s#127.0.0.1:[0-9]*#${K3D_SERVERLB_IP}:6443#g" ${KUBECONFIG}
      sed -i "s#0.0.0.0:[0-9]*#${K3D_SERVERLB_IP}:6443#g" ${KUBECONFIG}
      echo "Patched kubeconfig to use k3d serverlb IP: $K3D_SERVERLB_IP:6443"
    else
      echo "⚠️ Warning: Could not determine k3d serverlb IP. Kubeconfig may not work correctly."
    fi
    # Add insecure-skip-tls-verify and remove certificate-authority-data
    awk '/server: /{print; print "    insecure-skip-tls-verify: true"; next} !/certificate-authority-data/' ${KUBECONFIG} > ${KUBECONFIG}.tmp && mv ${KUBECONFIG}.tmp ${KUBECONFIG}
    chmod 600 ${KUBECONFIG}
    chown sandbox:sandbox ${KUBECONFIG}
    echo "✅ Kubeconfig patched."
}

# Reusable function from Bootstrap demo
function wait_for_k8s_ready() {
    echo "⏳ Waiting for Kubernetes cluster to be ready..."
    for i in {1..60}; do # Increased timeout slightly
        if kubectl cluster-info >/dev/null 2>&1; then
            echo "✅ Kubernetes cluster is ready!"
            kubectl get nodes # Show nodes
            return 0
        fi
        if [ $i -eq 60 ]; then
            echo "❌ Error: Kubernetes cluster did not become ready within the timeout period."
            k3d cluster list
            exit 1
        fi
        echo "Waiting for Kubernetes API... (${i}/60)"
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
    if [ -z "${KAFKA_ADVERTISED_HOST:-}" ]; then
        export KAFKA_ADVERTISED_HOST=$(hostname -i | awk '{print $1}')
        echo "Using container IP ${KAFKA_ADVERTISED_HOST} for Kafka advertised listener"
    else
        echo "Using environment-provided ${KAFKA_ADVERTISED_HOST} for Kafka advertised listener"
    fi

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

function setup_kafka_port_forward() {
    echo "🔧 Setting up resilient port forwarding for Kafka service '${KAFKA_SERVICE}' on port ${KAFKA_PORT}..."

    # Remove any existing trap to avoid conflicts with the loop's background process
    trap - EXIT

    # Kill any existing port-forward processes
    pkill -f "kubectl port-forward.*${KAFKA_SERVICE}" || true

    # Create a flag file to indicate when port forwarding is working
    PORT_FORWARD_OK="/tmp/kafka-port-forward-ok"
    rm -f ${PORT_FORWARD_OK}

    # Loop indefinitely to keep port-forward running
    ( # Run the loop in a subshell to handle backgrounding and errors
        while true; do
            echo "[Port Forward Loop] Starting kubectl port-forward..."
            # Run in foreground within the loop, log to file
            kubectl port-forward -n ${KAFKA_NAMESPACE} svc/${KAFKA_SERVICE} ${KAFKA_PORT}:${KAFKA_PORT} --address 0.0.0.0 >>/tmp/kafka-pf.log 2>&1 &
            PF_PID=$!

            # Wait for port-forwarding to be established
            for i in {1..12}; do
                if ss -tln | grep -q ":${KAFKA_PORT}"; then
                    echo "[Port Forward Loop] Port forwarding established on port ${KAFKA_PORT}"
                    touch ${PORT_FORWARD_OK}
                    break
                fi
                echo "[Port Forward Loop] Waiting for port ${KAFKA_PORT} to be open... (${i}/12)"
                sleep 2
            done

            # Wait for the process to exit or be killed
            wait $PF_PID

            # If kubectl exits (e.g., connection lost), log and wait before retrying
            echo "[Port Forward Loop] kubectl port-forward exited. Retrying in 10 seconds..." | tee -a /tmp/kafka-pf.log
            rm -f ${PORT_FORWARD_OK}
            sleep 10
        done
    ) &
    PORT_FORWARD_LOOP_PID=$!
    echo "✅ Port forward loop started in background (PID: $PORT_FORWARD_LOOP_PID)."

    # Verify port-forwarding is listening (wait up to 60s)
    echo "⏳ Verifying port forward establishment..."
    for i in {1..30}; do
        if [ -f ${PORT_FORWARD_OK} ]; then
            echo "✅ Port forwarding for Kafka is listening."
            return 0 # Success
        fi
        echo "   Waiting for port ${KAFKA_PORT} to be open... (${i}/30)"
        sleep 2
    done

    echo "❌ Error: Failed to establish port forwarding for Kafka on port ${KAFKA_PORT} within timeout."
    echo "Port forward logs:"
    cat /tmp/kafka-pf.log
    # Kill the background loop if verification fails
    kill $PORT_FORWARD_LOOP_PID 2>/dev/null || true
    exit 1
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

    # Configure vibectl using the llm tool approach
    echo "Configuring vibectl LLM API key..."
    LLM_KEYS_PATH=$(llm keys path 2>/dev/null)
    if [ -z "$LLM_KEYS_PATH" ]; then
        echo "Error: Could not determine keys path from llm tool." >&2
        # Fallback or debugging info
        echo "Attempting to find llm path manually: $(which llm || echo 'not found')" >&2
        echo "Python path: $(which python3 || echo 'not found')" >&2
        echo "Installed packages:" >&2
        pip list >&2
        exit 1
    fi
    echo "Using LLM keys path: $LLM_KEYS_PATH"

    # Ensure the directory exists (running as sandbox user)
    mkdir -p "$(dirname "$LLM_KEYS_PATH")"

    # Write the keys file directly
    cat > "$LLM_KEYS_PATH" << EOF
{
  "anthropic": "$VIBECTL_ANTHROPIC_API_KEY"
}
EOF
    chmod 600 "$LLM_KEYS_PATH"
    echo "LLM API key configured."

    # Now set other vibectl configurations
    vibectl config set kubeconfig ${KUBECONFIG}
    vibectl config set kubectl_command kubectl
    # Use model provided by environment variable AFTER key is set
    if [ -n "${VIBECTL_MODEL:-}" ]; then
        vibectl config set model "${VIBECTL_MODEL}"
        echo "Vibectl model set to: ${VIBECTL_MODEL}"
    else
        echo "⚠️ VIBECTL_MODEL not set, using default model."
    fi

    # Configure other vibectl settings (optional, based on needs)
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

    echo "✅ vibectl configured."
}

function run_vibectl_loop() {
    echo "🔄 Starting vibectl monitoring loop..."
    # No longer need to clear memory here, setup handles initial instructions
    # vibectl memory clear
    # vibectl memory set "Initial state: KRaft Kafka cluster running in k3d..."

    LAST_LATENCY=""
    while true; do
        # Check for shutdown signal
        if [ -f "${SHUTDOWN_FILE}" ]; then
            echo "🛑 Shutdown signal received. Exiting loop."
            break
        fi

        CURRENT_LATENCY=""
        if [ -f "${LATENCY_FILE}" ]; then
            CURRENT_LATENCY=$(cat "${LATENCY_FILE}")
            echo "[Loop] Found latency file: ${CURRENT_LATENCY}"
        else
            echo "[Loop] Latency file not found (${LATENCY_FILE}). Waiting..."
        fi

        # Only run vibectl if latency file exists and has changed since last check
        if [ -n "${CURRENT_LATENCY}" ] && [ "${CURRENT_LATENCY}" != "${LAST_LATENCY}" ]; then
            echo "[Loop] Latency updated. Updating memory and running vibectl auto..."
            # Update memory with the latest latency
            if ! vibectl memory update "Latest observed consumer latency: ${CURRENT_LATENCY}"; then
                echo "⚠️ Warning: Failed to update vibectl memory." >&2
            fi

            # Run vibectl auto with a limit
            if ! vibectl auto --limit 5; then
                echo "⚠️ Warning: vibectl auto command failed. Continuing loop." >&2
                # Consider adding error details to memory?
                # vibectl memory update "Vibectl auto failed. Last error: ..."
            fi

            LAST_LATENCY="${CURRENT_LATENCY}"
        else
             echo "[Loop] No new latency info. Sleeping..."
        fi

        sleep 15 # Check every 15 seconds
    done
}

function deploy_latency_reporter() {
    echo "🔧 Deploying latency reporter components..."
    # Apply ConfigMap first
    if ! kubectl apply -f /home/sandbox/kafka-latency-cm.yaml; then
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
    export STATUS_DIR KUBECTL_CMD="kubectl" CONFIGMAP_NAME CONFIGMAP_NAMESPACE CONFIGMAP_KEY CHECK_INTERVAL_S
    nohup python /home/sandbox/latency-reporter.py > /tmp/latency-reporter.log 2>&1 &
    REPORTER_PID=$!
    echo "✅ Latency reporter started in background (PID: $REPORTER_PID). Log: /tmp/latency-reporter.log"
    # Optional: Add trap to kill reporter PID on exit?
}

# --- Main Execution ---

if [ -f "$PHASE1_COMPLETE" ]; then
    echo "[INFO] Phase 1 (k8s, Kafka, Port Forward) already complete. Re-establishing port forward..."
    # Re-establish port forwarding if script restarted
    setup_kafka_port_forward
else
    echo "[INFO] Starting Phase 1: K8s Cluster, Kafka Deployment, Port Forwarding."
    setup_k3d_cluster
    patch_kubeconfig
    wait_for_k8s_ready
    deploy_kafka
    wait_for_kafka_ready
    setup_kafka_port_forward
    # Signal that Kafka is ready for dependents (producer/consumer)
    touch "${KAFKA_READY_FILE}"
    echo "✅ Phase 1 complete! Kafka is ready and port-forwarded." > "${PHASE1_COMPLETE}"
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
