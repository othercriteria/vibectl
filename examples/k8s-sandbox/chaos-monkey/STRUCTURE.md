# Chaos Monkey Demo Structure

This directory contains a "chaos monkey" style sandbox environment that simulates a red team vs. blue team scenario where:
- A "blue" agent tries to maintain service uptime and system stability
- A "red" agent attempts to disrupt the service through various attack vectors
- A poller continuously checks system availability
- An overseer coordinates and evaluates performance metrics

## Directory Structure

- `agent/`: Contains the unified agent components for both blue and red agents
  - `Dockerfile`: Single container definition for both agents
  - `agent-entrypoint.sh`: Unified script for both blue and red agents
  - `blue-memory-init.txt` & `red-memory-init.txt`: Initial memory for respective agents
  - `blue-custom-instructions.txt` & `red-custom-instructions.txt`: Custom instructions for respective agents
  - `defense-playbook.txt`: Blue agent strategies for system defense
  - `attack-playbook.txt`: Red agent strategies for system disruption
- `services/`: Contains the target service definitions
  - `Dockerfile`: Container definition for the services
  - `service-entrypoint.sh`: Script to initialize the target services
  - Kubernetes YAML files for deploying the target services
- `poller/`: Contains the availability monitoring service (future implementation)
  - `poller.sh`: Script that polls endpoints to check availability
  - `Dockerfile`: Container definition for the poller
- `overseer/`: Contains the coordination and metrics components (future implementation)
  - `overseer.sh`: Script that coordinates the demo and collects metrics
  - `Dockerfile`: Container definition for the overseer
  - `metrics.js`: Script for metrics visualization
- `run.sh`: Main entry script that sets up the environment and starts the demo
- `docker-compose.yaml`: Docker Compose configuration defining all services
- `Makefile`: For common tasks and easy usage
- `README.md`: User documentation for the demo
- `STRUCTURE.md`: This file, documenting component structure
- `attack-playbook.md`: Markdown documentation of attack strategies
- `defense-playbook.md`: Markdown documentation of defense strategies

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

The poller continuously checks service availability (future implementation):
- Accesses services from outside the cluster
- Records response times and availability status
- Sends data to the overseer for evaluation
- Provides real-time feedback on service health

### Overseer

The overseer coordinates the overall demonstration (future implementation):
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
   - Shares kubeconfig with agent containers

2. **Blue Agent Container**: Runs vibectl to defend and maintain the services
   - Monitors for failures and attacks
   - Implements defense strategies
   - Restores services when they fail
   - Uses the unified agent container with blue-specific configuration

3. **Red Agent Container**: Runs vibectl to simulate attacks
   - Implements various attack strategies
   - Operates with a delay to allow blue agent time to assess the environment
   - Limited permissions to prevent unrecoverable damage
   - Uses the unified agent container with red-specific configuration

4. **Poller Container**: Monitors service availability (future implementation)
   - Checks endpoint health continuously
   - Records response times and error rates
   - Reports to the overseer for scoring

5. **Overseer Container**: Coordinates the entire simulation (future implementation)
   - Controls timing of attacks
   - Collects and analyzes metrics
   - Provides a dashboard interface
   - Determines success/failure based on predefined criteria

## Unified Agent Architecture

The agents now share a unified codebase with role-specific configuration:

1. **Shared Components**:
   - Common Dockerfile with all necessary tools
   - Unified entrypoint script that adapts behavior based on role
   - Same underlying Kubernetes API access mechanism
   - Shared kubeconfig from services container

2. **Role-Specific Configuration**:
   - Agent role (blue/red) set via environment variables
   - Custom memory initialization based on role
   - Different playbooks (defense/attack) loaded based on role
   - Role-specific custom instructions
   - Different RBAC permissions in Kubernetes
   - Color-coded output for easy distinction (blue/red)

3. **Safety Features**:
   - Fail-fast on missing kubeconfig
   - Health checks to ensure cluster connectivity
   - Initial delay for red agent to allow blue agent preparation time

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

- `BLUE_MEMORY_MAX_CHARS`/`RED_MEMORY_MAX_CHARS`: Maximum memory size for each agent
- `BLUE_ACTION_PAUSE_TIME`/`RED_ACTION_PAUSE_TIME`: Time between actions for each agent
- `INITIAL_DELAY`: Delay before agent starts operations (useful for red agent)
- `POLLER_RETRY_POLICY`: How the poller handles service disruptions

These parameters provide natural control over the balance between agents and can be adjusted to achieve different scenarios.

## API Key Handling

API keys are handled securely through these mechanisms:

1. User provides API key via environment variable or interactive prompt
2. Key is passed to containers through Docker Compose environment variables
3. Each agent container configures vibectl with the API key
4. No API keys are stored in container images or filesystem
