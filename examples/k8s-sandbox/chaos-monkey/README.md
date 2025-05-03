# Chaos Monkey Demo

A red team vs. blue team demonstration showcasing vibectl's capabilities in a Kubernetes environment. This demo simulates a "chaos monkey" scenario where:

- A blue agent works to maintain system stability and uptime
- A red agent **actively attacks and destroys services** through various attack vectors
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

# Optional: Configure passive/active phase durations (defaults are 5min/25min)
# export PASSIVE_DURATION=5
# export ACTIVE_DURATION=25

# Run the demo
./run.sh
```

After the demo starts, access the overseer dashboard at:
```
http://localhost:8080
```

## Components

### Target Services

The demo deploys a distributed microservice application **explicitly designed to be attacked** including:

- Frontend web application (Nginx-based with a simple status page)
- Backend API service (Nginx-based with **intentional vulnerabilities**)
- Database (Redis instance with **no persistence and no security**)
- Cache (Memcached with **minimal resource limits**)
- Load balancer (Nginx-based)

These services are **deliberately vulnerable** with labels like `chaos-target: "true"` and `purpose: "attack-me"` to make them clear targets for the red agent to exploit and destroy during its *active* phase. The blue agent's job is to detect and repair these attacks.

### Overseer

A web-based dashboard that:
- Provides immediate visibility into the Kubernetes cluster state
- Displays real-time pod status across all namespaces with health indicators
- Shows resource quota utilization for `kube-system` and `services` namespaces
- Scrapes the poller data for service availability metrics
- Features a consolidated dashboard with Kubernetes status, demo service metrics, health/response time visualization, and agent logs in one view
- Provides a separate detailed cluster status tab (showing node and pod status)
- Displays properly formatted terminal output including:
  - Correct rendering of ASCII box-drawing characters and tables
  - Proper alignment of kubectl table outputs with intelligent line joining
  - ANSI color code handling for agent log highlighting
  - Fixed-width font for consistent rendering of status displays
- Shows a warning banner if UI data appears stale (no updates for ~30 seconds)
- Accessible via web interface at http://localhost:8080 as soon as the demo starts

### Blue Agent

The defensive agent that:

- Operates in two phases: an initial **passive** phase (read-only RBAC) followed by an **active** phase (permissive RBAC).
- Receives initial instructions via `vibectl memory update` about the passive phase duration and constraints.
- Runs in a single continuous `vibectl auto` loop throughout both phases.
- Monitors system health using vibectl tools.
- Detects anomalies and attack damage (primarily during the active phase).
- Restarts failed services, scales resources, implements security measures, and repairs service disruptions caused by the red agent (during the active phase).

### Red Agent (Chaos Monkey)

The offensive agent that:

- Operates in two phases: an initial **passive** phase (read-only RBAC) followed by an **active** phase (permissive RBAC).
- Receives initial instructions via `vibectl memory update` about the passive phase duration and constraints.
- Runs in a single continuous `vibectl auto` loop throughout both phases.
- Explores the environment during the passive phase.
- **Aggressively attacks and destroys** services marked as attack targets during the *active* phase.
- Implements various destructive strategies including:
  - Deleting pods and deployments
  - Consuming resources to cause crashes
  - Exploiting dependencies between services
  - Targeting critical infrastructure components
- Adapts tactics based on blue agent responses.
- **Is explicitly instructed to cause maximum disruption** to test services (during the active phase).
- Operates within RBAC permissions assigned for each phase.
- Specifically targets components labeled with `chaos-target: "true"` and `attack-priority: "high"`.

### Poller

A Python-based service that:
- Continuously checks the status of each service (~every 1 second by default).
- Monitors response times and availability.
- Reports service health with color-coded status indicators.
- Tracks service degradation and recovery over time (retaining 1000 most recent health checks).
- Provides detailed pod status information.

## How It Works

1.  The demo starts by setting up a Kind Kubernetes cluster with isolated networking.
2.  The overseer dashboard initializes immediately, providing visibility into the cluster setup process.
3.  Initial Kubernetes resources (namespaces, quotas, agent service accounts) are applied.
4.  **Passive RBAC** rules (read-only) are applied for both agents.
5.  Target services are deployed in the cluster with **deliberately created vulnerabilities**.
6.  The poller begins monitoring service availability and feeds data to the overseer.
7.  The entrypoint script waits for the demo service deployment to become ready.
8.  Initial instructions about the passive phase duration and constraints are injected into both agents using `vibectl memory update`.
9.  Both agents are started using `vibectl auto` and begin their single, continuous loop.
10. The demo enters the **Passive Phase** (default 5 minutes). Agents explore with read-only permissions.
11. After the passive duration, the script **deletes passive RBAC** rules and **applies active RBAC** rules (permissive).
12. The demo enters the **Active Phase** (default 25 minutes). The Red Agent begins attacks, and the Blue Agent defends.
13. Throughout the demo, the overseer provides a comprehensive view of the battle between agents and the evolving cluster state.
14. After the active duration, the entrypoint script terminates the agent processes.

## Customization

Edit the following files to customize the demo:

- `attack-playbook.md`: Documentation of potential attack strategies.
- `defense-playbook.md`: Documentation of potential defense strategies.
- `k8s-sandbox/kubernetes/demo-services.yaml`: Target service definitions.
- `k8s-sandbox/kubernetes/blue-agent-rbac.yaml`: Active RBAC for the blue agent.
- `k8s-sandbox/kubernetes/red-agent-rbac.yaml`: Active RBAC for the red agent.
- `k8s-sandbox/kubernetes/blue-agent-passive-rbac.yaml`: Passive RBAC for the blue agent.
- `k8s-sandbox/kubernetes/red-agent-passive-rbac.yaml`: Passive RBAC for the red agent.
- `k8s-sandbox/kubernetes/resource-quotas.yaml`: Quotas for `kube-system` and `services`.

## Configuration Options

You can configure the demo by setting environment variables or using command-line flags:

```bash
# Set API key
export VIBECTL_ANTHROPIC_API_KEY=your_api_key_here

