# Kubernetes CTF Sandbox

This directory contains a Capture The Flag (CTF) style sandbox environment for testing vibectl's autonomous mode capabilities using an isolated Kubernetes environment. The sandbox supports multiple difficulty levels to gradually test and improve vibectl's capabilities.

**Note:** This demo installs `vibectl` directly from your local source code (`pip install -e .`). This allows you to test local changes within the sandbox.

## Requirements

- Docker and Docker Compose
- An Anthropic API key for Claude (starts with `sk-ant-`)

## Running the Sandbox

The simplest way to run the sandbox is with the provided script:

```zsh
./run.sh
```

This script will:
1. Check for a required Anthropic API key (prompting you if not set)
2. Set up a Docker-based sandbox environment with Kind Kubernetes, including an `overseer` container to manage the challenge.
3. Deploy vibectl in autonomous mode within a `sandbox` container to solve CTF challenges.
4. Monitor progress via a `poller` container that checks endpoints.
5. Automatically shut down all containers when the `overseer` determines the challenge is complete or the time limit is reached, thanks to the `--abort-on-container-exit` flag used with Docker Compose.

You can also provide your API key as an environment variable:

```zsh
export VIBECTL_ANTHROPIC_API_KEY=your-api-key-here
./run.sh
```

## Challenge Difficulty Levels

The sandbox supports three difficulty levels:

1. **Easy** (default): Single service challenge
   - Create a service that returns a flag on port 30001
   - Good for initial testing of vibectl's capabilities

2. **Medium**: Two service challenges
   - Includes the easy challenge, plus:
   - Create a resilient service with multiple replicas on port 30002

3. **Hard**: Three service challenges
   - Includes all previous challenges, plus:
   - Create a service using ConfigMap to store flag text on port 30003

You can select the difficulty level when running the sandbox:

```zsh
# Run with easy difficulty (default)
./run.sh

# Run with medium difficulty
./run.sh --difficulty medium

# Run with hard difficulty
./run.sh --difficulty hard

# Run with a specific model
./run.sh --model claude-3-haiku

# Run with verbose output (shows kubectl commands and raw output)
./run.sh --verbose

# Run with multiple options
./run.sh --difficulty medium --verbose
./run.sh --difficulty hard --model claude-3-haiku
./run.sh --model claude-3-opus --verbose

# See all available options
./run.sh --help
```

## Monitoring Progress

The sandbox runs multiple containers, primarily:
- **overseer**: Manages challenge state, configuration, and timing.
- **sandbox**: Contains Kind K8s cluster and runs vibectl.
- **poller**: Monitors solution progress on the active ports based on difficulty level.

The poller will check if the flags are accessible at the expected ports and only monitor the ports relevant to the selected difficulty level. The overseer monitors the poller's status and the time limit.

When running with the `--verbose` flag, vibectl will show the raw output and kubectl commands being executed, making it easier to debug and understand what's happening.

## Cleaning Up

The sandbox is designed to shut down automatically when the challenge is completed successfully or the time limit is reached. This is triggered by the `overseer` container exiting, which causes `docker compose up --abort-on-container-exit` (run by `run.sh`) to stop all other containers.

The `run.sh` script also includes a `trap` that ensures a thorough cleanup process (running `docker compose down --volumes --remove-orphans`) happens when the script exits, either normally after the challenge ends or if you interrupt it with Ctrl+C.

If needed, you can manually clean up all resources by running:

```zsh
docker compose -f compose.yml down --volumes --remove-orphans
```

## Troubleshooting

If you see errors about API keys:

```
Error: Error executing prompt: No key found - add one using 'llm keys set
anthropic' or set the ANTHROPIC_API_KEY environment variable
```

Make sure you've set the VIBECTL_ANTHROPIC_API_KEY environment variable before running ./run.sh or entered it when prompted.

## Environment Variables

You can configure the sandbox using these environment variables:

- `VIBECTL_ANTHROPIC_API_KEY`: Your Anthropic API key (required)
- `VIBECTL_MODEL`: Model to use (defaults to claude-3.7-sonnet, can also be set via --model flag)
- `CHALLENGE_DIFFICULTY`: Set difficulty level (easy, medium, hard) as alternative to --difficulty flag
- `VIBECTL_VERBOSE`: Set to true to enable verbose output (equivalent to --verbose flag)
