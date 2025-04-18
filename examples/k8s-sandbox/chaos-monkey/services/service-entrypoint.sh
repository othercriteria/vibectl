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
  - containerPort: ${NODE_PORT_1:-30001}
    hostPort: ${NODE_PORT_1:-30001}
    # Bind to local interface only, not 0.0.0.0
    listenAddress: "127.0.0.1"
  - containerPort: ${NODE_PORT_2:-30002}
    hostPort: ${NODE_PORT_2:-30002}
    listenAddress: "127.0.0.1"
  - containerPort: ${NODE_PORT_3:-30003}
    hostPort: ${NODE_PORT_3:-30003}
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

# Create services (assuming YAML files are in the mounted kubernetes directory)
log "Deploying target services..."
for file in /kubernetes/*.yaml; do
    if [ -f "$file" ]; then
        log "Applying $file"
        kubectl apply -f "$file"
    fi
done

# Wait for deployments to be ready
log "Waiting for all deployments to be ready..."
kubectl wait --for=condition=available --timeout=180s deployment --all -n services

# Create a simple frontend service just to get started
log "Creating default frontend service..."
cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  namespace: services
spec:
  replicas: 1
  selector:
    matchLabels:
      app: frontend
  template:
    metadata:
      labels:
        app: frontend
    spec:
      containers:
      - name: nginx
        image: nginx:1.21
        ports:
        - containerPort: 80
        volumeMounts:
        - name: nginx-config
          mountPath: /usr/share/nginx/html
      volumes:
      - name: nginx-config
        configMap:
          name: frontend-content
---
apiVersion: v1
kind: Service
metadata:
  name: frontend
  namespace: services
spec:
  selector:
    app: frontend
  ports:
  - port: 80
    targetPort: 80
    nodePort: ${NODE_PORT_1:-30001}
  type: NodePort
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: frontend-content
  namespace: services
data:
  index.html: |
    <!DOCTYPE html>
    <html>
    <head>
      <title>Chaos Monkey Demo</title>
      <style>
        body {
          font-family: Arial, sans-serif;
          margin: 40px;
          text-align: center;
        }
        h1 {
          color: #333;
        }
        .status {
          padding: 20px;
          background-color: #f1f1f1;
          border-radius: 5px;
          margin: 20px 0;
        }
      </style>
    </head>
    <body>
      <h1>Service Status: Online</h1>
      <div class="status">
        <p>This service is currently operational.</p>
        <p>Service ID: frontend-v1</p>
        <p>Last updated: <span id="timestamp"></span></p>
      </div>
      <script>
        document.getElementById('timestamp').innerText = new Date().toISOString();
        setInterval(function() {
          document.getElementById('timestamp').innerText = new Date().toISOString();
        }, 1000);
      </script>
    </body>
    </html>
EOF

log "Services deployed successfully"

# Add a simple backend API service
log "Creating default backend service..."
cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: services
spec:
  replicas: 2
  selector:
    matchLabels:
      app: backend
  template:
    metadata:
      labels:
        app: backend
    spec:
      containers:
      - name: nginx
        image: nginx:1.21
        ports:
        - containerPort: 80
        volumeMounts:
        - name: nginx-config
          mountPath: /usr/share/nginx/html
      volumes:
      - name: nginx-config
        configMap:
          name: backend-content
---
apiVersion: v1
kind: Service
metadata:
  name: backend
  namespace: services
spec:
  selector:
    app: backend
  ports:
  - port: 80
    targetPort: 80
    nodePort: ${NODE_PORT_2:-30002}
  type: NodePort
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: backend-content
  namespace: services
data:
  index.html: |
    {
      "status": "ok",
      "service": "backend-api",
      "version": "1.0",
      "time": "dynamic",
      "endpoints": [
        "/api/users",
        "/api/products",
        "/api/orders"
      ]
    }
EOF

log "Backend service deployed successfully"

# Add a database service
log "Creating database service..."
cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: database
  namespace: services
spec:
  replicas: 1
  selector:
    matchLabels:
      app: database
  template:
    metadata:
      labels:
        app: database
    spec:
      containers:
      - name: redis
        image: redis:6
        ports:
        - containerPort: 6379
        resources:
          limits:
            memory: "256Mi"
            cpu: "200m"
          requests:
            memory: "128Mi"
            cpu: "100m"
---
apiVersion: v1
kind: Service
metadata:
  name: database
  namespace: services
spec:
  selector:
    app: database
  ports:
  - port: 6379
    targetPort: 6379
  type: ClusterIP
EOF

log "Database service deployed successfully"

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
