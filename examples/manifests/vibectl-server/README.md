# vibectl-server Kubernetes Demos

This directory contains comprehensive demonstration setups for `vibectl-server` deployment in Kubernetes, showcasing different certificate management approaches suitable for various deployment scenarios.

## Available Demos

### 1. CA Management Demo (`demo-ca.sh`)

**Purpose**: Demonstrates vibectl-server with **private Certificate Authority (CA)** management.

**Use Case**: 
- **Production internal networks** where you control certificate trust
- **Air-gapped environments** without internet access
- **Corporate environments** with existing PKI infrastructure
- **Local development** with full certificate control

**Features**:
- 🏭 **Private CA Generation**: Creates a custom Certificate Authority
- 🔐 **Server Certificate Issuance**: Generates TLS certificates signed by the private CA
- 🔑 **JWT Authentication**: Secure API access with JSON Web Tokens
- 📦 **Self-contained**: No external dependencies or internet access required
- 🧪 **Certificate Management**: Complete lifecycle including renewal workflows

**Namespace**: `vibectl-server-ca`

**Quick Start**:
```bash
# From project root
./examples/manifests/vibectl-server/demo-ca.sh
```

### 2. ACME Management Demo (`demo-acme.sh`)

**Purpose**: Demonstrates vibectl-server with **ACME certificate management** using TLS-ALPN-01 challenges and Pebble test server.

**Use Case**:
- **Production internet-facing deployments** with Let's Encrypt
- **Automatic certificate renewal** workflows
- **Testing ACME integration** before production deployment
- **Simplified certificate management** without HTTP infrastructure

**Features**:
- 🔰 **Pebble ACME Server**: Local Let's Encrypt-compatible test server
- 🔄 **TLS-ALPN-01 Challenges**: Secure domain validation directly on the gRPC port
- ✨ **Simplified Deployment**: Single container (no nginx sidecar required)
- 🔐 **Enhanced Security**: No HTTP port exposure required
- 🔄 **Certificate Renewal**: Infrastructure for automatic certificate updates
- 🧪 **ACME Integration Testing**: Complete ACME client workflow validation

**Namespace**: `vibectl-server-acme`

**Quick Start**:
```bash
# From project root
./examples/manifests/vibectl-server/demo-acme.sh
```

## Comparison Matrix

