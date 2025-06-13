#!/usr/bin/env bash
set -euo pipefail

echo "🔰 vibectl-server Demo: JWT Auth + ACME + TLS-ALPN-01 [EXPERIMENTAL]"
echo "=================================================================="
echo ""
echo "This demo showcases ACME certificate provisioning using TLS-ALPN-01 challenges"
echo "with a Pebble ACME test server. This approach provides automatic certificate"
echo "management compatible with Let's Encrypt for production deployments."
echo ""
echo "⚠️  NOTE: TLS-ALPN-01 implementation is experimental and demonstrates the"
echo "    architecture. For production use, HTTP-01 or DNS-01 challenges are"
echo "    recommended until TLS-ALPN-01 is fully integrated."
echo ""

# Check that we're in the project root
if [[ ! -f "pyproject.toml" || ! -d "vibectl" ]]; then
    echo "❌ Error: Please run this script from the project root:"
    echo "   ./examples/manifests/vibectl-server/demo-acme.sh"
    echo ""
    echo "Current directory: $(pwd)"
    exit 1
fi

PROJECT_ROOT="."
MANIFESTS_DIR="examples/manifests/vibectl-server"
IMAGE_NAME="vibectl-server:local"
NAMESPACE="vibectl-server-acme"

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
echo "📦 Step 2: Creating namespace and deploying Pebble ACME server..."
echo "=================================================================="
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# ----------------------------------------------------------------------------
# MetalLB prerequisite check (fail fast if not present)
# ----------------------------------------------------------------------------
if ! kubectl get ns metallb-system >/dev/null 2>&1; then
    cat <<EOF
❌ MetalLB not detected in the cluster.

This demo relies on a LoadBalancer Service (port 443) for ACME validation.

Quick single-node install (layer-2 mode):

  kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/v0.13.12/config/manifests/metallb-native.yaml

Then apply the demo address-pool (adjust the address range for your LAN):

  kubectl apply -f ${MANIFESTS_DIR}/metallb-demo.yaml

The external service already carries the annotation

  metallb.universe.tf/address-pool: vibectl-demo-pool

so MetalLB will assign it an IP from that pool only.

After the install, **wait for the controller webhook to become Ready**:

  kubectl -n metallb-system rollout status deployment/controller --timeout=120s

Then apply the demo address-pool (adjust the address range for your LAN):

  kubectl apply -f ${MANIFESTS_DIR}/metallb-demo.yaml

The external service already carries the annotation:

  metallb.universe.tf/address-pool: vibectl-demo-pool

so MetalLB will assign it an IP from that pool only.

If the pool creation fails with a *webhook unavailable* error, the controller
is not ready yet—just wait for it to finish starting and re-apply the manifest.

To uninstall MetalLB afterwards:

  kubectl delete -f https://raw.githubusercontent.com/metallb/metallb/v0.13.12/config/manifests/metallb-native.yaml
  kubectl delete -f ${MANIFESTS_DIR}/metallb-demo.yaml

EOF
    exit 1
fi

# Discover the node IP and get a predictable service IP range for certificate generation
echo "🔍 Discovering node IP for certificate generation..."
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
echo "📍 Node IP: $NODE_IP"

# Use Kubernetes service DNS name for ACME validation (resolvable within cluster)
ACME_DOMAIN="vibectl-server.${NAMESPACE}.svc.cluster.local"
echo "🌐 Using cluster DNS domain: $ACME_DOMAIN"

# External domain that resolves to the node IP using nip.io
EXTERNAL_DOMAIN="$(echo $NODE_IP | tr '.' '-')".nip.io

# Create a ConfigMap with network info for Pebble certificate generation
echo "🔧 Creating Pebble network-info ConfigMap..."
kubectl create configmap pebble-network-info \
  --from-literal=namespace="${NAMESPACE}" \
  --from-literal=node-ip="$NODE_IP" \
  --from-literal=acme-domain="$ACME_DOMAIN" \
  -n "${NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "🚀 Deploying Pebble ACME test server..."
kubectl apply -n "${NAMESPACE}" -f "${MANIFESTS_DIR}/pebble.yaml"

echo "⏳ Waiting for Pebble ACME server to be ready..."
kubectl wait --for=condition=available deployment/pebble -n "${NAMESPACE}" --timeout=120s
kubectl wait --for=condition=Ready pod -l app=pebble -n "${NAMESPACE}" --timeout=120s

