# Chaos Monkey Demo

A red team vs. blue team demonstration showcasing vibectl's capabilities in a Kubernetes environment. This demo simulates a "chaos monkey" scenario where:

- A blue agent works to maintain system stability and uptime
- A red agent attempts to disrupt services through various attack vectors
- A poller monitors service availability in real-time

## Requirements

- Docker and Docker Compose
- 4GB+ of available RAM
- 2+ CPU cores
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

- Frontend web application (Nginx-based with a simple status page)
- Backend API service (Nginx-based with intentional vulnerabilities)
- Database (Redis instance with no persistence)
- Cache (Memcached with minimal resource limits)
- Load balancer (Nginx-based)

These services intentionally have vulnerabilities that the red agent can exploit and the blue agent can detect and fix.

### Blue Agent

The defensive agent that:

- Monitors system health using vibectl
- Detects anomalies and attacks
- Restarts failed services
- Scales resources as needed
- Implements security measures

### Red Agent

The offensive agent that:

- Simulates various attack vectors from the attack playbook
- Implements disruption strategies
- Adapts tactics based on blue agent responses
- Operates within safety constraints

### Poller

A Python-based service that:
- Continuously checks the status of each service
- Monitors response times and availability
- Reports service health with color-coded status indicators
- Tracks service degradation and recovery over time
- Provides detailed pod status information

## How It Works

1. The demo starts by setting up a Kind Kubernetes cluster with isolated networking
2. Target services are deployed in the cluster with known vulnerabilities
3. The blue agent is initialized with defensive responsibilities
4. The red agent begins implementing attacks after a short delay
5. The poller continuously checks service availability

## Customization

Edit the following files to customize the demo:

- `agent/blue-memory-init.txt`: Instructions for the blue agent
- `agent/red-memory-init.txt`: Instructions for the red agent
- `agent/attack-playbook.txt`: Attack strategies for the red agent
- `agent/defense-playbook.txt`: Defense strategies for the blue agent
- `k8s-sandbox/kubernetes/demo-services.yaml`: Target service definitions

## Configuration Options

You can configure the demo by setting environment variables or using command-line flags:

```bash
# Set API key
export VIBECTL_ANTHROPIC_API_KEY=your_api_key_here

# Set model (defaults to claude-3.7-sonnet)
export VIBECTL_MODEL=claude-3.7-haiku

# Set session duration in minutes (defaults to 30)
export SESSION_DURATION=60

# Run with specific configuration via command line options
./run.sh --session-duration 45 --verbose
```

Available command-line options:
- `--session-duration MINUTES`: Set how long the demo should run
- `--verbose`: Enable detailed logging

## Development Status

Currently implemented features:

✅ Kind Kubernetes cluster creation with proper isolation
✅ Basic services with intentional vulnerabilities
✅ RBAC for blue and red agents with appropriate permissions
✅ Blue agent for defensive actions
✅ Red agent for attack simulation
✅ Python-based poller with comprehensive service monitoring

## Monitoring The Demo

To observe the demo in action:

1. In one terminal, watch the blue agent's actions:
   ```bash
   make blue-logs
   ```

2. In another terminal, watch the red agent's attacks:
   ```bash
   make red-logs
   ```

3. To monitor service availability:
   ```bash
   make poller-logs
   ```

4. To directly check the status of the services:
   ```bash
   docker exec chaos-monkey-k8s-sandbox kubectl get pods -n services
   ```

## Troubleshooting

If you encounter issues:

1. Check if the cluster started properly:
   ```bash
   docker logs chaos-monkey-k8s-sandbox | grep "Kubernetes"
   ```

2. For a complete reset:
   ```bash
   make clean
   ./run.sh --verbose
   ```

## Security and Isolation

The chaos-monkey demo creates a fully isolated Kubernetes environment:

- All components run in Docker containers with an isolated network
- No ports are exposed to the host system except when explicitly configured
- The Kubernetes cluster runs entirely within containers
- Complete separation from any host Kubernetes configuration
