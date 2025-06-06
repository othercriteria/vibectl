# vibectl-server Demo Manifests

This directory contains a minimal Kubernetes deployment for the `vibectl-server`.
It is intended for quick local demos or testing with a single replica.

## Contents

- `configmap.yaml` – basic server configuration
- `secret.yaml` – JWT secret used for token generation
- `deployment.yaml` – single replica Deployment
- `service.yaml` – NodePort Service exposing the gRPC port

## Usage

1. Apply the manifests:
   ```bash
   kubectl apply -f examples/manifests/vibect-server/
   ```
2. Generate a client token:
   ```bash
   kubectl exec deploy/vibectl-server -- \
     vibectl-server generate-token demo-user --expires-in 30d
   ```
3. Note the Node IP of your cluster and configure vibectl:
   ```bash
   vibectl setup-proxy configure \
     vibectl-server-insecure://TOKEN@NODE_IP:30551
   ```

Replace `TOKEN` with the JWT returned in step 2 and `NODE_IP` with a reachable
node address. Once configured, you can use vibectl as usual and requests will be
proxied through the deployed server.
