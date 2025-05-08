#!/bin/bash
set -euo pipefail
set -x # Enable debug tracing

# Configuration Variables
export KUBECONFIG="$HOME/.kube/config"
PASSIVE_DURATION=${PASSIVE_DURATION:-5} # Duration of passive phase in minutes (default 5)
ACTIVE_DURATION=${ACTIVE_DURATION:-25} # Duration of active phase in minutes (default 25)
# New: Increased timeouts for better resilience
COMPONENT_WAIT_TIMEOUT=${COMPONENT_WAIT_TIMEOUT:-300s} # Wait timeout for critical components (5 mins)
MAX_RETRIES=${MAX_RETRIES:-30} # Maximum retries for operations
RETRY_INTERVAL=${RETRY_INTERVAL:-5} # Seconds between retries

echo "Chaos Monkey Demo - Kubernetes Sandbox Entrypoint"
echo "-------------------------------------------------"
echo "Configuration:"
echo "- Passive RBAC Duration: ${PASSIVE_DURATION} minutes"
echo "- Active RBAC Duration: ${ACTIVE_DURATION} minutes"
echo "- Component Wait Timeout: ${COMPONENT_WAIT_TIMEOUT}"
echo "-------------------------------------------------"

# Default values for environment variables
VERBOSE=${VERBOSE:-false}
API_SERVER_PORT=6443

echo "Starting Chaos Monkey Kubernetes sandbox..."

# Enhanced logging for verbose mode
function log() {
    if [ "${VERBOSE}" = "true" ]; then
        echo "[$(date +%T)] $1"
    fi
}

# Function to clean up resources
function cleanup() {
    log "Cleaning up resources..."
    # Ensure kind cluster deletion even on script errors
    kind delete cluster --name chaos-monkey 2>/dev/null || true
    log "Cleanup complete"
}

# Wait for API server
function wait_for_api_server() {
    log "Waiting for API server to be ready..."
    local retry_count=0
    while [ $retry_count -lt $MAX_RETRIES ]; do
        if kubectl cluster-info 2>/dev/null | grep -q 'Kubernetes'; then
            log "API server is ready"
            return 0
        fi
        retry_count=$((retry_count + 1))
        log "API server not ready yet, waiting (attempt $retry_count/$MAX_RETRIES)..."
        sleep $RETRY_INTERVAL
    done
    echo "ERROR: API server did not become ready in time"
    return 1
}

# Wait for daemonset to be ready
function wait_for_daemonset_ready() {
    local daemonset_name=$1
    local namespace=$2
    local min_seconds=${3:-5}
    local max_attempts=${4:-10}
    local attempt=0

    echo "Waiting for daemonset ${daemonset_name} in namespace ${namespace} to be ready..."

    # Wait at least min_seconds to give it time to initialize
    sleep $min_seconds

    while [ $attempt -lt $max_attempts ]; do
        # Get the number of desired, current, ready, up-to-date pods
        local desired=$(kubectl get daemonset ${daemonset_name} -n ${namespace} -o jsonpath='{.status.desiredNumberScheduled}' 2>/dev/null || echo "0")
        local current=$(kubectl get daemonset ${daemonset_name} -n ${namespace} -o jsonpath='{.status.currentNumberScheduled}' 2>/dev/null || echo "0")
        local ready=$(kubectl get daemonset ${daemonset_name} -n ${namespace} -o jsonpath='{.status.numberReady}' 2>/dev/null || echo "0")
        local updated=$(kubectl get daemonset ${daemonset_name} -n ${namespace} -o jsonpath='{.status.updatedNumberScheduled}' 2>/dev/null || echo "0")

        echo "Daemonset ${daemonset_name}: desired=${desired}, current=${current}, ready=${ready}, updated=${updated}"

        # Check if daemonset is ready (all pods running and ready)
        if [ "$desired" != "0" ] && [ "$desired" = "$current" ] && [ "$desired" = "$ready" ] && [ "$desired" = "$updated" ]; then
            echo "✅ Daemonset ${daemonset_name} is fully ready"
            return 0
        fi

        attempt=$((attempt + 1))
        echo "Daemonset not fully ready yet (attempt $attempt/$max_attempts), waiting..."
        sleep 5
    done

    echo "⚠️ Daemonset ${daemonset_name} did not become fully ready within timeout"
    return 1
}

