#!/bin/bash
set -euo pipefail

# Default values for environment variables
SESSION_DURATION=${SESSION_DURATION:-30}
VERBOSE=${VERBOSE:-false}
# Use hardcoded values for internal ports
NODE_PORT_1=30001
NODE_PORT_2=30002
NODE_PORT_3=30003
API_SERVER_PORT=6443

echo "Starting Chaos Monkey Kubernetes sandbox..."
echo "Session duration: ${SESSION_DURATION} minutes"

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

# Create kind cluster with proper API server binding
log "Creating Kubernetes cluster with Kind..."
cat <<EOF > /tmp/kind-config.yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: chaos-monkey
networking:
  # Don't expose API server port to host
  podSubnet: "10.244.0.0/16"
  serviceSubnet: "10.245.0.0/16"
nodes:
- role: control-plane
  # Map the service nodeports within the container, but don't expose to host
  extraPortMappings:
  - containerPort: ${NODE_PORT_1}
    hostPort: ${NODE_PORT_1}
  - containerPort: ${NODE_PORT_2}
    hostPort: ${NODE_PORT_2}
  - containerPort: ${NODE_PORT_3}
    hostPort: ${NODE_PORT_3}
  kubeadmConfigPatches:
  - |
    kind: ClusterConfiguration
    apiServer:
      extraArgs:
        # Bind to all interfaces within the container
        bind-address: "0.0.0.0"
EOF

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

# Check if we can connect to the cluster
log "Checking Kubernetes connection..."
MAX_RETRIES=15
RETRY_COUNT=0
RETRY_INTERVAL=2

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

# Wait for the cluster to be ready
log "Waiting for Kubernetes cluster to be ready..."
MAX_RETRIES=15
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

# Create namespaces
log "Creating namespaces..."
kubectl create namespace services
kubectl create namespace monitoring
kubectl create namespace protected

# Label namespaces for identification
kubectl label namespace services purpose=target
kubectl label namespace monitoring purpose=system
kubectl label namespace protected purpose=system