# Get Pebble service details - use DNS name instead of IP for certificate validation
echo "🔍 Getting Pebble service information..."
PEBBLE_SERVICE_PORT=$(kubectl get service pebble -n "${NAMESPACE}" -o jsonpath='{.spec.ports[0].port}')
PEBBLE_SERVICE_IP=$(kubectl get service pebble -n "${NAMESPACE}" -o jsonpath='{.spec.clusterIP}')
PEBBLE_URL="https://pebble.${NAMESPACE}.svc.cluster.local:${PEBBLE_SERVICE_PORT}/dir"

echo "✅ Pebble ACME server ready"
echo "📍 Pebble URL (DNS): ${PEBBLE_URL}"
echo "📍 Pebble IP: ${PEBBLE_SERVICE_IP}:${PEBBLE_SERVICE_PORT}"
echo "🔐 Certificate includes SANs for both DNS name and IP address"

# Extract the dynamic CA certificate from Pebble and update the ConfigMap
echo ""
echo "🔍 Extracting Pebble CA certificate..."
PEBBLE_CA_CERT=$(kubectl exec -n "${NAMESPACE}" deployment/pebble -- cat /certs/ca.crt)

echo "🔧 Updating Pebble CA ConfigMap with dynamic certificate..."
kubectl create configmap pebble-ca-cert \
  --from-literal=ca.crt="$PEBBLE_CA_CERT" \
  -n "${NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "✅ Pebble CA certificate updated in ConfigMap"

# Show the generated certificate details for verification
echo ""
echo "🔍 Verifying Pebble certificate SANs..."
echo "   (Will verify after vibectl-server starts and has access to certificates)"

echo ""
echo "📦 Step 3: Creating ACME configuration and deploying vibectl-server..."
echo "====================================================================="

echo "🚀 Deploying vibectl-server services (ClusterIP + NodePort)..."
kubectl apply -n "${NAMESPACE}" -f "${MANIFESTS_DIR}/service-acme.yaml"

# Wait for the external IP of the LoadBalancer service
echo "⏳ Waiting for LoadBalancer external IP..."
LB_IP=""
timeout=120
while [ $timeout -gt 0 ]; do
  LB_IP=$(kubectl get svc vibectl-server-external -n "${NAMESPACE}" -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)
  if [ -n "$LB_IP" ]; then
    echo "✅ LoadBalancer IP: $LB_IP"
    break
  fi
  echo "⏳ Waiting for LoadBalancer IP... ($timeout seconds remaining)"
  sleep 5
  timeout=$((timeout - 5))
done

if [ -z "$LB_IP" ]; then
  echo "❌ Timeout waiting for LoadBalancer IP"
  exit 1
fi

# External domain derived from LoadBalancer IP
EXTERNAL_DOMAIN="$(echo $LB_IP | tr '.' '-')".nip.io

# Create ACME configuration ConfigMap with the dynamic Pebble URL and domains
echo "🔧 Creating ACME configuration..."
kubectl create configmap vibectl-server-acme-config \
  --from-literal=directory-url="$PEBBLE_URL" \
  --from-literal=acme-domain-internal="$ACME_DOMAIN" \
  --from-literal=acme-domain-external="$EXTERNAL_DOMAIN" \
  -n "${NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "🚀 Deploying vibectl-server with ACME..."
kubectl apply -n "${NAMESPACE}" -f "${MANIFESTS_DIR}/jwt-secret.yaml"
kubectl apply -n "${NAMESPACE}" -f "${MANIFESTS_DIR}/configmap-acme.yaml"
# Note: pebble-ca-cert ConfigMap is created dynamically after Pebble starts
kubectl apply -n "${NAMESPACE}" -f "${MANIFESTS_DIR}/deployment-acme.yaml"

echo "✅ All manifests deployed successfully!"

echo ""
echo "⏳ Step 4: Waiting for ACME certificate provisioning..."
echo "======================================================"
echo "The server will:"
echo "  🏭 Start with temporary self-signed certificates"
echo "  🔰 Request ACME certificate via TLS-ALPN-01 challenge"
echo "  🔑 Generate JWT demo token"
echo ""

# Wait for deployment to be ready (this includes init containers completing)
echo "⏳ Waiting for vibectl-server deployment to be ready..."
kubectl wait --for=condition=available deployment/vibectl-server -n "${NAMESPACE}" --timeout=300s

echo "✅ Deployment ready! Now waiting for ACME certificate provisioning..."

# Wait for the main deployment to be ready
echo "⏳ Waiting for vibectl-server pod to be running..."
kubectl wait --for=condition=Ready pod -l app=vibectl-server -n "${NAMESPACE}" --timeout=300s

# Get the pod name
POD_NAME=$(kubectl get pod -l app=vibectl-server -n "${NAMESPACE}" -o jsonpath='{.items[0].metadata.name}')
echo "📦 Found pod: $POD_NAME"

