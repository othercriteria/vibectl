# Chaos Monkey Demo

A red team vs. blue team demonstration showcasing vibectl's capabilities in a Kubernetes environment. This demo simulates a "chaos monkey" scenario where:

- A blue agent works to maintain system stability and uptime
- A red agent attempts to disrupt services through various attack vectors
- A poller monitors service availability in real-time
- An overseer provides a dashboard with service monitoring, agent logs, and cluster status

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

After the demo starts, access the overseer dashboard at:
```
http://localhost:8080
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

### Overseer

A web-based dashboard that:
- Provides immediate visibility into the Kubernetes cluster state
- Displays real-time pod status across all namespaces with health indicators
- Shows resource utilization metrics for CPU, memory, and network
- Scrapes the poller data for service availability metrics
- Follows logs from both red and blue agents with real-time updates
- Visualizes service health over time with trend analysis
- Calculates uptime statistics and displays performance degradation alerts
- Features clean, formatted logs with ANSI color codes and timestamps stripped for improved readability
- Accessible via web interface at http://localhost:8080 as soon as the demo starts

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
2. The overseer dashboard initializes immediately, providing visibility into the cluster setup process
3. Target services are deployed in the cluster with known vulnerabilities
4. The poller begins monitoring service availability and feeds data to the overseer
5. The blue agent is initialized with defensive responsibilities
6. The red agent begins implementing attacks after a short delay
7. Throughout the demo, the overseer provides a comprehensive view of the battle between agents and the evolving cluster state

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

# Set session duration in minutes (defaults to 30 min)
export SESSION_DURATION=60

# Set metrics interval in seconds (defaults to 15 sec)
export METRICS_INTERVAL=10

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
✅ Web dashboard via overseer with real-time cluster status monitoring
✅ Blue agent for defensive actions
✅ Red agent for attack simulation
✅ Python-based poller with comprehensive service monitoring
✅ Improved log formatting with ANSI codes and Docker timestamp stripping

## Monitoring The Demo

To observe the demo in action:

1. Open the overseer dashboard in your browser immediately after starting the demo:
   ```
   http://localhost:8080
   ```

   The dashboard provides:
   - Cluster node status and resource utilization
   - Pod status across all namespaces with health indicators
   - Service health metrics with response time trends
   - Real-time agent logs with activity timestamps
   - Resource consumption graphs for key components

2. In one terminal, watch the blue agent's actions:
   ```bash
   make blue-logs
   ```

3. In another terminal, watch the red agent's attacks:
   ```bash
   make red-logs
   ```

4. To monitor service availability:
   ```bash
   make poller-logs
   ```

5. To directly check the status of the services:
   ```bash
   docker exec chaos-monkey-k8s-sandbox kubectl get pods -n services
   ```

## Troubleshooting

If you encounter issues:

1. Check the overseer dashboard for cluster initialization status:
   ```
   http://localhost:8080/cluster-status
   ```

2. Check if the cluster started properly:
   ```bash
   docker logs chaos-monkey-k8s-sandbox | grep "Kubernetes"
   ```

3. Verify the overseer dashboard is running:
   ```bash
   docker logs chaos-monkey-overseer
   ```

4. For a complete reset:
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
- Health monitoring resources are protected in a dedicated `system-monitoring` namespace
- RBAC policies completely hide system monitoring resources from both agent roles
- Network policies provide additional isolation for the monitoring infrastructure
- System monitoring and observability components are isolated from the attack surface

## Monitoring Architecture

The monitoring system consists of the overseer dashboard and a persistent health-checker pod in a protected namespace that cannot be attacked, modified, or even viewed by the agents. This design ensures:

- Real-time visibility into cluster state with comprehensive status indicators
- Accurate response time measurements that reflect only the actual service performance
- Resilient monitoring that continues functioning even during aggressive chaos experiments
- Clear separation between monitoring infrastructure and the services being tested
- Consistent metrics collection throughout the entire demo session
- Prevents agents from fixating on resources they don't need to interact with
- Intuitive web interface for tracking the progress of the simulation

---

© 2025 Daniel Klein. Part of the [vibectl](https://github.com/othercriteria/vibectl) project.