# Create roles and role bindings for the blue agent
log "Setting up RBAC for blue agent..."
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ServiceAccount
metadata:
  name: blue-agent
  namespace: default
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: blue-agent-role
rules:
- apiGroups: [""]
  resources: ["pods", "services", "configmaps", "secrets", "namespaces"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["apps"]
  resources: ["deployments", "replicasets", "statefulsets"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["batch"]
  resources: ["jobs", "cronjobs"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["networking.k8s.io"]
  resources: ["ingresses", "networkpolicies"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: [""]
  resources: ["nodes"]
  verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: blue-agent-binding
subjects:
- kind: ServiceAccount
  name: blue-agent
  namespace: default
roleRef:
  kind: ClusterRole
  name: blue-agent-role
  apiGroup: rbac.authorization.k8s.io
EOF

# Create roles and role bindings for the red agent (more limited)
log "Setting up RBAC for red agent..."
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ServiceAccount
metadata:
  name: red-agent
  namespace: default
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: red-agent-role
rules:
- apiGroups: [""]
  resources: ["pods", "services", "configmaps"]
  verbs: ["get", "list", "watch", "delete"]
- apiGroups: ["apps"]
  resources: ["deployments", "replicasets"]
  verbs: ["get", "list", "watch", "update", "patch"]
- apiGroups: [""]
  resources: ["nodes"]
  verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: red-agent-binding
subjects:
- kind: ServiceAccount
  name: red-agent
  namespace: default
roleRef:
  kind: ClusterRole
  name: red-agent-role
  apiGroup: rbac.authorization.k8s.io
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: red-agent-restricted
  namespace: protected
rules:
- apiGroups: [""]
  resources: ["pods", "services", "configmaps"]
  verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: red-agent-restricted-binding
  namespace: protected
subjects:
- kind: ServiceAccount
  name: red-agent
  namespace: default
roleRef:
  kind: Role
  name: red-agent-restricted
  apiGroup: rbac.authorization.k8s.io
EOF

# Create services
log "Deploying target services..."

# Check for Kubernetes YAML files in the /kubernetes directory
if [ ! -d "/kubernetes" ] || [ -z "$(ls -A /kubernetes/*.yaml 2>/dev/null)" ]; then
    echo "ERROR: No Kubernetes YAML files found in /kubernetes directory."
    echo "The demo requires service definitions to be present at /kubernetes/*.yaml"
    exit 1
fi

# Apply all YAML files found in the kubernetes directory
for file in /kubernetes/*.yaml; do
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

# Add more detailed verification of the deployment
echo "Verifying deployments in services namespace..."
kubectl get deployments -n services --no-headers || echo "No deployments found"

# Add specific check for app service
log "Checking for app service in services namespace..."
if ! kubectl get deployment app -n services &>/dev/null; then
    echo "WARNING: app deployment not found in services namespace"
    echo "Available deployments in services namespace:"
    kubectl get deployments -n services
    
    # Look for deployment in other namespaces as a fallback
    echo "Looking for app deployment in other namespaces:"
    kubectl get deployments --all-namespaces | grep app || echo "No app deployment found in any namespace"
else
    echo "✅ app deployment found in services namespace"
fi

# Check for Redis DB service
log "Checking for demo-db service in services namespace..."
if ! kubectl get deployment demo-db -n services &>/dev/null; then
    echo "WARNING: demo-db deployment not found in services namespace"
    echo "Available deployments in services namespace:"
    kubectl get deployments -n services
else
    echo "✅ demo-db deployment found in services namespace"
fi

# Wait for deployments to be ready with timeout and retries
log "Waiting for deployments to be ready..."
MAX_DEPLOYMENT_RETRIES=3
DEPLOYMENT_RETRY=0

while [ $DEPLOYMENT_RETRY -lt $MAX_DEPLOYMENT_RETRIES ]; do
    if kubectl wait --for=condition=available --timeout=60s deployment --all -n services 2>/dev/null; then
        echo "✅ All deployments in services namespace are ready"
        DEPLOYMENT_SUCCESS=true
        break
    else
        DEPLOYMENT_RETRY=$((DEPLOYMENT_RETRY + 1))
        echo "WARNING: Deployments not ready yet, attempt $DEPLOYMENT_RETRY of $MAX_DEPLOYMENT_RETRIES"
        echo "Current deployment status:"
        kubectl get deployments -n services
        
        # Check specific app deployment status with more details
        echo "Detailed status of app deployment:"
        kubectl describe deployment app -n services || echo "Cannot get details for app deployment"
        
        # Check pod status if deployment exists
        echo "Checking pod status for app deployment:"
        kubectl get pods -n services -l app=app || echo "No pods found for app=app"
        
        if [ $DEPLOYMENT_RETRY -ge $MAX_DEPLOYMENT_RETRIES ]; then
            echo "ERROR: Deployments did not become ready after $MAX_DEPLOYMENT_RETRIES attempts"
            echo "Final deployment status:"
            kubectl get deployments -n services
            exit 1
        else
            echo "Retrying in 20 seconds..."
            sleep 20
        fi
    fi
done

# Create a shared kubeconfig for agent containers
log "Creating shared kubeconfig for agent containers..."
mkdir -p /config/kube

# Copy the current kubeconfig and update it for agent use
cp /root/.kube/config /config/kube/config

# Important: for access from other containers, use the control plane IP directly
kubectl config set-cluster kind-chaos-monkey --server="https://${CONTROL_PLANE_IP}:${API_SERVER_PORT}" --kubeconfig=/config/kube/config
chmod 644 /config/kube/config
log "Shared kubeconfig created at /config/kube/config with server URL: https://${CONTROL_PLANE_IP}:${API_SERVER_PORT}"

# Final verification of the services
echo "Final verification of resources in services namespace:"
kubectl get all -n services

# Check pod logs for app deployment
echo "Checking logs for app pods:"
APP_POD=$(kubectl get pods -n services -l app=app -o name | head -1)
if [ -n "$APP_POD" ]; then
    kubectl logs "${APP_POD}" -n services || echo "Cannot get logs for app pod"
    
    # Check app pod status - fixed format
    echo "App pod details:"
    kubectl describe "${APP_POD}" -n services || echo "Cannot describe app pod"
else
    echo "No app pods found"
fi

# Keep container running
echo "All services deployed. Container will keep running for the duration of the session."

# Create a counter to track remaining time
DURATION_SECONDS=$((SESSION_DURATION * 60))
START_TIME=$(date +%s)
END_TIME=$((START_TIME + DURATION_SECONDS))

while true; do
    CURRENT_TIME=$(date +%s)
    REMAINING_SECONDS=$((END_TIME - CURRENT_TIME))

    # Exit if time is up
    if [ $REMAINING_SECONDS -le 0 ]; then
        echo "Session duration completed. Exiting..."
        break
    fi

    # Keep alive with time remaining display every minute
    if [ $((REMAINING_SECONDS % 60)) -eq 0 ]; then
        REMAINING_MINUTES=$((REMAINING_SECONDS / 60))
        echo "Services running. $REMAINING_MINUTES minutes remaining."
    fi

    sleep 1
done

# Cleanup handled by EXIT trap
