# CTF Challenge Overseer

The overseer is a coordination component that manages the CTF challenge flow and determines success. It replaces the previous tight coupling between the sandbox and poller containers.

## Purpose

The overseer serves several key purposes:

1. **Decoupling Components**: Separates service verification from challenge success determination
2. **Reliable Success Detection**: Provides consistent, verified challenge completion detection
3. **Status Coordination**: Centralizes status reporting between components
4. **Graceful Shutdown**: Manages the termination of all containers upon success

## How It Works

The overseer:

1. Initializes its status in a shared volume (`/status`) accessible to all containers
2. Waits for a minimum runtime to prevent premature success detection
3. Independently verifies all services by checking ports and expected flag content
4. Requires multiple successful verifications to ensure stability
5. Terminates the sandbox when all challenge criteria are met

## Configuration

The overseer accepts these environment variables:

- `CHALLENGE_DIFFICULTY`: Difficulty level (easy, medium, hard)
- `ACTIVE_PORTS`: Comma-separated list of ports to monitor
- `MIN_RUNTIME_SECONDS`: Minimum runtime before considering success (default: 60)
- `SUCCESS_VERIFICATION_COUNT`: Number of successful checks required (default: 2)
- `POLL_INTERVAL_SECONDS`: Time between verification attempts (default: 10)

## Integration

The overseer coordinates with other containers via:

1. A shared volume for status files (`/status`)
2. Docker socket access to manage other containers
3. Direct service verification using the sandbox container

This design eliminates premature success detection and flakiness in the CTF challenge environment.
