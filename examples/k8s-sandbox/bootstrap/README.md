# Vibectl Kubernetes Analysis Demo

This demo creates a self-contained environment with Ollama as an LLM backend for vibectl and demonstrates Kubernetes analysis capabilities using example manifests.

## Components

- **Docker**: Used to run the demo container
- **K3d**: Lightweight Kubernetes deployment
- **Helm**: Package manager for Kubernetes
- **Ollama**: LLM service for vibectl (installed via Helm chart)
- **Vibectl**: CLI tool for analyzing Kubernetes resources using AI

## How it Works

1. The `run.sh` script builds and starts a Docker container with all necessary tools
2. Inside the container, `bootstrap-entrypoint.sh`:
   - Installs vibectl and its dependencies
   - Creates a K3d Kubernetes cluster
   - Deploys Ollama using the [ollama-helm](https://github.com/otwld/ollama-helm) chart
   - Downloads and configures the requested LLM model
   - Creates example Kubernetes manifests
   - Configures vibectl to use the Ollama LLM

3. After setup, a series of demonstration commands run to showcase vibectl's capabilities

## Usage

### Starting the Demo

```bash
# Run with defaults (uses tinyllama model)
./run.sh

# Use PyPI-released versions instead of source code
./run.sh --use-stable-versions

# Change the model (if you have a more powerful system)
OLLAMA_MODEL=llama2 ./run.sh

# Adjust resource limits
RESOURCE_LIMIT_CPU=4 RESOURCE_LIMIT_MEMORY=8Gi ./run.sh
```

### Interacting with the Demo

Once the demo is running, you can interact with it:

```bash
# Run vibectl commands
docker exec -it vibectl-k3d-demo vibectl vibe "How can I optimize my Kubernetes deployments?"

# View the example Kubernetes manifest
docker exec -it vibectl-k3d-demo cat /home/bootstrap/example-deployment.yaml

# Analyze the example manifest with vibectl
docker exec -it vibectl-k3d-demo vibectl describe vibe "analyze this deployment" -f /home/bootstrap/example-deployment.yaml

# Suggest improvements to the deployment
docker exec -it vibectl-k3d-demo vibectl vibe "suggest improvements to this deployment" -f /home/bootstrap/example-deployment.yaml

# Access the container shell
docker exec -it vibectl-k3d-demo bash
```

### Cleaning Up

```bash
# Remove only the status volume (no effect on Ollama model persistence)
./cleanup.sh
```

## Requirements

- Docker
- At least 5GB RAM (more recommended for better LLM performance)
- Docker Compose

## Customization

You can customize the demo with environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| OLLAMA_MODEL | tinyllama | Model to use (e.g., llama2, tinyllama). Use the alias from `llm models`. |
| RESOURCE_LIMIT_CPU | 2 | CPU limit for Ollama (may not be enforced; see below) |
| RESOURCE_LIMIT_MEMORY | 4Gi | Memory limit for Ollama (may not be enforced; see below) |
| USE_STABLE_VERSIONS | false | Use stable versions from PyPI instead of source |
| VIBECTL_VERSION | 0.5.0 | Version of vibectl to install when using stable versions |
| LLM_VERSION | 0.24.2 | Version of LLM to install when using stable versions |

**Notes:**
- Ollama model downloads are ephemeral and tied to the k3d cluster lifecycle. Models will be re-downloaded each time the cluster is recreated. Persistent model storage is not supported in this demo setup.
- Ollama pod resource limits (CPU/memory) may not be enforced due to Helm chart or upstream Ollama limitations. See https://github.com/otwld/ollama-helm for details.

## Troubleshooting

- **Container fails to start**: Check Docker has sufficient resources (5GB+ RAM recommended)
- **Ollama doesn't initialize**: Check logs with `docker logs vibectl-k3d-demo`
- **Model download timeout**: For larger models, increase timeout in bootstrap-entrypoint.sh
- **Out of memory errors**: Reduce memory requirements with `RESOURCE_LIMIT_MEMORY=2Gi ./run.sh`
- **Source install fails**: Try using stable versions with `./run.sh --use-stable-versions`
- **High CPU usage**: LLM generation may use all available CPU cores for best performance. If you want to restrict usage, set Docker resource limits or adjust the k8s pod spec (note: Ollama pod limits may not be enforced).

## Architecture

The demo creates a Docker container that:
- Uses K3d to create a lightweight Kubernetes cluster
- Runs Ollama within the Kubernetes cluster
- Installs and configures vibectl
- Creates example Kubernetes manifests for analysis
- Demonstrates vibectl's AI-powered analysis capabilities

This provides a self-contained environment for exploring vibectl's capabilities without requiring an external Kubernetes cluster.

## Contributing

Contributions to improve the demo are welcome! Please:

1. Create an issue describing your proposed change
2. Submit a PR referencing the issue

## Notes

- The `run.sh` script generates a temporary Compose file for each run. Do not edit it directly; use environment variables or script arguments to customize the demo.

# Change the model (if you have a more powerful system)
OLLAMA_MODEL=llama2 ./run.sh

# ⚠️ Model string should be a providerless alias (e.g., 'tinyllama') for best compatibility. See `llm models` for available aliases.

# Adjust resource limits
RESOURCE_LIMIT_CPU=4 RESOURCE_LIMIT_MEMORY=8Gi ./run.sh
