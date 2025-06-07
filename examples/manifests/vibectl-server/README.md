# vibectl-server Demo Manifests

This directory contains a minimal Kubernetes deployment for the `vibectl-server`.
It demonstrates both **JWT authentication** and **TLS secure connections** in a single replica setup.

## Contents

- `configmap.yaml` – server configuration with TLS and JWT auth enabled
- `secret.yaml` – JWT secret used for token generation
- `deployment.yaml` – single replica Deployment with automatic certificate generation
- `service.yaml` – NodePort Service exposing the secure gRPC port

## Features Demonstrated

- **JWT Authentication**: Server requires valid JWT tokens for access
- **TLS Security**: All connections are encrypted using automatically generated certificates
- **Self-Signed Certificates**: Perfect for development and demo environments

## Usage

### 1. Deploy the server
```bash
kubectl apply -f examples/manifests/vibectl-server/
```

### 2. Wait for the server to start and generate certificates
```bash
kubectl wait --for=condition=ready pod -l app=vibectl-server --timeout=60s
```

### 3. Generate a client token
```bash
kubectl exec deploy/vibectl-server -- \
  vibectl-server generate-token demo-user --expires-in 30d
```

### 4. Get the node IP and configure vibectl
```bash
# Get a node IP
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')

# Configure vibectl with insecure connection for development (replace TOKEN with the JWT from step 3)
vibectl setup-proxy configure \
  vibectl-server-insecure://TOKEN@${NODE_IP}:30551
```

### 5. Test the secure connection
```bash
# This should work with the insecure proxy (for development with self-signed certs)
vibectl get pods
```

## Important Notes

- **Certificate Security**: This demo uses self-signed certificates suitable for development/testing only
- **Connection Security**: The demo uses `vibectl-server-insecure://` for development with self-signed certificates
- **Production Usage**: For production deployments, use `vibectl-server://` with proper CA-signed certificates
- **Token Security**: The JWT secret is stored in a Kubernetes secret but uses a simple example value
- **Network Access**: The service uses NodePort (30551) for easy access from outside the cluster

## Production Alternative

For production-grade TLS with certificate verification, use the CA management demo:

```bash
./examples/manifests/vibectl-server/demo.sh
```

This demonstrates:
- Private Certificate Authority setup
- Proper certificate verification with CA bundles
- Production-ready TLS configuration

## Troubleshooting

### Check server logs
```bash
kubectl logs deploy/vibectl-server
```

### Verify TLS certificates were generated
```bash
kubectl exec deploy/vibectl-server -- ls -la /etc/vibectl/certs/
```

### Test token generation
```bash
kubectl exec deploy/vibectl-server -- \
  vibectl-server generate-token test-user --expires-in 1h
```

Replace `TOKEN` with the JWT returned in step 3 and ensure `NODE_IP` points to a reachable
node address. Once configured, vibectl will use the proxy for all LLM requests.
