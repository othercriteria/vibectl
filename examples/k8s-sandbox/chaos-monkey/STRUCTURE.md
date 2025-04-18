# Chaos Monkey Demo Structure

This directory contains a "chaos monkey" style sandbox environment that simulates a red team vs. blue team scenario where:
- A "blue" agent tries to maintain service uptime and system stability
- A "red" agent attempts to disrupt the service through various attack vectors
- A poller continuously checks system availability
- An overseer coordinates and evaluates performance metrics

## Directory Structure

- `blue-agent/`: Contains the defensive agent components
  - `Dockerfile`: Container definition for the blue agent
  - `agent-entrypoint.sh`: Script executed inside the blue agent container
  - `memory-init.txt`: Initial memory/instructions for the blue agent
- `red-agent/`: Contains the offensive agent components
  - `Dockerfile`: Container definition for the red agent
  - `agent-entrypoint.sh`: Script executed inside the red agent container
  - `memory-init.txt`: Initial memory/instructions for the red agent
  - `attack-playbook.md`: Documentation of attack strategies
- `services/`: Contains the target service definitions
  - `Dockerfile`: Container definition for the services
  - `service-entrypoint.sh`: Script to initialize the target services
  - Kubernetes YAML files for deploying the target services
- `poller/`: Contains the availability monitoring service
  - `poller.sh`: Script that polls endpoints to check availability
  - `Dockerfile`: Container definition for the poller
- `overseer/`: Contains the coordination and metrics components
  - `overseer.sh`: Script that coordinates the demo and collects metrics
  - `Dockerfile`: Container definition for the overseer
  - `metrics.js`: Script for metrics visualization
- `run.sh`: Main entry script that sets up the environment and starts the demo
- `docker-compose.yaml`: Docker Compose configuration defining all services
- `Makefile`: For common tasks and easy usage
- `README.md`: User documentation for the demo
- `STRUCTURE.md`: This file, documenting component structure

## Key Components

### Blue Agent

The blue agent is responsible for maintaining system stability and uptime:
- Uses vibectl to monitor and manage Kubernetes resources
- Has appropriate RBAC permissions to interact with the cluster
- Reacts to detected failures and attacks by:
  - Restarting failed services
  - Scaling resources to handle load
  - Implementing defensive measures
  - Restoring from backup when necessary

### Red Agent

The red agent is responsible for simulating attacks and disruptions:
- Uses vibectl to identify and target system vulnerabilities
- Has limited RBAC permissions to prevent unrecoverable damage
- Implements various attack vectors:
  - Resource exhaustion
  - Pod termination
  - Configuration tampering
  - Network disruption
  - Service degradation

### Services

The target services represent a distributed microservice architecture:
- Deployed on a Kind Kubernetes cluster
- Includes frontend, backend API, database, and load balancer
- Exposes endpoints for the poller to verify availability
- Designed with known vulnerabilities for the red agent to exploit
- Structured to allow the blue agent to implement defenses

### Poller

The poller continuously checks service availability:
- Accesses services from outside the cluster
- Records response times and availability status
- Sends data to the overseer for evaluation
- Provides real-time feedback on service health

### Overseer

The overseer coordinates the overall demonstration:
- Tracks key metrics:
  - System uptime percentage
  - Mean time to recovery
  - Attack success/failure rates
  - Blue team response effectiveness
- Controls game parameters:
  - Time limits
  - Attack scheduling
  - Metrics collection
- Provides a dashboard for monitoring the scenario
- Generates reports of performance metrics

## Architecture

The demo operates with five main components in an isolated Docker network:

1. **Services Container**: Hosts a Kind Kubernetes cluster with target services
   - Creates a multi-tier application with multiple failure points
   - Exposes services on fixed ports
   - Provides a controlled environment for the simulation

2. **Blue Agent Container**: Runs vibectl to defend and maintain the services
   - Monitors for failures and attacks
   - Implements defense strategies
   - Restores services when they fail
   - Maintains separate configuration from the red agent

3. **Red Agent Container**: Runs vibectl to simulate attacks
   - Implements various attack strategies
   - Operates on a schedule defined by the overseer
   - Limited permissions to prevent unrecoverable damage
   - Adapts strategies based on blue agent's responses

4. **Poller Container**: Monitors service availability
   - Checks endpoint health continuously
   - Records response times and error rates
   - Reports to the overseer for scoring

5. **Overseer Container**: Coordinates the entire simulation
   - Controls timing of attacks
   - Collects and analyzes metrics
   - Provides a dashboard interface
   - Determines success/failure based on predefined criteria

## Safety Measures

To ensure the demonstration runs without unintended consequences:

1. The red agent has limitations to prevent:
   - Attacking the overseer or poller components
   - Breaking out of the sandbox environment
   - Making permanent or unrecoverable changes

2. Critical infrastructure is protected:
   - The blue agent has backup/restore capabilities
   - System state can be reset if needed
   - The entire environment is containerized to prevent external impact

## Configuration

The demo can be configured with the following parameters:

- `VIBECTL_ANTHROPIC_API_KEY`: Required API key for Claude
- `VIBECTL_MODEL`: Model to use for agents (defaults to claude-3.7-sonnet)
- `SESSION_DURATION`: How long the demonstration should run (in minutes)
- `DOCKER_GID`: Docker group ID for socket access (auto-detected)
- `METRICS_INTERVAL`: How frequently metrics are collected (in seconds)
- `VISUALIZATION`: Whether to enable the metrics visualization dashboard
- `VERBOSE`: Enable detailed logging output

## Agent Parameters

The agents can be fine-tuned with these parameters:

- `MEMORY_MAX_CHARS`: Maximum memory size for each agent (blue/red)
- `ACTION_PAUSE_TIME`: Time between actions for each agent (blue/red)
- `POLLER_RETRY_POLICY`: How the poller handles service disruptions

These parameters provide natural control over the balance between agents and can be adjusted to achieve different scenarios.

## API Key Handling

API keys are handled securely through these mechanisms:

1. User provides API key via environment variable or interactive prompt
2. Key is passed to containers through Docker Compose environment variables
3. Each agent container configures vibectl with the API key
4. No API keys are stored in container images or filesystem
