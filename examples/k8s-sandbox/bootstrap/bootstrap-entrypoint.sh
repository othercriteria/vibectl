#!/bin/bash
set -euo pipefail

# Configure environment
export OLLAMA_MODEL=${OLLAMA_MODEL:-tinyllama}
export RESOURCE_LIMIT_CPU=${RESOURCE_LIMIT_CPU:-2}
export RESOURCE_LIMIT_MEMORY=${RESOURCE_LIMIT_MEMORY:-4Gi}
export STATUS_DIR="/home/bootstrap/status"
export USE_STABLE_VERSIONS=${USE_STABLE_VERSIONS:-false}
export VIBECTL_VERSION=${VIBECTL_VERSION:-0.5.0}
export LLM_VERSION=${LLM_VERSION:-0.24.2}
export K3D_CLUSTER_NAME=${K3D_CLUSTER_NAME:-vibectl-demo}

mkdir -p "${STATUS_DIR}"
PHASE1_COMPLETE="${STATUS_DIR}/phase1_complete"
PHASE2_COMPLETE="${STATUS_DIR}/phase2_complete"

# --- Functions ---
function setup_k3d_cluster() {
    echo "Checking for existing K3d cluster '${K3D_CLUSTER_NAME}'..."
    if k3d cluster list | grep -q "${K3D_CLUSTER_NAME}"; then
        echo "Found existing cluster with the same name. Removing it first..."
        k3d cluster delete ${K3D_CLUSTER_NAME} || true
        sleep 5
    fi
    echo "Creating K3d cluster with minimal configuration..."
    if ! k3d cluster create ${K3D_CLUSTER_NAME}; then
        echo "Error: Failed to create K3d cluster."
        exit 1
    fi
    echo "K3d cluster created successfully!"
}

