# Kubernetes CTF Sandbox

This directory contains a Capture The Flag (CTF) style sandbox environment for testing vibectl's autonomous mode capabilities using an isolated Kubernetes environment. The sandbox supports multiple difficulty levels to gradually test and improve vibectl's capabilities.

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
2. Set up a Docker-based sandbox environment with Kind Kubernetes
3. Deploy vibectl in autonomous mode to solve CTF challenges
4. Monitor progress via a poller container that checks endpoints

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

# See all available options
./run.sh --help
```

## Monitoring Progress

The sandbox runs two containers:
- **sandbox**: Contains Kind K8s cluster and runs vibectl
- **poller**: Monitors solution progress on the active ports based on difficulty level

The poller will check if the flags are accessible at the expected ports and only monitor the ports relevant to the selected difficulty level.

## Cleaning Up

To clean up all resources, press Ctrl+C in the terminal where you started ./run.sh, or run:

```zsh
docker compose -f compose.yml down --volumes --remove-orphans
```

The `run.sh` script includes a thorough cleanup process that:
- Stops and removes all containers
- Deletes the Kind cluster
- Removes any straggling containers
- Cleans up Docker networks

This cleanup happens automatically when you exit the script with Ctrl+C.

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
- `VIBECTL_MODEL`: Model to use (defaults to claude-3.7-sonnet)
- `CHALLENGE_DIFFICULTY`: Set difficulty level (easy, medium, hard) as alternative to --difficulty flag
