# Vibectl Kubernetes Analysis Demo

This demo creates a self-contained environment with Ollama as an LLM backend for vibectl and demonstrates Kubernetes analysis capabilities using example manifests.

## Components

- **Docker**: Used to run the demo container
- **K3d**: Lightweight Kubernetes deployment
- **Helm**: Package manager for Kubernetes
- **Ollama**: LLM service for vibectl (installed via Helm chart)
- **Vibectl**: CLI tool for analyzing Kubernetes resources using AI

## How it Works

1. The `launch.sh` script builds and starts a Docker container with all necessary tools
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
./launch.sh

# Use PyPI-released versions instead of source code
./launch.sh --use-stable-versions

# Change the model (if you have a more powerful system)
OLLAMA_MODEL=llama2 ./launch.sh

# Adjust resource limits
RESOURCE_LIMIT_CPU=4 RESOURCE_LIMIT_MEMORY=8Gi ./launch.sh
```

After the demo launches, you can run a guided demonstration of vibectl's capabilities:

```bash
./demo-commands.sh
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
# Remove all demo containers, volumes, and the k3d cluster
./cleanup.sh
```

Running `cleanup.sh` will also delete the k3d cluster (`vibectl-demo`), ensuring a fully clean state for the next run. Use this if you want to reset everything, including the Kubernetes environment. The next run will recreate the cluster from scratch.

## Requirements

- Docker
- At least 5GB RAM (more recommended for better LLM performance)
- Docker Compose

## Customization

You can specify any model string for `OLLAMA_MODEL` (including those with dots, colons, underscores, etc.). The demo will automatically register your requested model string as an alias in `llm`, ensuring compatibility regardless of how Ollama or llm normalizes model names. This prevents 'Unknown model' errors due to alias mismatches.

When you launch the demo, the requested model is baked into the Docker image at build time, so it is available immediately when the environment starts. You can bake multiple models into the image by editing the Dockerfile.ollama-model or customizing the build process.

| Variable | Default | Description |
|----------|---------|-------------|
| OLLAMA_MODEL | tinyllama | Default model for vibectl and Helm (must be baked into the image) |
| RESOURCE_LIMIT_CPU | (dynamic) | CPU limit for Ollama; dynamically set to 75% of available CPU cores (minimum 1) unless explicitly specified |
| RESOURCE_LIMIT_MEMORY | 6Gi | Memory limit for Ollama |
| USE_STABLE_VERSIONS | false | Use stable versions from PyPI instead of source |
| VIBECTL_VERSION | 0.5.0 | Version of vibectl to install when using stable versions |
| LLM_VERSION | 0.24.2 | Version of LLM to install when using stable versions |

**Notes:**
- All default values are set directly in `launch.sh`.
- `RESOURCE_LIMIT_CPU` is dynamically determined at runtime as 75% of available CPU cores (minimum 1), unless you explicitly set it. This ensures optimal performance for most systems.
- The demo automatically ensures that your `OLLAMA_MODEL` value is always available as an alias in `llm`, regardless of normalization (dots, dashes, colons, etc.).
- You can check available models and aliases inside the container with `llm models`.
- Temporary Compose files are generated for each run and are ignored by git via `.gitignore`.

## Troubleshooting

- **Container fails to start**: Check Docker has sufficient resources (5GB+ RAM recommended)
- **Ollama doesn't initialize**: Check logs with `docker logs vibectl-k3d-demo`
- **Model download timeout**: For larger models, increase timeout in bootstrap-entrypoint.sh
- **Out of memory errors**: Reduce memory requirements with `RESOURCE_LIMIT_MEMORY=2Gi ./launch.sh`
- **Source install fails**: Try using stable versions with `./launch.sh --use-stable-versions`
- **High CPU usage**: LLM generation may use up to the specified CPU limit for best performance. Adjust RESOURCE_LIMIT_CPU to restrict usage if needed.
- **Unknown model errors**: The demo now automatically registers your requested `OLLAMA_MODEL` as an alias in `llm`. If you still encounter issues, check the logs for aliasing actions and verify with `llm models` inside the container.

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

- The `launch.sh` script generates a temporary Compose file for each run. Do not edit it directly; use environment variables or script arguments to customize the demo.
- The `demo-commands.sh` script provides a guided demonstration of vibectl's capabilities. Run it after launching the demo for a quick tour.