# Function to check service accessibility in the Kind container
function check_service() {
    local port=$1
    local kind_container="chaos-monkey-control-plane"
    local kind_container_ip

    # Get the Kind container IP (where K8s is actually running)
    kind_container_ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' $kind_container 2>/dev/null || echo "")

    if [ -z "$kind_container_ip" ]; then
        log "Could not determine Kind container IP"
        return 1
    fi

    log "Checking service at Kind container ${kind_container} (${kind_container_ip}:$port)"
    if ! nc -z $kind_container_ip $port &>/dev/null; then
        log "Port $port is not listening on Kind container"
        return 1
    fi

    log "Port $port is accessible on Kind container"
    local response
    response=$(curl -s --connect-timeout 5 --max-time 10 http://${kind_container_ip}:$port)

    if [ -z "$response" ]; then
        log "Empty response from port $port"
        return 1
    fi

    log "Got response from port $port: ${response}"
    return 0
}

# Register the cleanup function to be called on EXIT
trap cleanup EXIT

# Explicitly delete any pre-existing cluster to ensure clean state
log "Ensuring no previous 'chaos-monkey' cluster exists..."
kind delete cluster --name chaos-monkey 2>/dev/null || true

# Create kind cluster with proper API server binding
log "Creating Kubernetes cluster with Kind..."
# Process and use the kind-config.yaml file
envsubst < /kubernetes/kind-config.yaml > /tmp/kind-config.yaml

if ! kind create cluster --config /tmp/kind-config.yaml; then
  echo "Error: Failed to create Kind cluster."
  # Check if there's a port conflict
  if docker logs chaos-monkey-control-plane 2>&1 | grep -q "address already in use"; then
    echo "Port conflict detected. Another service is already using one of the required ports."
    echo "Try stopping any existing Kubernetes clusters or change the port mappings in docker-compose.yaml."
  fi
  exit 1
fi

log "Kubernetes cluster created successfully"

# Get the control plane container name and IP
CONTROL_PLANE_CONTAINER="chaos-monkey-control-plane"
CONTROL_PLANE_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "${CONTROL_PLANE_CONTAINER}" 2>/dev/null || echo "")

if [ -z "$CONTROL_PLANE_IP" ]; then
    echo "Error: Could not get control plane IP. This is required for the setup to work."
    exit 1
fi

log "Control plane IP is: ${CONTROL_PLANE_IP}"

# Set up Kubernetes config to use the control plane IP directly
export KUBECONFIG=/root/.kube/config

# Update the server URL in kubeconfig to use the control plane IP
log "Updating kubeconfig to use control plane IP directly"
kubectl config set-cluster kind-chaos-monkey --server="https://${CONTROL_PLANE_IP}:${API_SERVER_PORT}"

# Wait for the API server to become available before proceeding
wait_for_api_server

# Check if we can connect to the cluster
log "Checking Kubernetes connection..."
RETRY_COUNT=0

while ! kubectl cluster-info > /dev/null 2>&1; do
    echo -n "."
    RETRY_COUNT=$((RETRY_COUNT + 1))

    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo ""
        echo "ERROR: Cannot connect to Kubernetes API server"
        echo "Testing API server connection:"
        nc -zv 127.0.0.1 ${API_SERVER_PORT} || echo "Cannot connect to API server port on localhost"
        nc -zv ${CONTROL_PLANE_IP} ${API_SERVER_PORT} || echo "Cannot connect to API server port on container IP"
        exit 1
    fi

    sleep $RETRY_INTERVAL
done

echo " API server is reachable!"

# Wait for the cluster node to be definitively Ready
log "Waiting for Kubernetes cluster node to be ready..."
RETRY_COUNT=0

