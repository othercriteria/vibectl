# vibectl-server ACME Example Manifests

This directory contains a minimal setup to test the LLM proxy server with TLS certificates issued by `cert-manager` using a local Pebble ACME server.

## Files

- `pebble.yaml` – Deploys a Pebble ACME server and supporting resources.
- `cluster-issuer.yaml` – Creates a `ClusterIssuer` that points cert-manager at the Pebble instance.
- `deployment-tls.yaml` – Deploys the vibectl server with a `Certificate` resource so cert-manager automatically provisions TLS.

## Usage Workflow

1. **Deploy ACME infrastructure**

   ```bash
   kubectl apply -f examples/manifests/vibectl-server/pebble.yaml
   kubectl apply -f examples/manifests/vibectl-server/cluster-issuer.yaml
   ```

2. **Deploy vibectl-server**

   ```bash
   kubectl apply -f examples/manifests/vibectl-server/deployment-tls.yaml
   kubectl wait --for=condition=available deployment/vibectl-server -n vibectl-demo
   ```

3. **Verify TLS certificate**

   ```bash
   openssl s_client -connect vibectl-server.vibectl-demo.svc.cluster.local:443
   ```

Successful connection confirms the ACME workflow and TLS setup are functioning.