| Feature | CA Demo | ACME Demo |
|---------|---------|-----------|
| **Certificate Source** | Private CA | ACME Server (Pebble/Let's Encrypt) |
| **Internet Dependency** | None | Required for real Let's Encrypt |
| **Trust Model** | Custom CA bundle | Public/ACME CA |
| **Renewal** | Manual regeneration | Automatic ACME renewal |
| **Challenge Method** | N/A | TLS-ALPN-01 (secure, direct) |
| **Deployment Complexity** | Medium | Low (single container) |
| **HTTP Port Required** | No | No (TLS-ALPN-01 advantage) |
| **Best For** | Internal/Private networks | Public internet deployments |
| **Security Model** | Trust custom CA | Trust public CA |

## TLS-ALPN-01 Advantages

The ACME demo uses **TLS-ALPN-01** challenges instead of the traditional HTTP-01 approach, providing significant benefits:

✅ **Simplified Architecture**: Single container deployment without nginx sidecar  
✅ **Enhanced Security**: No HTTP port (80) exposure required  
✅ **Direct Challenge Handling**: Challenges processed on the main gRPC port  
✅ **Reduced Resource Usage**: Fewer containers, volumes, and configurations  
✅ **Automatic Management**: Challenge handling integrated into the main server process  

## Parallel Operation

Both demos can run simultaneously:

- **CA Demo**: Uses namespace `vibectl-server-ca` on ports 30443/30080
- **ACME Demo**: Uses namespace `vibectl-server-acme` on port 30443

The demos share the same NodePort numbers but operate in different namespaces, so they won't conflict if run on different clusters or at different times.

## Technical Details

### Common Infrastructure

Both demos share:
- **Docker Image Building**: Consistent `vibectl-server:local` image
- **Multi-cluster Support**: Auto-detection for kind, k3s, minikube, Docker Desktop
- **JWT Authentication**: Secure API access with configurable tokens
- **Health Monitoring**: Readiness and liveness probes
- **Volume Management**: Persistent certificate and key storage

### CA Demo Specifics

```yaml
# Certificate generation flow
ca-init container:
  1. Generate root CA private key
  2. Create CA certificate
  3. Generate server private key  
  4. Create certificate signing request (CSR)
  5. Sign server certificate with CA
  6. Bundle certificates for client verification
```

### ACME Demo Specifics (TLS-ALPN-01)

```yaml
# ACME certificate acquisition flow
acme-init container:
  1. Connect to Pebble ACME server
  2. Create ACME account
  3. Request domain validation
  4. Complete TLS-ALPN-01 challenge (directly on gRPC port)
  5. Acquire signed certificate
  6. Store certificate for server use
  
# Single container deployment:
vibectl-server container:
  - Handles gRPC API requests
  - Processes TLS-ALPN-01 challenges automatically
  - No separate HTTP server needed
  - Simplified volume and networking configuration
  
# Pebble ACME server provides:
pebble service:
  - ACME directory at https://pebble:14000/dir
  - TLS-ALPN-01 challenge validation
  - Certificate issuance simulation
  - Let's Encrypt protocol compatibility
```

## Cleanup

Each demo provides its own cleanup commands:

```bash
# Clean up CA demo
kubectl delete namespace vibectl-server-ca
rm -f /tmp/vibectl-demo-ca-bundle.crt

# Clean up ACME demo  
kubectl delete namespace vibectl-server-acme
rm -f /tmp/vibectl-demo-acme-cert.pem
```

## Troubleshooting

### Common Issues

1. **Image Loading Failures**
   ```bash
   # Verify cluster type
   kubectl version --short
   kubectl config current-context
   
   # Manual image loading for kind
   kind load docker-image vibectl-server:local
   ```

2. **Certificate Generation Timeouts**
   ```bash
   # Check init container logs
   kubectl logs deploy/vibectl-server -c ca-init    # CA demo
   kubectl logs deploy/vibectl-server -c acme-init  # ACME demo (pebble-ca-init)
   ```

3. **Connection Test Failures**
   ```bash
   # Verify certificate files
   kubectl exec deploy/vibectl-server -- ls -la /ca-data/     # CA demo
   kubectl exec deploy/vibectl-server -- ls -la /root/.config/vibectl/server/certs/   # ACME demo
   
   # Test certificate manually
   openssl s_client -connect NODE_IP:NODE_PORT -CAfile /tmp/cert-file.pem
   ```

### ACME-Specific Issues

1. **Pebble Server Not Ready**
   ```bash
   # Check Pebble deployment
   kubectl logs deploy/pebble -n vibectl-server-acme
   kubectl get svc pebble -n vibectl-server-acme
   ```

2. **TLS-ALPN-01 Challenge Failures**
   ```bash
   # Check server logs for challenge processing
   kubectl logs deploy/vibectl-server -n vibectl-server-acme -c vibectl-server
   
   # Verify TLS configuration
   kubectl port-forward svc/vibectl-server 30443:50051 -n vibectl-server-acme &
   openssl s_client -connect localhost:30443 -alpn acme-tls/1
   ```

## Next Steps

- **Production CA Deployment**: Use `demo-ca.sh` as a template for private networks
- **Let's Encrypt Integration**: Adapt `demo-acme.sh` for real Let's Encrypt servers
- **Certificate Monitoring**: Implement certificate expiration monitoring
- **Automated Renewal**: Set up cron jobs or operators for certificate renewal
- **High Availability**: Deploy multiple replicas with shared certificate storage

## Development

To modify or extend these demos:

1. **Test Changes**: Run demos in clean environments
2. **Validate Certificates**: Verify certificate generation and validation
3. **Check Integration**: Ensure vibectl client compatibility
4. **Document Changes**: Update this README with new features or requirements

## File Structure

The following files make up the vibectl-server Kubernetes demo:

### Core Manifests (CA-based)
- `Dockerfile` - Multi-stage Docker build for vibectl-server
- `jwt-secret.yaml` - JWT signing secret (base64 encoded)
- `configmap.yaml` - Server configuration for CA-based deployment
- `deployment-ca.yaml` - CA-based certificate generation deployment
- `service.yaml` - NodePort service for external access
- `demo-ca.sh` - Demo script for CA-based TLS setup

### ACME Manifests (TLS-ALPN-01)
- `pebble.yaml` - Pebble ACME test server deployment
- `configmap-acme.yaml` - Server configuration for ACME-based deployment
- `deployment-acme.yaml` - ACME-based certificate deployment (TLS-ALPN-01)
- `service-acme.yaml` - NodePort service for ACME deployment
- `demo-acme.sh` - Demo script for ACME-based TLS setup with TLS-ALPN-01

### Shared Components
- `configmap-jwt.yaml` - Shared JWT configuration (planned)
- `README.md` - This documentation file