while ! kubectl get nodes | grep -q "Ready"; do
    echo -n "."
    RETRY_COUNT=$((RETRY_COUNT + 1))

    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo ""
        echo "ERROR: Kubernetes cluster did not become ready within the timeout period"
        echo "Last status of nodes:"
        kubectl get nodes || echo "Failed to get nodes status"
        exit 1
    fi

    sleep $RETRY_INTERVAL
done

echo " Kubernetes cluster is ready!"

# Function to wait for CoreDNS to be ready
function wait_for_coredns() {
    log "Waiting for CoreDNS to be ready..."
    local retry_count=0
    local max_retries=10

    while [ $retry_count -lt $max_retries ]; do
        # Check if CoreDNS pods exist and are running
        local pods_running=$(kubectl get pods -n kube-system -l k8s-app=kube-dns --field-selector=status.phase=Running -o name 2>/dev/null | wc -l)

        if [ "$pods_running" -gt 0 ]; then
            # Check for DNS endpoints
            if kubectl get endpoints kube-dns -n kube-system -o jsonpath='{.subsets[0].addresses[0].ip}' 2>/dev/null | grep -q .; then
                log "CoreDNS is ready with endpoints"
                return 0
            fi
        fi

        retry_count=$((retry_count + 1))
        log "CoreDNS not ready yet, waiting (attempt $retry_count/$max_retries)..."

        # On first attempt, show status
        if [ $retry_count -eq 1 ]; then
            echo "Current CoreDNS status:"
            kubectl get pods -n kube-system -l k8s-app=kube-dns -o wide || true
        fi

        # On third attempt, try restarting CoreDNS if needed
        if [ $retry_count -eq 3 ]; then
            echo "Trying to restart CoreDNS if needed..."
            kubectl rollout restart deployment coredns -n kube-system || true
        fi

        sleep 5
    done

    echo "WARNING: CoreDNS might not be fully ready. Proceeding anyway."
    return 0
}

