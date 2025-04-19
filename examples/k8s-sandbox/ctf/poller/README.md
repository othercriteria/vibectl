# CTF Challenge Poller

A service that monitors the progress of the CTF challenges by checking for specific flag text on exposed ports.

## Architecture

- Runs in a separate container connected to the sandbox via an internal Docker network
- Waits for the Kubernetes cluster in the sandbox to be fully operational
- Polls services on predefined internal ports (30001, 30002, 30003)
- Reports progress with colored status output
- Exits when all challenges are completed

## Operation Sequence

1. The poller waits for the sandbox container to pass its health check (via Docker Compose)
2. It then attempts to connect to service ports in the sandbox container
3. When services start responding, it checks for expected flag text in responses
4. It reports challenge completion as flags are found
5. When all three challenges are complete, the poller exits with success

## Why the CTF is Challenging

Although the poller provides basic validation (checking for text on specific ports), the CTF remains challenging because:

- vibectl cannot use curl or any HTTP testing tools
- vibectl has no way to directly verify if its services are working
- The agent must reason about service exposure and configuration without feedback
- vibectl must track which steps it has completed using its memory system

## Reliability Features

- Graceful startup with health check waiting
- Connection timeouts to prevent hanging
- Generous retry logic for service connections
- Clean failure handling and reporting

## Future Improvements

- **Detailed Verification**: Check actual Kubernetes resources (replicas, ConfigMap)
- **Enhanced Metrics**: Track time to completion and response times
- **Improved UI**: Real-time status updates via websocket
- **Automated Testing**: Compare different LLM models' performance
