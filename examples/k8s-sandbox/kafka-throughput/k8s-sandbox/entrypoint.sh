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
        echo "🧹 Found existing cluster with the same name. Removing it first..."
        k3d cluster delete ${K3D_CLUSTER_NAME} || true
        sleep 5
    fi
    echo "✨ Creating K3d cluster '${K3D_CLUSTER_NAME}'..."
    # Note: Add any specific k3d flags if needed (e.g., ports, agents)
    if ! k3d cluster create ${K3D_CLUSTER_NAME}; then
        echo "❌ Error: Failed to create K3d cluster."
        exit 1
    fi
    echo "✅ K3d cluster created successfully!"
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

function ensure_kafka_cluster_id() {
    local cluster_id_cm="kafka-cluster-id-config"
    echo "🔧 Ensuring Kafka Cluster ID ConfigMap (${cluster_id_cm}) exists..."
    if kubectl get configmap "${cluster_id_cm}" -n "${KAFKA_NAMESPACE}" > /dev/null 2>&1; then
        echo "✅ Cluster ID ConfigMap already exists."
        return 0
    fi

    echo "🤔 Cluster ID ConfigMap not found. Generating new Cluster ID..."
    # Note: Assumes kafka-storage.sh is available in the image PATH
    # May need to adjust path depending on the Kafka image used (e.g., /opt/kafka/bin/kafka-storage.sh)
    local cluster_id
    if ! cluster_id=$(kafka-storage.sh random-uuid); then
        echo "❌ Error: Failed to generate Kafka Cluster ID using kafka-storage.sh random-uuid" >&2
        exit 1
    fi
    echo "🔑 Generated Cluster ID: ${cluster_id}"

    echo "📝 Creating ConfigMap ${cluster_id_cm} with Cluster ID..."
    cat <<EOF | kubectl apply -n "${KAFKA_NAMESPACE}" -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: ${cluster_id_cm}
  namespace: ${KAFKA_NAMESPACE}
data:
  clusterId: "${cluster_id}"
EOF
    if [ $? -ne 0 ]; then
        echo "❌ Error: Failed to create Cluster ID ConfigMap." >&2
        exit 1
    fi
    echo "✅ Cluster ID ConfigMap created successfully."
}

function deploy_kafka() {
    echo "🔧 Creating Kafka namespace: ${KAFKA_NAMESPACE}..."
    kubectl create namespace ${KAFKA_NAMESPACE} || echo "Namespace ${KAFKA_NAMESPACE} likely already exists."

    # Ensure the cluster ID exists BEFORE applying the main manifest
    ensure_kafka_cluster_id

    echo "🔧 Deploying Kafka from manifest: ${KAFKA_MANIFEST}..."
    if ! kubectl apply -f "${KAFKA_MANIFEST}" -n ${KAFKA_NAMESPACE}; then
        echo "❌ Error: Failed to apply Kafka manifest ${KAFKA_MANIFEST}."
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
    echo "🔧 Setting up port forwarding for Kafka service '${KAFKA_SERVICE}' on port ${KAFKA_PORT}..."
    # Run in background, redirect output, make accessible from all interfaces
    kubectl port-forward -n ${KAFKA_NAMESPACE} svc/${KAFKA_SERVICE} ${KAFKA_PORT}:${KAFKA_PORT} --address 0.0.0.0 >/tmp/kafka-pf.log 2>&1 &
    PORT_FORWARD_PID=$!
    # Ensure the port-forward process is killed when the script exits
    trap "echo '🧹 Cleaning up port forward (PID: $PORT_FORWARD_PID)...'; kill $PORT_FORWARD_PID 2>/dev/null || true" EXIT
    sleep 5 # Give port-forward time to establish

    # Verify port-forwarding is listening (simple netstat check)
    echo "⏳ Verifying port forward..."
    if ! ss -tln | grep -q ":${KAFKA_PORT}"; then
        echo "❌ Error: Failed to establish port forwarding for Kafka on port ${KAFKA_PORT}."
        echo "Port forward logs:"
        cat /tmp/kafka-pf.log
        exit 1
    fi
    echo "✅ Port forwarding for Kafka established (PID: $PORT_FORWARD_PID)."
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
    vibectl config set kubeconfig ${KUBECONFIG}
    vibectl config set kubectl_command kubectl
    # Use model provided by environment variable
    if [ -n "${VIBECTL_MODEL:-}" ]; then
        vibectl config set model "${VIBECTL_MODEL}"
    else
        echo "⚠️ VIBECTL_MODEL not set, vibectl may not function correctly for 'vibe' commands."
    fi
    echo "Current vibectl config:"
    vibectl config show

    # Define goal and constraints using vibectl setup
    CPU_LIMIT="${K8S_SANDBOX_CPU_LIMIT:-4.0}" # Read from env, default if unset
    MEM_LIMIT="${K8S_SANDBOX_MEM_LIMIT:-4G}" # Read from env, default if unset

    echo "🔧 Setting up vibectl goal and constraints (CPU: ${CPU_LIMIT}, Memory: ${MEM_LIMIT})..."
    # Use heredoc for multiline instructions
    vibectl setup --goal "Maximize Kafka producer throughput while minimizing consumer P99 latency, observed via /tmp/status/latency.txt." --instructions - <<-EOF
	You are operating within a resource-constrained Kubernetes sandbox (k3d).
	The container hosting Kubernetes and Kafka is limited to approximately ${CPU_LIMIT} CPUs and ${MEM_LIMIT} Memory.
	The Kafka cluster runs as a StatefulSet named 'kafka-controller' in the 'kafka' namespace.
	You can tune the following Kafka parameters by patching the StatefulSet's environment variables:
	- KAFKA_HEAP_OPTS (e.g., -Xms<size>m -Xmx<size>m)
	- KAFKA_NUM_NETWORK_THREADS (integer)
	- KAFKA_NUM_IO_THREADS (integer)

	Monitor the P99 latency reported by the consumer in /tmp/status/latency.txt (mounted in this container).
	Use 'kubectl patch statefulset kafka-controller -n kafka --type=strategic -p ...' to apply changes.
	Ensure changes respect the resource limits of the sandbox.
	Start with the initial low settings and iteratively improve them.
	The Kafka broker service inside Kubernetes is kafka-controller-0.kafka-headless.kafka.svc.cluster.local:9092.
	The external Kafka endpoint (via port-forward) is localhost:9092 from this container's perspective.
	Focus on tuning the env vars mentioned above.
	EOF

    if [ $? -ne 0 ]; then
        echo "❌ Error: Failed to run vibectl setup." >&2
        exit 1
    fi

    echo "✅ vibectl configured and setup complete."
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

# Start the main vibectl loop
run_vibectl_loop

echo "🏁 Sandbox finished."