# Function to install Kubernetes State Metrics (KSM)
function install_kubernetes_state_metrics() {
    log "Installing Kubernetes State Metrics (KSM)..."

    # Use latest stable version based on repo info and apply manifests from examples/standard
    KSM_VERSION="v2.15.0"
    KSM_BASE_URL="https://raw.githubusercontent.com/kubernetes/kube-state-metrics/${KSM_VERSION}/examples/standard"
    KSM_MANIFESTS=(
        "service-account.yaml"
        "cluster-role.yaml"
        "cluster-role-binding.yaml"
        "deployment.yaml"
        "service.yaml"
    )
    KSM_TEMP_DIR="/tmp/ksm-manifests-${KSM_VERSION}"
    mkdir -p "${KSM_TEMP_DIR}"

    log "Downloading KSM manifests for version ${KSM_VERSION} from ${KSM_BASE_URL}..."
    for manifest in "${KSM_MANIFESTS[@]}"; do
        local url="${KSM_BASE_URL}/${manifest}"
        local file="${KSM_TEMP_DIR}/${manifest}"
        log "Downloading ${url} to ${file}..."
        if ! curl -sSLf "${url}" -o "${file}"; then
            echo "ERROR: Failed to download KSM manifest ${manifest} from ${url}. curl exit code: $?"
            rm -rf "${KSM_TEMP_DIR}" # Clean up partial downloads
            return 1
        fi
        if [ ! -s "${file}" ]; then
            echo "ERROR: Downloaded KSM manifest file ${file} is empty."
            rm -rf "${KSM_TEMP_DIR}" # Clean up partial downloads
            return 1
        fi
        log "Successfully downloaded ${manifest}."
    done
    log "All KSM manifests downloaded successfully to ${KSM_TEMP_DIR}."

    # Optional: Validate manifests client-side before applying (optional)
    # log "Performing client-side validation of KSM manifests..."
    # if ! kubectl apply -f "${KSM_TEMP_DIR}" --validate=true --dry-run=client > /dev/null; then
    #     echo "WARNING: Client-side validation of KSM manifests failed."
    # fi

    log "Applying KSM manifests from ${KSM_TEMP_DIR}..."
    if ! kubectl apply -f "${KSM_TEMP_DIR}"; then
        echo "ERROR: Failed to apply KSM manifests from ${KSM_TEMP_DIR}."
        # Attempt to show logs from failed apply if possible, or list files applied
        ls -l "${KSM_TEMP_DIR}"
        return 1
    fi
    log "KSM manifests applied successfully."
    rm -rf "${KSM_TEMP_DIR}" # Clean up downloaded manifests

    # Wait for the KSM deployment object to exist before patching
    log "Waiting for KSM deployment object (kube-state-metrics in kube-system) to be created..."
    RETRY_COUNT=0
    # Note: The deployment name might vary based on the manifest, confirm it's 'kube-state-metrics'
    KSM_DEPLOYMENT_NAME="kube-state-metrics"
    while ! kubectl get deployment ${KSM_DEPLOYMENT_NAME} -n kube-system &>/dev/null; do
        echo -n "."
        RETRY_COUNT=$((RETRY_COUNT + 1))
        if [ $RETRY_COUNT -ge 10 ]; then
            echo ""
            echo "WARNING: KSM deployment object '${KSM_DEPLOYMENT_NAME}' did not get created in time. Skipping patch."
            return 1 # Return error as we couldn't ensure tolerations
        fi
        sleep 3
    done
    echo " KSM deployment object created."

    # Add tolerations using kubectl patch
    log "Adding tolerations to KSM deployment '${KSM_DEPLOYMENT_NAME}' using kubectl patch..."
    KSM_PATCH='{"spec":{"template":{"spec":{"tolerations":[{"key":"node-role.kubernetes.io/control-plane","operator":"Exists","effect":"NoSchedule"}]}}}}'
    if ! kubectl patch deployment ${KSM_DEPLOYMENT_NAME} -n kube-system --type=strategic --patch="${KSM_PATCH}"; then
        echo "WARNING: Failed to patch KSM deployment '${KSM_DEPLOYMENT_NAME}' with tolerations. It might not run on the control plane node."
        # Continue, but log the warning.
    else
        log "Successfully patched KSM deployment '${KSM_DEPLOYMENT_NAME}' with tolerations."
    fi

    # Wait for KSM to become available (best effort)
    log "Waiting for KSM deployment '${KSM_DEPLOYMENT_NAME}' to become available (best effort)..."
    if ! kubectl wait --for=condition=available --timeout=60s deployment/${KSM_DEPLOYMENT_NAME} -n kube-system; then
        echo "WARNING: KSM deployment '${KSM_DEPLOYMENT_NAME}' did not become available in 60 seconds."
        echo "Will continue without waiting further for KSM."
        # Not returning error, we'll proceed anyway
    else
        echo "✅ KSM deployment '${KSM_DEPLOYMENT_NAME}' is ready!"

        # Verify KSM service is working
        log "Verifying KSM service..."
        # Note: Service name might also vary, assuming 'kube-state-metrics' based on standard practice
        KSM_SERVICE_NAME="kube-state-metrics"
        KSM_POD=$(kubectl get pods -n kube-system -l app.kubernetes.io/name=${KSM_DEPLOYMENT_NAME} -o name | head -1)
        if [ -n "$KSM_POD" ]; then
            echo "KSM pod found: ${KSM_POD}"

            # Check KSM logs
            kubectl logs ${KSM_POD} -n kube-system --tail=5 || true

            # Report service information
            echo "KSM service information (${KSM_SERVICE_NAME}):"
            kubectl get service ${KSM_SERVICE_NAME} -n kube-system -o wide || echo "Could not get service info for ${KSM_SERVICE_NAME}"
        else
            echo "WARNING: KSM pod not found for deployment ${KSM_DEPLOYMENT_NAME}, but deployment was applied."
        fi
    fi

    return 0
}