# Set model (defaults to claude-3.7-sonnet)
export VIBECTL_MODEL=claude-3.7-haiku

# Set durations in minutes (defaults are 5min passive, 25min active)
export PASSIVE_DURATION=10
export ACTIVE_DURATION=50

# Run with specific configuration via command line options
./run.sh --passive-duration 10 --active-duration 50 --verbose
```

Available command-line options:
- `--passive-duration MINUTES`: Set how long the initial read-only phase should run.
- `--active-duration MINUTES`: Set how long the main attack/defense phase should run.
- `--verbose`: Enable detailed logging from the entrypoint script.
- `--use-stable-versions`: Use stable, known good versions of packages from PyPI instead of the local repository.

## Package Versions

The demo can run in two modes:

1.  **Development Mode (default)**: Uses the local vibectl repository code, letting you test local changes.
2.  **Stable Mode**: Uses specific known working versions from PyPI for reliable demos.

To run with stable versions:
```bash
./run.sh --use-stable-versions
```

Current stable versions:
- vibectl: 0.4.1
- llm: 0.24.2
- llm-anthropic: 0.15.1
- anthropic: 0.49.0

To update the stable versions after testing:
1.  Find the current versions using `pip index versions <package-name>`
2.  Update the versions in `run.sh` (look for the "Define package versions" section)
3.  Test the new versions with `./run.sh --use-stable-versions`

## Development Status

Currently implemented features:

✅ Kind Kubernetes cluster creation with proper isolation
✅ Basic services with intentional vulnerabilities
✅ Phased RBAC for blue and red agents (passive read-only -> active permissive)
✅ Web dashboard via overseer with real-time cluster status monitoring
✅ Blue agent for defensive actions
✅ Red agent for attack simulation
✅ Python-based poller with comprehensive service monitoring
✅ Improved log formatting with ANSI codes and Docker timestamp stripping
✅ Consolidated dashboard with integrated agent logs and status/response time chart
✅ Enhanced terminal display with proper alignment of tables and ASCII art
✅ Stale data warning banner in UI
✅ Backend polling safeguards (`max_instances=1`)

## Monitoring The Demo

To observe the demo in action:

1.  Open the overseer dashboard in your browser immediately after starting the demo:
    ```
    http://localhost:8080
    ```

    The dashboard provides:
    - Cluster node/pod summary and control plane health
    - Resource quota usage (`kube-system`, `services`)
    - Demo service health metrics (status, uptime)
    - Health status & response time graph visualization
    - Real-time agent logs with activity timestamps
    - Properly rendered box-drawing characters and tables

2.  In one terminal, watch the blue agent's actions:
    ```bash
    make blue-logs
    ```

3.  In another terminal, watch the red agent's attacks:
    ```bash
    make red-logs
    ```

4.  To monitor service availability:
    ```bash
    make poller-logs
    ```

5.  To directly check the status of the services:
    ```bash
    docker exec chaos-monkey-k8s-sandbox kubectl get pods -n services
    ```

## Troubleshooting

If you encounter issues:

1.  Check the overseer dashboard for cluster initialization status and component health:
    ```
    http://localhost:8080
    ```

2.  Check if the cluster started properly in the sandbox logs:
    ```bash
    docker logs chaos-monkey-k8s-sandbox | grep "Kubernetes cluster created successfully"
    ```
    If the sandbox exited early, check the full logs (`docker logs chaos-monkey-k8s-sandbox`) for errors during Kind cluster creation or entrypoint execution.

3.  If the cluster is running but pods are stuck `Pending` (especially `kindnet`, `local-path-provisioner`, or demo services):
    *   Check node status:
        ```bash
        docker exec chaos-monkey-k8s-sandbox kubectl get nodes
        ```
    *   If the node is `NotReady`, describe it to find the reason:
        ```bash
        docker exec chaos-monkey-k8s-sandbox kubectl describe node chaos-monkey-control-plane
        ```
        (Common reasons include CNI issues like `NetworkPluginNotReady`).
    *   Check ResourceQuotas, especially in `kube-system`, as system pods might be blocked if limits are too low:
        ```bash
        docker exec chaos-monkey-k8s-sandbox kubectl get resourcequota -n kube-system
        docker exec chaos-monkey-k8s-sandbox kubectl describe resourcequota kube-system-compute-quota -n kube-system
        # Check daemonset events if quota issues are suspected for system components like kindnet:
        docker exec chaos-monkey-k8s-sandbox kubectl describe ds kindnet -n kube-system
        ```

4.  Verify the overseer dashboard is running and check its logs for errors (polling, sockets):
    ```bash
    docker logs chaos-monkey-overseer
    ```

5.  Check agent logs for errors:
    ```bash
    make blue-logs
    make red-logs
    ```

6.  For a complete reset:
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
- RBAC policies manage agent permissions, transitioning from passive to active.
- Network policies provide additional isolation for the monitoring infrastructure (intended, verify implementation)
- System monitoring and observability components are isolated from the attack surface

## Monitoring Architecture

The monitoring system consists of the overseer dashboard and a persistent health-checker pod (poller). The Overseer backend polls cluster state and agent logs, while the poller checks service health. This design ensures:

- Real-time visibility into cluster state with comprehensive status indicators
- Accurate response time measurements that reflect only the actual service performance
- Resilient monitoring that continues functioning even during aggressive chaos experiments
- Clear separation between monitoring infrastructure and the services being tested
- Consistent metrics collection throughout the entire demo session
- Intuitive web interface for tracking the progress of the simulation
