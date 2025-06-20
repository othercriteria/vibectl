#!/usr/bin/env bash
set -euo pipefail

echo "🎯 vibectl-server Demo: JWT Auth + CA Management + TLS"
echo "=============================================================="
echo ""
echo "This demo showcases various capabilities that support a production"
echo "deployment of vibectl-server with a private Certificate Authority."
echo ""

# Check that we're in the project root
if [[ ! -f "pyproject.toml" || ! -d "vibectl" ]]; then
    echo "❌ Error: Please run this script from the project root:"
    echo "   ./examples/manifests/vibectl-server/demo-ca.sh"
    echo ""
    echo "Current directory: $(pwd)"
    exit 1
fi

PROJECT_ROOT="."
MANIFESTS_DIR="examples/manifests/vibectl-server"
IMAGE_NAME="vibectl-server:local"
NAMESPACE="vibectl-server-ca"

echo "🧹 Cleaning up any previous demo setup..."
kubectl delete namespace "${NAMESPACE}" --ignore-not-found=true

echo ""
echo "🔨 Step 1: Building vibectl-server Docker image..."
echo "=================================================="
docker build -f "${MANIFESTS_DIR}/Dockerfile" -t "${IMAGE_NAME}" "${PROJECT_ROOT}"

echo ""
echo "📦 Step 1b: Loading image into cluster..."
echo "========================================"
# Auto-detect cluster type and load image appropriately
if kubectl get nodes -o jsonpath='{.items[0].status.nodeInfo.containerRuntimeVersion}' | grep -q containerd; then
    # Check if this is k3s
    if kubectl version --short 2>/dev/null | grep -q k3s; then
        echo "  Detected k3s cluster, importing image..."
        docker save "${IMAGE_NAME}" | sudo k3s ctr images import -
    # Check if this is kind
    elif kubectl config current-context | grep -q kind; then
        echo "  Detected kind cluster, loading image..."
        kind load docker-image "${IMAGE_NAME}"
    else
        echo "  Detected containerd cluster, attempting ctr import..."
        # Generic containerd approach
        docker save "${IMAGE_NAME}" | sudo ctr -n k8s.io images import -
    fi
elif kubectl get nodes -o jsonpath='{.items[0].status.nodeInfo.containerRuntimeVersion}' | grep -q docker; then
    # Check if this is minikube
    if kubectl config current-context | grep -q minikube; then
        echo "  Detected minikube cluster, loading image..."
        minikube image load "${IMAGE_NAME}"
    else
        echo "  Detected Docker runtime, image should be available..."
        # For Docker Desktop Kubernetes, the image should already be available
    fi
else
    echo "  ⚠️  Unknown cluster type, assuming image is available..."
fi

echo ""
echo "📦 Step 2: Creating namespace and deploying manifests..."
echo "========================================================"
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# Discover the node IP that will be used for external access
echo "🔍 Discovering node IP for certificate generation..."
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
echo "📍 Node IP: $NODE_IP"

# Create a ConfigMap with the node IP for the init container to use
echo "🔧 Creating node-info ConfigMap with discovered IP..."
kubectl create configmap vibectl-server-node-info \
  --from-literal=node-ip="$NODE_IP" \
  -n "${NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "🚀 Deploying vibectl-server..."
kubectl apply -n "${NAMESPACE}" -f "${MANIFESTS_DIR}/jwt-secret.yaml"
kubectl apply -n "${NAMESPACE}" -f "${MANIFESTS_DIR}/configmap-ca.yaml"
kubectl apply -n "${NAMESPACE}" -f "${MANIFESTS_DIR}/deployment-ca.yaml"
kubectl apply -n "${NAMESPACE}" -f "${MANIFESTS_DIR}/service-ca.yaml"

echo "✅ All manifests deployed successfully!"

echo ""
echo "⏳ Step 3: Waiting for deployment to be ready..."
echo "==============================================="
echo "Init containers will:"
echo "  🏭 Generate CA and server certificates"
echo "  🔑 Generate JWT demo token"
echo ""

# Wait for deployment to be ready (this includes init containers completing)
kubectl wait --for=condition=available deployment/vibectl-server -n "${NAMESPACE}" --timeout=300s

echo "✅ Deployment ready!"

echo ""
echo "📋 Step 4: Extracting demo data from running pod..."
echo "============================================="

# Wait for the main deployment to be ready
echo "⏳ Waiting for vibectl-server pod to be running..."
kubectl wait --for=condition=Ready pod -l app=vibectl-server -n "${NAMESPACE}" --timeout=300s

# Get the pod name
POD_NAME=$(kubectl get pod -l app=vibectl-server -n "${NAMESPACE}" -o jsonpath='{.items[0].metadata.name}')
echo "📦 Found pod: $POD_NAME"

# Wait for init containers to complete and files to be available
echo "⏳ Waiting for JWT token and CA bundle to be generated..."
timeout=120
while [ $timeout -gt 0 ]; do
  if kubectl exec "$POD_NAME" -n "${NAMESPACE}" -- test -f /jwt-data/demo-token.jwt 2>/dev/null && \
     kubectl exec "$POD_NAME" -n "${NAMESPACE}" -- test -f /ca-data/ca-bundle.crt 2>/dev/null; then
    echo "✅ Demo data is ready"
    break
  fi
  echo "⏳ Waiting for demo data generation... ($timeout seconds remaining)"
  sleep 5
  timeout=$((timeout - 5))