# Apply Namespaces, Quotas, and initial PASSIVE RBAC
log "Applying initial Kubernetes configurations (Namespaces, initial RBAC)..."
kubectl apply -f /kubernetes/namespaces.yaml
log "Applying standalone agent ServiceAccounts..."
kubectl apply -f /kubernetes/agent-serviceaccounts.yaml
kubectl apply -f /kubernetes/blue-agent-passive-rbac.yaml
kubectl apply -f /kubernetes/red-agent-passive-rbac.yaml
# Apply Poller RBAC early so the SA exists for token generation later
log "Applying Poller RBAC..."
kubectl apply -f /kubernetes/poller-rbac.yaml
# Apply Overseer RBAC
log "Applying Overseer RBAC..."
kubectl apply -f /kubernetes/overseer-rbac.yaml

# Create Agent Kubeconfigs
log "Creating dedicated kubeconfigs for services..."
mkdir -p /config/kube

# Get cluster CA data and server URL using jq for reliability
CLUSTER_CONFIG_JSON=$(kubectl config view -o json --raw)
if [ -z "$CLUSTER_CONFIG_JSON" ]; then
    echo "ERROR: Failed to get cluster config as JSON."
    exit 1
fi

SERVER_URL=$(echo "$CLUSTER_CONFIG_JSON" | jq -r '.clusters[] | select(.name=="kind-chaos-monkey") | .cluster.server')
CA_DATA=$(echo "$CLUSTER_CONFIG_JSON" | jq -r '.clusters[] | select(.name=="kind-chaos-monkey") | .cluster."certificate-authority-data"') # Note: key needs quoting for jq

if [ -z "$SERVER_URL" ] || [ -z "$CA_DATA" ]; then
    echo "ERROR: Failed to retrieve server URL or CA data using jq."
    exit 1
fi

# Function to create agent kubeconfig (Moved from later in the script)
create_agent_kubeconfig() {
    local agent_sa_name=$1
    local agent_namespace=$2 # Now expects namespace as arg
    local config_path=$3
    # Use a consistent context name format
    local context_name=\"${agent_namespace}/${agent_sa_name}\"

    log "Generating token for ServiceAccount ${agent_namespace}/${agent_sa_name}..."
    # Use a reasonably long duration, e.g., 8 hours. Adjust if needed.
    AGENT_TOKEN=$(kubectl create token "${agent_sa_name}" -n "${agent_namespace}" --duration=8h)
    if [ -z "$AGENT_TOKEN" ]; then
        echo "ERROR: Failed to generate token for ServiceAccount ${agent_namespace}/${agent_sa_name}"
        exit 1
    fi
    log "Token generated successfully for ${agent_namespace}/${agent_sa_name}."

    log "Creating kubeconfig file at ${config_path} for ${agent_namespace}/${agent_sa_name}"
    # Create dedicated config file

    # Decode CA data to a temporary file
    local temp_ca_file=$(mktemp)
    echo "${CA_DATA}" | base64 --decode > "${temp_ca_file}"

    kubectl config set-cluster kind-chaos-monkey \
      --server="${SERVER_URL}" \
      --certificate-authority="${temp_ca_file}" \
      --embed-certs=true \
      --kubeconfig="${config_path}"

    # Clean up temporary CA file
    rm -f "${temp_ca_file}"

    kubectl config set-credentials "${agent_sa_name}" --token="${AGENT_TOKEN}" --kubeconfig="${config_path}"
    kubectl config set-context "${context_name}" --cluster=kind-chaos-monkey --user="${agent_sa_name}" --namespace="${agent_namespace}" --kubeconfig="${config_path}"
    kubectl config use-context "${context_name}" --kubeconfig="${config_path}"
    chmod 644 "${config_path}"
    log "Kubeconfig created and configured at ${config_path}"
}

