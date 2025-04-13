# Kubernetes CTF Sandbox

This directory contains a Capture The Flag (CTF) style sandbox environment for testing vibectl's autonomous mode capabilities using an isolated Kubernetes environment.

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

## Monitoring Progress

The sandbox runs two containers:
- **sandbox**: Contains Kind K8s cluster and runs vibectl
- **poller**: Monitors solution progress on ports 30001, 30002, and 30003

The poller will check if the flags are accessible at the expected ports.

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
