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
- `red-agent/attack-playbook.md`: Attack strategies
- `services/*.yaml`: Target service definitions

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

## Troubleshooting

If you encounter issues:

1. Ensure Docker is running with sufficient resources
2. Verify your API key is valid and has appropriate permissions
3. Check container logs: `docker compose logs blue-agent`
4. Restart the demo with verbose logging: `./run.sh --verbose`

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
