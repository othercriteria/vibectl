# Kubernetes CTF Sandbox Structure

This directory contains a Capture The Flag (CTF) style sandbox environment for testing vibectl's autonomous mode capabilities using an isolated Kubernetes environment.

## Key Files

- `run.sh`: Main entry script that sets up the Docker environment and starts the sandbox
  - Detects Docker GID
  - Checks for Anthropic API key and prompts if not set
  - Handles cleanup on exit
- `start.sh`: Script executed inside the sandbox container to initialize Kind and challenge environment
  - Validates API key environment variables
  - Configures vibectl with the API key and model settings
  - Sets up memory for the challenges
- `compose.yml`: Docker Compose configuration defining the sandbox and poller services
  - Passes API key from host environment to containers
- `Dockerfile`: Container definition for the sandbox environment
- `README.md`: User documentation for the sandbox
- `STRUCTURE.md`: This file, documenting component structure

## Directories

- `poller/`: Contains the service that monitors challenge completion
  - `poller.sh`: Script that polls endpoints to detect successful challenges
  - `Dockerfile`: Container definition for the poller
  - `README.md`: Documentation for the poller component

## Architecture

The sandbox operates with two main components in an isolated Docker network:

1. **Sandbox Container**: Creates a Kind Kubernetes cluster and runs vibectl to solve challenges
   - Uses internal nodePort services on fixed ports (30001-30003)
   - Executes vibectl in autonomous mode to solve challenges
   - Mounts Docker socket to run Kind inside the container
   - Uses a health check to verify the cluster is ready

2. **Poller Container**: Monitors success by checking endpoints within the internal network
   - Connects directly to the sandbox container (no host port mapping)
   - Polls each service port for the expected flag text
   - Reports completion status
   - Waits for sandbox container health check before starting
   - Exits when all challenges are completed

## Interface with Main Project

This sandbox demonstrates vibectl's autonomous capabilities by creating a controlled environment where:

- vibectl memory is initialized with challenge instructions
- vibectl must infer kubectl commands to execute based on limited information
- vibectl success is measured by external validation (poller)

## Configuration

The sandbox can be configured with the following environment variables:

- `VIBECTL_ANTHROPIC_API_KEY`: Required API key for Claude (passed from host to container)
- `VIBECTL_MODEL`: Model to use (defaults to claude-3.7-sonnet)
- `DOCKER_GID`: Docker group ID for socket access (auto-detected)

## API Key Handling

API keys are handled securely through these mechanisms:

1. User provides API key via environment variable or interactive prompt in `run.sh`
2. Key is passed to containers through Docker Compose environment variables
3. `start.sh` validates key presence and configures vibectl with:
   - Direct environment variable export (VIBECTL_ANTHROPIC_API_KEY and ANTHROPIC_API_KEY)
   - Configuration via `vibectl config set model_keys.anthropic`
4. No API keys are stored in container images or filesystem