# Wait for JWT token to be generated
echo "⏳ Waiting for JWT token to be generated..."
timeout=120
while [ $timeout -gt 0 ]; do
  if kubectl exec "$POD_NAME" -n "${NAMESPACE}" -- test -f /jwt-data/demo-token.jwt 2>/dev/null; then
    echo "✅ JWT token is ready"
    break
  fi
  echo "⏳ Waiting for JWT token generation... ($timeout seconds remaining)"
  sleep 5
  timeout=$((timeout - 5))
done

if [ $timeout -le 0 ]; then
  echo "❌ Timeout waiting for JWT token generation"
  exit 1
fi

# Extract the JWT token
echo "🔑 Extracting JWT token..."
JWT_TOKEN=$(kubectl exec "$POD_NAME" -n "${NAMESPACE}" -c vibectl-server -- cat /jwt-data/demo-token.jwt)

echo "✅ Demo data extracted successfully!"

echo ""
echo "🔍 Step 5: Waiting for ACME certificate provisioning..."
echo "======================================================="
echo "⏳ Waiting for ACME certificate to be provisioned..."

# Wait for ACME certificate to be provisioned
timeout=300
while [ $timeout -gt 0 ]; do
  if kubectl exec "$POD_NAME" -n "${NAMESPACE}" -c vibectl-server -- sh -c 'ls /root/.config/vibectl/server/acme-certs/*.crt 2>/dev/null' >/dev/null 2>&1; then
    echo "✅ ACME certificate provisioned successfully!"
    break
  fi
  echo "⏳ Waiting for ACME certificate provisioning... ($timeout seconds remaining)"
  sleep 10
  timeout=$((timeout - 10))
done

if [ $timeout -le 0 ]; then
  echo "❌ Timeout waiting for ACME certificate provisioning"
  echo "🔍 Check vibectl-server logs for ACME errors:"
  kubectl logs "$POD_NAME" -n "${NAMESPACE}" -c vibectl-server --tail=20
  exit 1
fi

