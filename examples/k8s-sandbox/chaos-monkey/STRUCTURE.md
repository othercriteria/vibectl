# Chaos Monkey Demo Structure

This directory contains a "chaos monkey" style sandbox environment that simulates a red team vs. blue team scenario where:
- A "blue" agent tries to maintain service uptime and system stability
- A "red" agent attempts to disrupt the service through various attack vectors
- A poller continuously checks system availability
- An overseer provides a dashboard with real-time monitoring

## Directory Structure

```
examples/k8s-sandbox/chaos-monkey/
├── README.md                  # Main documentation
├── STRUCTURE.md               # Project structure documentation
├── run.sh                     # Primary script to launch the demo
├── docker-compose.yaml        # Docker Compose configuration
├── Makefile                   # Build and development utilities
│
├── k8s-sandbox/               # Kubernetes sandbox environment
│   ├── Dockerfile             # Container definition for k8s-sandbox
│   ├── k8s-entrypoint.sh      # Entrypoint for k8s-sandbox container
│   └── kubernetes/            # Kubernetes resource definitions
│       └── demo-services.yaml # Basic services with vulnerabilities
│
├── agent/                     # Unified agent container
│   ├── Dockerfile             # Container definition for agents
│   ├── agent-entrypoint.sh    # Unified entrypoint for both agents
│   ├── blue-memory-init.txt   # Memory initialization for blue agent
│   ├── red-memory-init.txt    # Memory initialization for red agent
│   ├── blue-custom-instructions.txt # Custom instructions for blue agent
│   ├── red-custom-instructions.txt  # Custom instructions for red agent
│   ├── attack-playbook.txt    # Attack strategies for red agent
│   └── defense-playbook.txt   # Defense strategies for blue agent
│
├── poller/                    # Service availability checker
│   ├── Dockerfile             # Container definition for poller
│   └── poller.py              # Python service monitoring script
│
└── overseer/                  # Dashboard and monitoring system
    ├── Dockerfile             # Container definition for overseer
    ├── overseer.py            # Main application for monitoring
    ├── requirements.txt       # Python dependencies
    ├── README.md              # Overseer documentation
    ├── STRUCTURE.md           # Overseer structure documentation
    ├── static/                # Static web assets
    │   └── style.css          # Additional CSS styles
    └── templates/             # HTML templates
        └── index.html         # Dashboard template
```

## Key Components

### K8s Sandbox

The K8s Sandbox container creates and manages the Kind Kubernetes cluster where:
- It sets up a multi-node Kubernetes cluster in Docker
- Deploys a set of intentionally vulnerable services
- Manages networking for access to cluster services
- Shares kubeconfig with agent containers

### Target Services

The demo deploys microservices with intentional vulnerabilities:
- Frontend web app (Nginx with a simple status page)
- Backend API (Nginx with minimal configuration)
- Database (Redis with no persistence)
- Cache (Memcached with minimal resource limits)
- Load balancer (Nginx)

These services have various vulnerabilities:
- Insufficient replicas for high-availability
- Missing health checks
- Inadequate resource limits
- No persistent storage
- Secret management issues

### Blue Agent

The blue agent is responsible for defending and maintaining services:
- Uses vibectl to interact with the cluster
- Has permissions to fix and maintain services
- Implements defensive strategies from the defense playbook
- Monitors for attacks and service disruptions
- Works to restore and improve service resilience

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

### Poller

The poller continuously checks service availability:
- Python-based monitoring system with comprehensive checks
- Monitors the Kubernetes cluster health and individual service status
- Tracks pod readiness, restart counts, and container status
- Reports response times and HTTP status codes for each service
- Performs content validation for web services
- Checks Redis and Memcached connectivity
- Maintains a visual history of service health over time
- Generates detailed JSON status reports

### Overseer

The overseer provides a web-based dashboard and monitoring system:
- Flask-based web server with Socket.IO for real-time updates
- Scrapes poller data for service availability metrics
- Follows logs from both red and blue agents
- Visualizes service health history with interactive charts
- Calculates uptime statistics and availability trends
- Provides a responsive UI accessible at http://localhost:8080
- Maintains persistent storage of historical data
- Color-codes logs and status indicators for quick assessment

## Architecture

The demo operates with five main components in an isolated Docker network:

1. **K8s Sandbox Container**: Hosts a Kind Kubernetes cluster with target services
   - Creates a multi-tier application with multiple failure points
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

4. **Poller Container**: Monitors service availability
   - Checks cluster health continuously
   - Monitors pod status across namespaces
   - Provides regular status reports with colored indicators
   - Tracks service availability history and response times

5. **Overseer Container**: Provides dashboard and coordination
   - Web-based UI for monitoring the simulation in real-time
   - Aggregates data from poller for service availability metrics
   - Follows logs from both red and blue agents
   - Calculates and displays uptime metrics
   - Maintains persistent record of service health
   - Exposes a web interface on port 8080

## Unified Agent Architecture

The agents share a unified codebase with role-specific configuration:

1. **Shared Components**:
   - Common Dockerfile with all necessary tools
   - Unified entrypoint script that adapts behavior based on role
   - Same underlying Kubernetes API access mechanism
   - Shared kubeconfig from k8s-sandbox container

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
   - Attacking system components
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
- `POLL_INTERVAL_SECONDS`: How frequently the poller checks service status (in seconds)
- `METRICS_INTERVAL`: How frequently the overseer updates metrics (in seconds)
- `VISUALIZATION`: Enable/disable visualization features in the dashboard
- `VERBOSE`: Enable detailed logging output

## Agent Parameters

The agents can be fine-tuned with these parameters:

- `BLUE_MEMORY_MAX_CHARS`/`RED_MEMORY_MAX_CHARS`: Maximum memory size for each agent
- `BLUE_ACTION_PAUSE_TIME`/`RED_ACTION_PAUSE_TIME`: Time between actions for each agent
- `INITIAL_DELAY`: Delay before agent starts operations (useful for red agent)

These parameters provide natural control over the balance between agents and can be adjusted to achieve different scenarios.

## API Key Handling

API keys are handled securely through these mechanisms:

1. User provides API key via environment variable or interactive prompt
2. Key is passed to containers through Docker Compose environment variables
3. Each agent container configures vibectl with the API key
4. No API keys are stored in container images or filesystem
