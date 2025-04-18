# Chaos Monkey Demo

A red team vs. blue team demonstration showcasing vibectl's capabilities in a Kubernetes environment. This demo simulates a "chaos monkey" scenario where:

- A blue agent works to maintain system stability and uptime
- A red agent attempts to disrupt services through various attack vectors
- A poller monitors service availability in real-time
- An overseer tracks metrics and coordinates the simulation

## Requirements

- Docker and Docker Compose
- 8GB+ of available RAM
- 4+ CPU cores
- Anthropic Claude API key for the vibectl agents

## Quick Start

```bash
# Set your API key (or you'll be prompted)
export VIBECTL_ANTHROPIC_API_KEY=your_api_key_here

# Run the demo
./run.sh
```

## Components

### Target Services

The demo deploys a distributed microservice application including:

- Frontend web application
- Backend API service
- Database
- Cache
- Load balancer

These services form a realistic environment for the agents to interact with.

### Blue Agent

The defensive agent that:

- Monitors system health using vibectl
- Detects anomalies and attacks
- Restarts failed services
- Scales resources as needed
- Restores from backups when necessary
- Implements security measures

### Red Agent

The offensive agent that:

- Simulates various attack vectors
- Implements disruption strategies
- Adapts tactics based on blue agent responses
- Operates within safety constraints

### Metrics and Visualization

The demo tracks and displays:

- System uptime percentage
- Mean time to recovery
- Attack success/failure rates
- Blue team response effectiveness

Access the metrics dashboard at http://localhost:8080 when the demo is running.

## How It Works

1. The demo starts by setting up a Kind Kubernetes cluster
2. Target services are deployed in the cluster
3. The blue agent is initialized with defensive responsibilities
4. The red agent begins implementing attacks on a schedule
5. The poller continuously checks service availability
6. The overseer tracks metrics and coordinates between components
7. The dashboard displays real-time performance and statistics

## Customization

Edit the following files to customize the demo:

- `blue-agent/memory-init.txt`: Instructions for the blue agent
- `red-agent/memory-init.txt`: Instructions for the red agent
- `attack-playbook.md`: Attack strategies for the red agent
- `defense-playbook.md`: Defense strategies for the blue agent
- `services/kubernetes/*.yaml`: Target service definitions

### Required Kubernetes Files

The demo requires at least one Kubernetes YAML file to be present in the `services/kubernetes/` directory. If no YAML files are found, the services container will exit with an error message.

Currently, the following YAML file is included:
- `services/kubernetes/demo-services.yaml`: Defines the core services with intentional vulnerabilities for the blue agent to detect and fix

To add your own services, create additional YAML files in this directory following the Kubernetes resource specification format.

## Configuration Options

You can configure the demo by setting environment variables or using command-line flags:

```bash
# Set API key
export VIBECTL_ANTHROPIC_API_KEY=your_api_key_here

# Set model (defaults to claude-3.7-sonnet)
export VIBECTL_MODEL=claude-3.7-haiku

# Set session duration in minutes (defaults to 30)
export SESSION_DURATION=60

# Enable/disable visualization dashboard (defaults to true)
export VISUALIZATION=false

# Run with specific configuration via environment variables
./run.sh

# Or use command line options:
./run.sh --session-duration 45 --no-visualization --verbose
```

Available command-line options:
- `--session-duration MINUTES`: Set how long the demo should run
- `--no-visualization`: Disable the metrics dashboard
- `--verbose`: Enable detailed logging

## Development Status

This demo is currently in MVP (Minimum Viable Product) state. Here's what's implemented:

✅ Kind Kubernetes cluster creation
✅ Basic vulnerable services deployment (frontend, backend, database, cache, load balancer)
✅ RBAC for blue and red agents with appropriate permissions
✅ Blue agent framework for defensive actions
✅ Red agent framework for attack simulation

Pending implementation:
❌ Metrics collection
❌ Visualization dashboard
❌ Poller for service availability
❌ Overseer for coordination

### Current Limitations

1. Since this is an MVP, you may need to restart if the agents get stuck or the simulation breaks
2. The vulnerable services are basic implementation
3. The metrics and visualization components are commented out in the docker-compose.yaml
4. The demo will fail fast with a clear error if no Kubernetes service definitions are found

### Getting Started with the MVP

To run the MVP demo:

1. Ensure you have the Anthropic API key:
   ```bash
   export VIBECTL_ANTHROPIC_API_KEY=your_api_key_here
   ```

2. Start the demo in verbose mode to see what's happening:
   ```bash
   ./run.sh --verbose
   ```

3. Watch the agent logs to see the red team attacking and blue team defending:
   ```bash
   # In another terminal
   docker logs -f chaos-monkey-blue-agent

   # Or in yet another terminal
   docker logs -f chaos-monkey-red-agent
   ```

4. To check service states during the demo:
   ```bash
   # Get access to the cluster
   docker exec -it chaos-monkey-services bash

   # Check services status
   kubectl get pods -n services
   kubectl get services -n services
   ```

5. To stop the demo, use Ctrl+C in the terminal running the `run.sh` script

## Troubleshooting

If you encounter issues:

1. Ensure Docker is running with sufficient resources
   - The Kind Kubernetes cluster requires at least 4GB of RAM
   - Increase Docker memory limits if needed

2. Verify your API key is valid and has appropriate permissions
   - Must be an Anthropic API key (starting with `sk-ant-`)
   - Must have permission to use the specified model

3. Check container logs for specific errors:
   ```bash
   docker compose logs services
   docker compose logs blue-agent
   docker compose logs red-agent
   ```

4. If the services container appears to hang during startup:
   - The script now includes a 60-second timeout for cluster readiness
   - If you see it hanging at "Waiting for Kubernetes cluster to be ready...", it may be having trouble initializing the Kind cluster
   - This can happen due to network issues or resource constraints
   - Try stopping other Kubernetes clusters or containers that might be using the same resources
   - Check if your machine has sufficient memory and CPU available

5. If the "services" container shows as unhealthy or exits with an error:
   - Check if kubernetes files exist in services/kubernetes/ directory
   - This can happen if the kubernetes directory is empty or doesn't contain YAML files
   - Verify the files with: `ls -la examples/k8s-sandbox/chaos-monkey/services/kubernetes/*.yaml`
   - Check if port 30001-30003 are already in use on your system
   - Try stopping other containers or Kubernetes clusters first
   - Ensure the Docker socket is properly mounted with: `ls -l /var/run/docker.sock`

6. If the agents can't communicate with the Kind cluster:
   - Make sure the services container is healthy first
   - Check container networking with: `docker network inspect chaos-monkey-network`
   - Verify Kind cluster is running: `docker ps | grep chaos-monkey-control-plane`

7. For complete reset and restart:
   ```bash
   # Stop all running containers
   docker compose down --volumes --remove-orphans

   # Delete Kind cluster if it exists
   kind delete cluster --name chaos-monkey

   # Remove any leftover containers
   docker ps -a --filter "name=chaos-monkey" -q | xargs docker rm -f

   # Remove any orphaned docker volumes
   docker volume prune -f

   # Run with verbose logging
   ./run.sh --verbose
   ```

## Safety Measures

The demo includes safety measures to prevent unintended consequences:

- The red agent has limited RBAC permissions
- Protected namespaces for critical components
- Automatic state restoration for unrecoverable situations
- Complete containerization to prevent system impact

## Learn More

For more details about the architecture and implementation:

- See [STRUCTURE.md](STRUCTURE.md) for component details
- Explore the source code in each component directory