function patch_kubeconfig() {
    export KUBECONFIG="/home/bootstrap/kubeconfig"
    echo "Using kubeconfig at: ${KUBECONFIG}"
    k3d kubeconfig get ${K3D_CLUSTER_NAME} > ${KUBECONFIG}
    K3D_SERVERLB_NAME="k3d-${K3D_CLUSTER_NAME}-serverlb"
    K3D_SERVERLB_IP=$(docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$K3D_SERVERLB_NAME")
    if [ -n "$K3D_SERVERLB_IP" ]; then
      sed -i "s#127.0.0.1:[0-9]*#${K3D_SERVERLB_IP}:6443#g" ${KUBECONFIG}
      sed -i "s#0.0.0.0:[0-9]*#${K3D_SERVERLB_IP}:6443#g" ${KUBECONFIG}
      echo "Patched kubeconfig to use k3d serverlb IP: $K3D_SERVERLB_IP:6443"
    else
      echo "Warning: Could not determine k3d serverlb IP. Kubeconfig may not work in DinD."
    fi
    sed -i '/certificate-authority-data/d' ${KUBECONFIG}
    awk '/server: /{print; print "    insecure-skip-tls-verify: true"; next}1' ${KUBECONFIG} > ${KUBECONFIG}.tmp && mv ${KUBECONFIG}.tmp ${KUBECONFIG}
    chmod 600 ${KUBECONFIG}
}

function wait_for_k8s_ready() {
    echo "Waiting for Kubernetes cluster to be ready..."
    for i in {1..30}; do
        if kubectl cluster-info; then
            echo "Kubernetes cluster is ready!"
            break
        fi
        if [ $i -eq 30 ]; then
            echo "Error: Kubernetes cluster did not become ready within the timeout period."
            exit 1
        fi
        echo "Waiting for Kubernetes API to be accessible... ($i/30)"
        sleep 10
    done
    echo "Verifying cluster connectivity..."
    kubectl get nodes
    echo "Checking Kubernetes API server connectivity..."
    if ! kubectl cluster-info; then
        echo "[ERROR] Kubernetes API server is not reachable. Check k3d cluster status and kubeconfig."
        exit 1
    fi
}

function install_helm_if_needed() {
    echo "Checking for Helm..."
    if ! command -v helm &> /dev/null; then
        echo "Installing Helm..."
        curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
    fi
}

function add_ollama_helm_repo() {
    echo "Adding ollama-helm repository..."
    if ! helm repo list | grep -q ollama-helm; then
        helm repo add ollama-helm https://otwld.github.io/ollama-helm/
    fi
    helm repo update
}

function create_ollama_values() {
    echo "Creating Helm values file for Ollama..."
    cat <<EOF > /tmp/ollama-values.yaml
image:
  repository: vibectl-ollama
  tag: ${OLLAMA_MODEL}
  pullPolicy: IfNotPresent

resources:
  limits:
    cpu: "${RESOURCE_LIMIT_CPU}"
    memory: "${RESOURCE_LIMIT_MEMORY}"
  requests:
    cpu: "0.5"
    memory: "1Gi"

env:
  - name: OLLAMA_MODELS
    value: /root/.ollama

securityContext:
  runAsUser: 0
  runAsGroup: 0

ollama:
  models:
    pull:
      - ${OLLAMA_MODEL}

service:
  type: ClusterIP
  port: 11434

persistentVolume:
  enabled: false
EOF
}

function create_post_renderer() {
    # Inlined for permissions reasons; see repo history for details.
    cat > /home/bootstrap/remove-ollama-volume.py <<'EOF'
#!/usr/bin/env python3
import sys
import yaml

docs = list(yaml.safe_load_all(sys.stdin))
out_docs = []
for doc in docs:
    if not doc:
        continue
    if doc.get('kind') == 'Deployment' and doc['metadata']['name'].startswith('ollama'):
        containers = doc['spec']['template']['spec']['containers']
        for c in containers:
            if 'volumeMounts' in c:
                c['volumeMounts'] = [vm for vm in c['volumeMounts'] if vm.get('name') != 'ollama-data']
        if 'volumes' in doc['spec']['template']['spec']:
            doc['spec']['template']['spec']['volumes'] = [
                v for v in doc['spec']['template']['spec']['volumes'] if v.get('name') != 'ollama-data'
            ]
    out_docs.append(doc)
yaml.safe_dump_all(out_docs, sys.stdout, sort_keys=False)
EOF
    chmod +x /home/bootstrap/remove-ollama-volume.py
}

function install_ollama_helm() {
    CHART_VERSION="1.14.0"
    echo "==== Downloading Ollama Helm chart version ${CHART_VERSION} ===="
    helm pull ollama-helm/ollama --version ${CHART_VERSION} --untar --untardir /tmp
    echo "Installing Ollama using Helm chart..."
    helm install ollama /tmp/ollama \
      --namespace ollama \
      --create-namespace \
      --values /tmp/ollama-values.yaml \
      --wait \
      --timeout 10m \
      --post-renderer /home/bootstrap/remove-ollama-volume.py
}

function wait_for_ollama_ready() {
    echo "Waiting for Ollama pod to be ready..."
    kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=ollama -n ollama --timeout=10m
    echo "Setting up port forwarding to Ollama service..."
    kubectl port-forward -n ollama svc/ollama 11434:11434 --address 0.0.0.0 &
    PORT_FORWARD_PID=$!
    trap "kill $PORT_FORWARD_PID 2>/dev/null || true; cleanup_phase1" EXIT
    echo "Waiting for Ollama API to be accessible..."
    for i in {1..60}; do
        if curl -s -f "http://localhost:11434/api/tags" > /dev/null; then
            echo "Ollama API is accessible!"
            break
        fi
        if [ $i -eq 60 ]; then
            echo "Error: Ollama API did not become accessible within the timeout period."
            echo "Debugging Ollama pod:"
            kubectl get pods -n ollama
            kubectl describe pods -n ollama
            kubectl logs -n ollama -l app.kubernetes.io/name=ollama
            exit 1
        fi
        echo "Waiting for Ollama API... ($i/60)"
        sleep 5
    done
    if ! curl -s "http://localhost:11434/api/tags" | grep -q "${OLLAMA_MODEL}"; then
        echo "Warning: Model ${OLLAMA_MODEL} not found in Ollama. It might still be pulling."
        echo "You can check model status with: curl http://localhost:11434/api/tags"
    else
        echo "Model ${OLLAMA_MODEL} is ready!"
    fi
}

function setup_vibectl() {
    echo "Installing required packages..."
    if [ "${USE_STABLE_VERSIONS}" = "true" ]; then
        echo "Using stable versions from PyPI"
        echo "- vibectl: ${VIBECTL_VERSION}"
        echo "- llm: ${LLM_VERSION}"
        pip install --no-cache-dir llm==${LLM_VERSION} vibectl==${VIBECTL_VERSION}
        python -m llm install llm-ollama
    else
        echo "Installing llm and llm-ollama..."
        pip install --no-cache-dir llm==${LLM_VERSION}
        python -m llm install llm-ollama
        if [ -d "/home/bootstrap/vibectl-src" ]; then
            echo "Installing vibectl from source directory..."
            cd /home/bootstrap/vibectl-src
            if ! pip install -e .; then
                echo "Error: Failed to install vibectl from source."
                echo "Consider using --use-stable-versions flag for a more reliable setup."
                exit 1
            fi
            echo "vibectl installed from source"
            cd - >/dev/null
        else
            echo "Error: vibectl source directory not found at /home/bootstrap/vibectl-src"
            echo "Please ensure the repository is mounted or use the --use-stable-versions flag."
            exit 1
        fi
    fi
    if ! command -v vibectl &> /dev/null; then
        echo "Error: vibectl command not found after installation."
        echo "Please use --use-stable-versions flag for a more reliable setup."
        exit 1
    fi
    echo "Vibectl version: $(vibectl --version)"
    echo "Configuring vibectl..."
    vibectl config set model "${OLLAMA_MODEL}"
    vibectl config set kubeconfig /home/bootstrap/kubeconfig
    vibectl config set kubectl_command kubectl
    vibectl config show
    cat > /home/bootstrap/COMMANDS.md <<EOF
# Vibectl Command Examples

## Basic Commands

- View configuration: `vibectl config show`
- Get resources with AI analysis: `vibectl get pods`
- Describe resources with AI insights: `vibectl describe deployment`
- Analyze your Kubernetes resources: `vibectl vibe "analyze my cluster resources"`

## AI-Powered Commands

- Let vibectl suggest improvements: `vibectl vibe "suggest improvements for my cluster"`
- Ask questions: `vibectl vibe "How do I scale a deployment?"`
- Use memory context to continue work: `vibectl vibe "continue working on our cluster"`
- Check cluster state: `vibectl vibe "what's the status of our cluster?"`

## Memory Features

- View current memory: `vibectl memory show`
- Set memory manually: `vibectl memory set "Working on cluster configuration"`
- Clear memory: `vibectl memory clear`

For more information, see the full documentation at:
https://github.com/othercriteria/vibectl
EOF
}

# --- Main Script ---

if [ -f "$PHASE1_COMPLETE" ]; then
    echo "[INFO] Phase 1 (cluster and Ollama) already complete. Skipping."
else
    echo "[INFO] Starting Phase 1: Cluster and Ollama setup."
    setup_k3d_cluster
    patch_kubeconfig
    wait_for_k8s_ready
    install_helm_if_needed
    add_ollama_helm_repo
    create_ollama_values
    create_post_renderer
    # Import the pre-built Ollama image into k3d
    echo "==== Importing Ollama image into k3d cluster '${K3D_CLUSTER_NAME}' (inside container) ===="
    k3d image import vibectl-ollama:${OLLAMA_MODEL} -c ${K3D_CLUSTER_NAME}
    install_ollama_helm
    wait_for_ollama_ready
    echo "Phase 1 complete!" > "$PHASE1_COMPLETE"
    echo "[INFO] Phase 1 complete."
fi

if [ -f "$PHASE2_COMPLETE" ]; then
    echo "[INFO] Phase 2 (vibectl setup) already complete. Skipping."
else
    echo "[INFO] Starting Phase 2: Vibectl setup."
    setup_vibectl
    echo "Phase 2 complete!" > "$PHASE2_COMPLETE"
    echo "[INFO] Phase 2 complete."
fi

echo "==== Kubernetes demo environment is ready! ===="
echo "Container will remain running to allow vibectl commands to be executed"
echo "K3d cluster name: ${K3D_CLUSTER_NAME}"
echo "Ollama is running inside the cluster and accessible via http://localhost:11434"
echo "See /home/bootstrap/COMMANDS.md for example vibectl commands"

echo "To shut down, run: touch ${STATUS_DIR}/shutdown or use cleanup.sh."
while true; do
    if [ -f ${STATUS_DIR}/shutdown ]; then
        echo "Shutdown requested. Exiting..."
        break
    fi
    sleep 5
done