done

if [ $timeout -le 0 ]; then
  echo "❌ Timeout waiting for demo data generation"
  exit 1
fi

# Extract the data directly
echo "🔑 Extracting JWT token and CA bundle..."
JWT_TOKEN=$(kubectl exec "$POD_NAME" -n "${NAMESPACE}" -c vibectl-server -- cat /jwt-data/demo-token.jwt | tr -d '\n\r')
CA_BUNDLE=$(kubectl exec "$POD_NAME" -n "${NAMESPACE}" -c vibectl-server -- cat /ca-data/ca-bundle.crt)

echo "✅ Demo data extracted successfully!"

echo ""
echo "🔑 Step 5: Setting up demo credentials..."
echo "========================================"

# Save CA bundle to a temporary file for client use
CA_BUNDLE_FILE="/tmp/vibectl-demo-ca-bundle.crt"
echo "$CA_BUNDLE" > "$CA_BUNDLE_FILE"
echo "📁 CA bundle saved to: $CA_BUNDLE_FILE"

# Save JWT token to a temporary file for client use (more secure than embedding in URL)
JWT_TOKEN_FILE="/tmp/vibectl-demo-token.jwt"
echo "$JWT_TOKEN" > "$JWT_TOKEN_FILE"
echo "📁 JWT token saved to: $JWT_TOKEN_FILE"

# Display the extracted credentials
echo ""
echo "📋 Demo Credentials:"
echo "==================="
echo "🔑 JWT Token: ${JWT_TOKEN:0:20}..."
echo "📜 CA Bundle: $(echo "$CA_BUNDLE" | wc -l) lines"

echo ""
echo "🔑 Step 6: Getting node access information..."
echo "============================================="

# Use the node IP that was already discovered in Step 2
# NODE_IP was already set during ConfigMap creation
NODE_PORT=$(kubectl get service vibectl-server -n "${NAMESPACE}" -o jsonpath='{.spec.ports[0].nodePort}')

echo "📍 Node IP: $NODE_IP (using IP from certificate generation)"
echo "🔌 Node Port: $NODE_PORT"
echo "🌐 External URL: vibectl-server://$NODE_IP:$NODE_PORT"

echo ""
echo "⚙️  Step 7: Configuring vibectl proxy with CA bundle..."
echo "======================================================="
echo "   (Using production TLS with CA certificate verification)"

echo "📝 Saving proxy configuration..."
vibectl setup-proxy configure "demo-ca" "vibectl-server://$NODE_IP:$NODE_PORT" \
    --jwt-path "$JWT_TOKEN_FILE" \
    --ca-bundle "$CA_BUNDLE_FILE" \
    --enable-sanitization \
    --enable-audit-logging \
    --activate

echo "✅ Proxy configuration saved with CA bundle"

echo ""
echo "🧪 Step 8: Testing secure connection..."
echo "========================================"
echo "Testing connection with proper certificate verification..."

if vibectl setup-proxy test; then
    echo ""
    echo "🎉 Demo Complete!"
    echo "==============================="
    echo ""
    echo "📋 Technical Summary:"
    echo "   • Server endpoint: ${NODE_IP}:${NODE_PORT}"
    echo "   • Token: ${JWT_TOKEN}"
    echo "   • CA Bundle: ${CA_BUNDLE_FILE}"
    echo ""
    echo "🧪 Certificate Management:"
    echo "   • View cert info: kubectl exec deploy/vibectl-server -n ${NAMESPACE} -- ls -la /ca-data/"
    echo "   • Check logs: kubectl logs deployment/vibectl-server -n ${NAMESPACE} -c ca-init"
    echo "   • Regenerate: kubectl delete pod -l app=vibectl-server -n ${NAMESPACE}"
else
    echo ""
    echo "❌ Connection test failed. Troubleshooting information:"
    echo ""
    echo "🔍 Check deployment logs:"
    echo "   kubectl logs deploy/vibectl-server -n ${NAMESPACE}"
    echo "   kubectl logs deploy/vibectl-server -n ${NAMESPACE} -c ca-init"
    echo "   kubectl logs deploy/vibectl-server -n ${NAMESPACE} -c jwt-init"
    echo ""
    echo "🔍 Verify certificates in container:"
    echo "   kubectl exec deploy/vibectl-server -n ${NAMESPACE} -- ls -la /ca-data/"
    echo ""
    echo "🔍 Test certificate verification manually:"
    echo "   openssl s_client -connect ${NODE_IP}:${NODE_PORT} -CAfile ${CA_BUNDLE_FILE}"
fi

echo ""
echo "🧹 Cleanup Commands:"
echo "==================="
echo "To clean up this demo environment, run:"
echo "   kubectl delete namespace ${NAMESPACE}"
echo "   rm -f ${CA_BUNDLE_FILE} ${JWT_TOKEN_FILE}"
echo ""
echo "🏁 Demo complete!"