# Function to switch RBAC for an agent
# Arguments:
# $1: Agent Role (e.g., "Red", "Blue")
# $2: Passive RBAC YAML file path
# $3: Active RBAC YAML file path
# $4: Service Account Name (e.g., "red-agent", "blue-agent")
# $5: Service Account Namespace (e.g., "chaos-monkey-system")
# $6: Target Kubeconfig Path (e.g., "/config/kube/red-agent-config")
switch_agent_rbac() {
    local agent_role="$1"
    local passive_rbac_yaml="$2"
    local active_rbac_yaml="$3"
    local sa_name="$4"
    local sa_namespace="$5"
    local kubeconfig_path="$6"
    local agent_name_lower
    agent_name_lower=$(echo "$agent_role" | tr '[:upper:]' '[:lower:]') # red or blue

    echo "[RBAC Switch][${agent_role}] Starting RBAC transition..."

    # --- Delete Passive RBAC ---
    echo "[RBAC Switch][${agent_role}] Deleting passive RBAC from ${passive_rbac_yaml}..."
    # Use kubectl delete with --ignore-not-found and capture exit code
    if ! kubectl delete -f "${passive_rbac_yaml}" --ignore-not-found=true; then
        echo "[RBAC Switch][${agent_role}] WARNING: Problem occurred during passive RBAC deletion (kubectl delete exit code $?). Continuing..."
        # Don't exit, maybe it was already gone or partially deleted
    else
        echo "[RBAC Switch][${agent_role}] Passive RBAC deletion command executed."
    fi

    # Optional: Add specific verification checks here if needed, e.g.:
    # if kubectl get clusterrolebinding "${agent_name_lower}-agent-passive-view-binding" > /dev/null 2>&1; then
    #    echo "[RBAC Switch][${agent_role}] WARNING: Passive ClusterRoleBinding still found after delete!"
    # fi

    echo "[RBAC Switch][${agent_role}] Waiting 2 seconds after passive RBAC deletion..."
    sleep 2

    # --- Apply Active RBAC ---
    echo "[RBAC Switch][${agent_role}] Applying active RBAC from ${active_rbac_yaml}..."
    if ! kubectl apply -f "${active_rbac_yaml}"; then
        echo "[RBAC Switch][${agent_role}] ERROR: Failed to apply active RBAC from ${active_rbac_yaml}!"
        # Optionally add more debug info here, e.g., show the YAML content or last few lines of kubectl output
        exit 1 # Critical failure
    fi
    echo "[RBAC Switch][${agent_role}] Active RBAC applied successfully."

    # Optional: Add specific verification checks here if needed, e.g.:
    # if ! kubectl get clusterrolebinding "${agent_name_lower}-agent-binding" > /dev/null 2>&1; then
    #     echo "[RBAC Switch][${agent_role}] ERROR: Active ClusterRoleBinding not found after apply!"
    # fi

    # --- Regenerate Kubeconfig (Now Skipped) ---
    # echo "[RBAC Switch][${agent_role}] Regenerating Kubeconfig (${kubeconfig_path}) with active token..."
    # # Call the existing function to handle regeneration
    # create_agent_kubeconfig "${sa_name}" "${sa_namespace}" "${kubeconfig_path}"
    # echo "[RBAC Switch][${agent_role}] Kubeconfig regenerated."

    echo "[RBAC Switch][${agent_role}] Waiting 2 seconds after active RBAC application..."
    sleep 2

    echo "[RBAC Switch][${agent_role}] RBAC transition completed."
}

# Create kubeconfig using chaos-monkey-system namespace for all SAs
create_agent_kubeconfig "blue-agent" "chaos-monkey-system" "/config/kube/blue-agent-config"
create_agent_kubeconfig "red-agent" "chaos-monkey-system" "/config/kube/red-agent-config"
create_agent_kubeconfig "poller-sa" "chaos-monkey-system" "/config/kube/poller-config"
create_agent_kubeconfig "overseer-sa" "chaos-monkey-system" "/config/kube/overseer-config"

log "Dedicated service kubeconfigs created."

# Install Kubernetes State Metrics for resource monitoring
install_kubernetes_state_metrics

# Create services
log "Deploying target services..."

# Check for Kubernetes YAML files in the /kubernetes directory
if [ ! -d "/kubernetes" ] || [ -z "$(ls -A /kubernetes/*.yaml 2>/dev/null)" ]; then
    echo "ERROR: No Kubernetes YAML files found in /kubernetes directory."
    echo "The demo requires service definitions to be present at /kubernetes/*.yaml"
    exit 1
