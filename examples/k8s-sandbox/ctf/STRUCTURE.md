# Kubernetes CTF Sandbox Structure

This directory contains a Capture The Flag (CTF) style sandbox environment for testing vibectl's autonomous mode capabilities using an isolated Kubernetes environment. The sandbox can be run with different difficulty levels to gradually train and test vibectl's capabilities.

## Key Files

- `run.sh`: Main entry script that sets up the Docker environment and starts the sandbox.
  - Detects Docker GID.
  - Checks for Anthropic API key and prompts if not set.
  - Calls `docker compose up --build --abort-on-container-exit` to run the services.
  - Relies on the `overseer` container exiting to trigger shutdown via Docker Compose.
  - Sets a `trap` to ensure `docker compose down` runs for thorough cleanup on script exit (normal or interrupted).
- `sandbox-entrypoint.sh`: Script executed inside the `sandbox` container to initialize Kind and run the `vibectl auto` process.
  - Validates API key environment variables.
  - Configures vibectl with the API key and model settings.
  - Sets up initial memory/instructions for vibectl.
  - Runs `vibectl auto` which continues until the container is stopped.
- `compose.yml`: Docker Compose configuration defining the `overseer`, `sandbox`, and `poller` services and their dependencies.
  - Defines shared named volumes (`status-volume`, `llm-keys-volume`).
  - Configures health checks and dependencies to manage startup order.
  - Passes API key and challenge difficulty from host environment to containers.
- `Dockerfile`: Container definition for the `sandbox` service.
- `README.md`: User documentation for the sandbox.
- `STRUCTURE.md`: This file, documenting component structure.

## Directories

- `poller/`: Contains the service that monitors challenge completion by checking service endpoints.
  - `poller.sh`: Script that polls endpoints and writes status to the shared `status-volume`.
  - `Dockerfile`: Container definition for the poller.
  - `README.md`: Documentation for the poller component.
- `overseer/`: Contains the service that coordinates the challenge.
  - `overseer.sh`: Script that generates challenge config, monitors the poller status and time limit via the shared `status-volume`, writes completion status, and exits when the challenge ends.
  - `config/`: Contains configuration generation logic.
  - `Dockerfile`: Container definition for the overseer.
  - `README.md`: Documentation for the overseer component.

## Architecture

The sandbox operates with three main components in an isolated Docker network:

1.  **Overseer Container**: Initializes the challenge configuration (difficulty, ports, flags, runtime) and writes it to the shared `status-volume`. Monitors the `poller` status and the overall time limit. Writes a completion message to the `status-volume` and exits when the challenge ends (success or timeout).
2.  **Sandbox Container**: Waits for the `overseer` to be healthy. Creates a Kind Kubernetes cluster. Runs `vibectl auto` to solve the challenge based on initial instructions. Continues running until stopped by Docker Compose.
3.  **Poller Container**: Waits for `overseer` and `sandbox` to be healthy. Reads challenge config from `status-volume`. Monitors success by checking service endpoints within the internal network. Writes verification progress to `status-volume`.

**Shutdown Sequence:**
- `overseer.sh` detects completion/timeout, writes final status, and exits (code 0).
- Docker Compose, running with `--abort-on-container-exit`, detects the `overseer` container exit.
- Docker Compose stops all other running containers (`sandbox`, `poller`).
- The `run.sh` script, which was waiting for `docker compose up` to finish, now proceeds.
- The `trap` in `run.sh` executes the `cleanup` function, running `docker compose down --volumes --remove-orphans` to remove containers, networks, and volumes, and deleting the Kind cluster.

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

The sandbox can be configured with the following environment variables in `run.sh`:

- `VIBECTL_ANTHROPIC_API_KEY`: Required API key for Claude (passed from host to container)
- `VIBECTL_MODEL`: Model to use (defaults to claude-3.7-sonnet)
- `CHALLENGE_DIFFICULTY`: Difficulty level of challenges (easy, medium, hard)
- `DOCKER_GID`: Docker group ID for socket access (auto-detected)

## API Key Handling

API keys are handled securely through these mechanisms:

1. User provides API key via environment variable or interactive prompt in `run.sh`
2. Key is passed to containers through Docker Compose environment variables
3. `sandbox-entrypoint.sh` uses the key via the `llm` library's credential handling (writing to a keys file in the `llm-keys-volume`).
4. No API keys are stored in container images.
