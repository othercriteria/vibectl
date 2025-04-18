#!/bin/bash
set -euo pipefail

# Set up Docker group ID if provided
if [ -n "${DOCKER_GID:-}" ]; then
    # Check if the group already exists with this GID
    if getent group ${DOCKER_GID} > /dev/null; then
        groupmod -g ${DOCKER_GID} docker
    else
        # Create the group with the provided GID
        groupadd -g ${DOCKER_GID} docker
    fi
    # Add user to docker group
    usermod -aG docker root
fi

# Default values for environment variables
SESSION_DURATION=${SESSION_DURATION:-30}
VERBOSE=${VERBOSE:-false}
NODE_PORT_1=${NODE_PORT_1:-30001}
NODE_PORT_2=${NODE_PORT_2:-30002}
NODE_PORT_3=${NODE_PORT_3:-30003}

echo "Starting Chaos Monkey services container..."
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
    kind delete cluster --name chaos-monkey
    log "Cleanup complete"
}

# Register the cleanup function to be called on EXIT
trap cleanup EXIT

# Create kind cluster
log "Creating Kubernetes cluster with Kind..."
cat <<EOF > /kind-config.yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: chaos-monkey
nodes:
- role: control-plane
  # Port mappings only needed within the container, not exposed to host
  extraPortMappings:
  - containerPort: ${NODE_PORT_1}
    hostPort: ${NODE_PORT_1}
    # Bind to local interface only, not 0.0.0.0
    listenAddress: "127.0.0.1"
  - containerPort: ${NODE_PORT_2}
    hostPort: ${NODE_PORT_2}
    listenAddress: "127.0.0.1"
  - containerPort: ${NODE_PORT_3}
    hostPort: ${NODE_PORT_3}
    listenAddress: "127.0.0.1"
EOF

kind create cluster --config /kind-config.yaml
log "Kubernetes cluster created successfully"

# Set up Kubernetes config
export KUBECONFIG=/root/.kube/config

# Wait for the cluster to be ready
log "Waiting for Kubernetes cluster to be ready..."
until kubectl cluster-info > /dev/null 2>&1; do
    echo -n "."
    sleep 2
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
for file in /kubernetes/*.yaml; do
    if [ -f "$file" ]; then
        log "Applying $file"
        # Replace environment variables in the YAML file before applying
        envsubst < "$file" | kubectl apply -f -
    fi
done

# Wait for deployments to be ready
log "Waiting for all deployments to be ready..."
kubectl wait --for=condition=available --timeout=180s deployment --all -n services

# Verify all services
log "Verifying all services..."
kubectl get pods -n services
kubectl get svc -n services

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
