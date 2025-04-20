# Kubernetes CTF Sandbox Structure

This directory contains a Capture The Flag (CTF) style sandbox environment for testing vibectl's autonomous mode capabilities using an isolated Kubernetes environment. The sandbox can be run with different difficulty levels to gradually train and test vibectl's capabilities.

## Key Files

- `run.sh`: Main entry script that sets up the Docker environment and starts the sandbox
  - Detects Docker GID
  - Checks for Anthropic API key and prompts if not set
  - Handles cleanup on exit
  - Accepts `--difficulty` parameter to set challenge level
- `sandbox-entrypoint.sh`: Script executed inside the sandbox container to initialize Kind and challenge environment
  - Validates API key environment variables
  - Configures vibectl with the API key and model settings
  - Sets up memory for the challenges based on selected difficulty level
- `compose.yml`: Docker Compose configuration defining the sandbox and poller services
  - Passes API key and challenge difficulty from host environment to containers
- `Dockerfile`: Container definition for the sandbox environment
- `README.md`: User documentation for the sandbox
- `STRUCTURE.md`: This file, documenting component structure

## Directories

- `poller/`: Contains the service that monitors challenge completion
  - `poller.sh`: Script that polls endpoints to detect successful challenges
  - `Dockerfile`: Container definition for the poller
  - `README.md`: Documentation for the poller component
- `overseer/`: Contains the overseer component that coordinates the challenges
  - Monitors and reports on challenge progress
  - Provides feedback to the user

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
   - Exits when all challenges at the selected difficulty level are completed

## Challenge Difficulty Levels

The sandbox supports three difficulty levels:

1. **Easy**: Creates a single service returning a flag text on port 30001
   - Good for basic testing of vibectl's Kubernetes capabilities
   - Requires minimal knowledge of Kubernetes objects

2. **Medium**: Creates two services on ports 30001 and 30002
   - Second service requires multiple replicas for resilience
   - Tests more advanced deployment knowledge

3. **Hard**: Creates three services on ports 30001, 30002, and 30003
   - Third service requires using a ConfigMap
   - Tests comprehensive knowledge of Kubernetes configuration objects

## Interface with Main Project

This sandbox demonstrates vibectl's autonomous capabilities by creating a controlled environment where:

- vibectl memory is initialized with challenge instructions
- vibectl must infer kubectl commands to execute based on limited information
- vibectl success is measured by external validation (poller)
- Challenge difficulty can be adjusted to match vibectl's capabilities

## Configuration

The sandbox can be configured with the following environment variables:

- `VIBECTL_ANTHROPIC_API_KEY`: Required API key for Claude (passed from host to container)
- `VIBECTL_MODEL`: Model to use (defaults to claude-3.7-sonnet)
- `CHALLENGE_DIFFICULTY`: Difficulty level of challenges (easy, medium, hard)
- `DOCKER_GID`: Docker group ID for socket access (auto-detected)

## API Key Handling

API keys are handled securely through these mechanisms:

1. User provides API key via environment variable or interactive prompt in `run.sh`
2. Key is passed to containers through Docker Compose environment variables
3. `sandbox-entrypoint.sh` validates key presence and configures vibectl with:
   - Direct environment variable export (VIBECTL_ANTHROPIC_API_KEY and ANTHROPIC_API_KEY)
   - Configuration via `vibectl config set model_keys.anthropic`
4. No API keys are stored in container images or filesystem