fi

# Apply all YAML files found in the kubernetes directory
for file in /kubernetes/demo-*.yaml; do
    if [ -f "$file" ]; then
        log "Applying $file"
        echo "Applying Kubernetes manifest: $file"

        # Apply with descriptive output for debugging
        if ! envsubst < "$file" | kubectl apply -f - ; then
            echo "ERROR: Failed to apply $file"
            echo "Content of $file:"
            cat "$file" | grep -v "^\s*#" | grep -v "^\s*$"
            exit 1
        fi

        # Verify namespace exists after applying manifests
        if ! kubectl get namespace services &>/dev/null; then
            echo "ERROR: services namespace not found after applying $file"
            echo "Available namespaces:"
            kubectl get namespaces
            exit 1
        fi
    fi
done

# Wait for deployments to be ready with a simplified loop
log "Waiting for deployments in 'services' namespace to be ready..."
MAX_DEPLOYMENT_RETRIES=3
DEPLOYMENT_RETRY=0

while [ $DEPLOYMENT_RETRY -lt $MAX_DEPLOYMENT_RETRIES ]; do
    # Attempt to wait for all deployments in the namespace
    if kubectl wait --for=condition=available --timeout=60s deployment --all -n services 2>/dev/null; then
        echo "✅ All deployments in services namespace are ready."
        break # Exit loop on success
    else
        DEPLOYMENT_RETRY=$((DEPLOYMENT_RETRY + 1))
        if [ $DEPLOYMENT_RETRY -ge $MAX_DEPLOYMENT_RETRIES ]; then
            echo "ERROR: Deployments in 'services' namespace did not become ready after $MAX_DEPLOYMENT_RETRIES attempts."
            echo "Final deployment status:"
            kubectl get deployments -n services || echo "Failed to get final deployment status."
            exit 1 # Exit script on final failure
        else
            echo "WARNING: Deployments not ready yet, attempt $DEPLOYMENT_RETRY of $MAX_DEPLOYMENT_RETRIES. Retrying in 20 seconds..."
            sleep 20
        fi
    fi
done

# Apply Resource Quotas and Network Isolation AFTER services are ready
log "Applying Resource Quotas..."
kubectl apply -f /kubernetes/resource-quotas.yaml

log "Applying System Monitoring Namespace Isolation..."
kubectl apply -f /kubernetes/system-monitoring-isolation.yaml

# --- Passive Phase Wait ---
echo "Waiting for PASSIVE phase duration (${PASSIVE_DURATION} minutes)..."
sleep ${PASSIVE_DURATION}m

# --- Switch to Active RBAC ---
echo "Passive phase complete. Switching to ACTIVE RBAC rules..."

# --- Red Agent RBAC Switch ---
switch_agent_rbac "Red" \
                  "/kubernetes/red-agent-passive-rbac.yaml" \
                  "/kubernetes/red-agent-active-rbac.yaml" \
                  "red-agent" \
                  "chaos-monkey-system" \
                  "/config/kube/red-agent-config"

# --- Blue Agent RBAC Switch ---
switch_agent_rbac "Blue" \
                  "/kubernetes/blue-agent-passive-rbac.yaml" \
                  "/kubernetes/blue-agent-active-rbac.yaml" \
                  "blue-agent" \
                  "chaos-monkey-system" \
                  "/config/kube/blue-agent-config"

echo "Active Phase RBAC configured for both agents."

# Wait for the active duration
log "Running active phase for ${ACTIVE_DURATION} minutes..."

# --- Active Phase Wait ---
echo "Waiting for ACTIVE phase duration (${ACTIVE_DURATION} minutes)..."
sleep ${ACTIVE_DURATION}m

# --- Session End ---
echo "Active phase duration complete."
echo "-------------------------------------------------"
echo "Chaos Monkey Demo Session Finished."
echo "-------------------------------------------------"

# Cleanup will be handled by the trap EXIT