echo ""
echo "🔍 Step 5b: Verifying ACME certificate details..."
echo "================================================"
echo "🔍 Checking ACME certificate SANs and chain..."
kubectl exec "$POD_NAME" -n "${NAMESPACE}" -c vibectl-server -- sh -c '
  CERT_FILE=$(ls /root/.config/vibectl/server/acme-certs/*.crt 2>/dev/null | head -n 1)
  if [ -n "$CERT_FILE" ]; then
    echo "📋 Certificate Subject Alternative Names:"
    openssl x509 -in "$CERT_FILE" -text -noout | grep -A 5 "Subject Alternative Name" || echo "   No SANs found"
    echo ""
    echo "📋 Certificate chain summary:"
    openssl crl2pkcs7 -nocrl -certfile "$CERT_FILE" | openssl pkcs7 -print_certs -noout
  else
    echo "⚠️  ACME certificate not found"
    exit 1
  fi
'

echo ""
echo "🔑 Step 6: Setting up demo credentials..."
echo "========================================"

# Extract the intermediate CA certificate from the ACME certificate chain for client use
# The server certificate was issued by an intermediate CA, so we need that CA for verification
CA_BUNDLE_FILE="/tmp/vibectl-demo-pebble-ca.crt"
echo "🔍 Extracting intermediate CA certificate from ACME certificate chain..."

# Extract the intermediate CA certificate inside the vibectl-server container
# The certificate chain order is: [Server Cert] -> [Intermediate CA] -> [Root CA]
# We capture the *second* certificate (the intermediate CA) and stream it back
kubectl exec "$POD_NAME" -n "${NAMESPACE}" -c vibectl-server -- sh -c '
  CERT_FILE=$(ls /root/.config/vibectl/server/acme-certs/*.crt 2>/dev/null | head -n 1)
  if [ -z "$CERT_FILE" ]; then
    echo "❌ No ACME certificate found"
    exit 1
  fi

  openssl crl2pkcs7 -nocrl -certfile "$CERT_FILE" \
    | openssl pkcs7 -print_certs \
    | awk "
        /-----BEGIN CERTIFICATE-----/ { count++; capture = (count==2) }
        capture { print }
        /-----END CERTIFICATE-----/ && capture { capture = 0 }
        END {
          if (count < 2) {
            print \"❌ No intermediate CA found in certificate chain\" > "/dev/stderr";
            exit 1;
          }
        }"
' > "$CA_BUNDLE_FILE"

if [ $? -eq 0 ] && [ -s "$CA_BUNDLE_FILE" ]; then
  echo "✅ Intermediate CA certificate extracted successfully"
  echo "📁 CA bundle saved to: $CA_BUNDLE_FILE"
else
  echo "❌ Failed to extract intermediate CA certificate"
  echo "🔍 Certificate chain details:"
  kubectl exec "$POD_NAME" -n "${NAMESPACE}" -c vibectl-server -- sh -c '
    CERT_FILE=$(ls /root/.config/vibectl/server/acme-certs/*.crt 2>/dev/null | head -n 1)
    openssl crl2pkcs7 -nocrl -certfile "$CERT_FILE" | openssl pkcs7 -print_certs -noout
  '
  exit 1
fi

echo ""
echo "🔑 Step 7: Getting service access information..."
echo "==============================================="

###############################
#  Step 7: Service information #
###############################

# For external access, use NodePort (clients outside cluster can't resolve internal DNS)
PROXY_HOST="$EXTERNAL_DOMAIN"
PROXY_PORT="443"

echo "🔍 ACME validation uses internal domain: $ACME_DOMAIN"
echo "🌐 Client access uses external domain: $EXTERNAL_DOMAIN"

echo "📍 Proxy Host: $PROXY_HOST"
echo "🔌 Proxy Port: $PROXY_PORT"
echo "🌐 External URL (DNS-based): vibectl-server://$JWT_TOKEN@$PROXY_HOST:$PROXY_PORT"

echo ""
echo "⚙️  Step 8: Configuring vibectl proxy with Pebble CA..."
echo "======================================================="
echo "   (Using Pebble CA certificate for proper TLS verification)"

echo "📝 Saving proxy configuration..."
vibectl setup-proxy configure "vibectl-server://$JWT_TOKEN@$PROXY_HOST:$PROXY_PORT" --ca-bundle "$CA_BUNDLE_FILE" --no-test

echo "✅ Proxy configuration saved with Pebble CA bundle"

echo ""
echo "🧪 Step 9: Testing secure connection..."
echo "========================================"
echo "Testing connection with ACME certificate verification..."

if vibectl setup-proxy test; then
    echo ""
    echo "🎉 ACME Demo Complete!"
    echo "==============================="
    echo ""
    echo "📋 Technical Summary:"
    echo "   • Server endpoint: ${PROXY_HOST}:${PROXY_PORT}"
    echo "   • Token: ${JWT_TOKEN}"
    echo "   • ACME Provider: Pebble (${PEBBLE_URL})"
    echo "   • Challenge Type: TLS-ALPN-01"
    echo "   • Domain: ${ACME_DOMAIN} (cluster DNS)"
    echo "   • Email: admin@vibectl.test (hard-coded in config)"
    echo ""
    echo "🔰 ACME Features Demonstrated:"
    echo "   • Automatic certificate provisioning via TLS-ALPN-01"
    echo "   • Integration with Pebble ACME test server"
    echo "   • Single-port operation (443) for both gRPC and ACME challenges"
    echo "   • Production-ready ACME workflow (compatible with Let's Encrypt)"
    echo "   • Simplified configuration with hard-coded demo values"
    echo ""
    echo "🧪 Verification Commands:"
    echo "   • Check logs: kubectl logs deployment/vibectl-server -n ${NAMESPACE}"
    echo "   • Pebble status: kubectl logs deployment/pebble -n ${NAMESPACE}"
    echo "   • Test connection: vibectl setup-proxy test"
else
    echo ""
    echo "❌ Connection test failed. Troubleshooting information:"
    echo ""
    echo "🔍 Check deployment logs:"
    echo "   kubectl logs deploy/vibectl-server -n ${NAMESPACE}"
    echo "   kubectl logs deploy/vibectl-server -n ${NAMESPACE} -c config-init"
    echo "   kubectl logs deploy/vibectl-server -n ${NAMESPACE} -c jwt-init"
    echo ""
    echo "🔍 Check Pebble ACME server:"
    echo "   kubectl logs deploy/pebble -n ${NAMESPACE}"
    echo ""
    echo "🔍 Check ACME certificate provisioning:"
    echo "   kubectl exec deploy/vibectl-server -n ${NAMESPACE} -- ls -la /root/.config/vibectl/server/certs/"
    echo ""
    echo "🔍 Manual connection test:"
    echo "   # Test ACME server connectivity"
    echo "   curl -k ${PEBBLE_URL}"
    echo ""
    echo "   # Test vibectl-server gRPC port"
    echo "   telnet ${NODE_IP} ${NODE_PORT}"
fi

echo ""
echo "🧹 Cleanup Commands:"
echo "==================="
echo "To clean up this demo environment, run:"
echo "   kubectl delete namespace ${NAMESPACE}"
echo "   rm -f ${CA_BUNDLE_FILE}"
echo ""
echo "🏁 ACME Demo complete!"
