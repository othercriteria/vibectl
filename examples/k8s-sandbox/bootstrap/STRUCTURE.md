# Vibectl Bootstrap Demo Structure

This directory contains a bootstrap demo showcasing vibectl's capabilities using a self-contained Kubernetes environment with Ollama as the LLM provider.

## Key Files

- `run.sh`: Main entry script that sets up the Docker environment and runs the entire demo
  - Detects Docker GID
  - Configures environment variables
  - Handles source vs. stable installation options
  - Starts the container
  - Waits for container to become healthy
  - Runs demonstration commands
  - Provides summary output
- `bootstrap-entrypoint.sh`: Script executed inside the container to initialize Kind and Ollama environment
  - Installs vibectl (from source or stable packages)
  - Creates Kind cluster
  - Deploys Ollama
  - Configures vibectl
  - Uses port-forwarding for Ollama API access
  - Sets up the status monitoring system
- `compose.yml`: Docker Compose configuration defining the bootstrap container
  - Configures volumes and environment variables
  - Sets up health checks
  - Mounts local repository code for source installation
- `Dockerfile`: Container definition for the bootstrap environment
- `README.md`: User documentation for the bootstrap demo
- `STRUCTURE.md`: This file, documenting component structure
- `cleanup.sh`: Script to clean up resources when done

## Directories

- `k8s/`: Kubernetes manifests for the bootstrap environment
  - `ollama-deployment.yaml`: Ollama deployment configuration
  - `ollama-service.yaml`: Service for Ollama API (ClusterIP)
  - `ollama-pvc.yaml`: Persistent volume claim for Ollama models
  - `ollama-namespace.yaml`: Namespace definition for Ollama
  - `kind-config.yaml`: Kind cluster configuration

## Architecture

The bootstrap demo operates as a single container in an isolated Docker network:

1. **Bootstrap Container**: Creates a Kind Kubernetes cluster and sets up Ollama
   - Runs Kind with a minimal cluster configuration
   - Deploys Ollama with a smaller LLM model
   - Configures vibectl to use the Ollama instance
   - Uses kubectl port-forward to access Ollama API
   - Uses health checks to verify component readiness

2. **Demo Automation**: The `run.sh` script handles the entire demo lifecycle
   - Starts the container with appropriate configuration
   - Waits for all components to initialize
   - Executes demonstration commands against the running environment
   - Provides a summary of what was demonstrated

3. **Installation Options**:
   - **Source Installation**: Installs vibectl directly from the mounted repository (default)
   - **Stable Installation**: Installs vibectl from PyPI with specific versions (optional)

## Implementation Details

### Kind Cluster

- Minimal Kubernetes cluster with a single node
- Resource limits to ensure it runs on most systems
- Health checks to verify cluster readiness

### Ollama Deployment

- Runs as a Kubernetes Deployment in the "ollama" namespace
- Uses persistent storage for model files
- Exposed via ClusterIP service
- Accessed via kubectl port-forward from bootstrap-entrypoint.sh
- Configured with a smaller model for faster startup
- Health checks ensure model is loaded and ready

### Vibectl Configuration

- Vibectl installed in the container environment (source or stable)
- Configured to use the Ollama instance via port-forward
- Environment setup for proper vibectl operation
- Verification steps ensure vibectl can connect to Ollama

### Demonstration Flow

The demo showcases several vibectl capabilities in a single automated flow:

1. **Environment Verification**: Ensures all components are working correctly
2. **Basic LLM Functionality**: Verifies vibectl can communicate with Ollama
3. **Kubernetes Analysis**: Uses vibectl to analyze the Ollama deployment
4. **Improvement Suggestions**: Shows how vibectl can suggest improvements to the deployment

## Interface with Main Project

This demo showcases vibectl's capabilities by:

- Providing a self-contained environment that requires minimal setup
- Demonstrating how vibectl can work with local LLMs like Ollama
- Showing how vibectl can analyze and improve Kubernetes deployments
- Supporting both source installation and stable package installation

## Configuration

The bootstrap demo can be configured with the following environment variables:

- `OLLAMA_MODEL`: Model to use for Ollama (defaults to tinyllama)
- `DOCKER_GID`: Docker group ID for socket access (auto-detected)
- `KIND_CLUSTER_NAME`: Name for the Kind cluster (defaults to bootstrap-cluster)
- `RESOURCE_LIMIT_CPU`: CPU limit for Ollama container (defaults to "2")
- `RESOURCE_LIMIT_MEMORY`: Memory limit for Ollama container (defaults to "4Gi")
- `USE_STABLE_VERSIONS`: Whether to use stable PyPI versions (defaults to "false")
- `VIBECTL_VERSION`: Version of vibectl to install when using stable versions (defaults to "0.5.0")
- `LLM_VERSION`: Version of LLM to install when using stable versions (defaults to "0.24.2")
