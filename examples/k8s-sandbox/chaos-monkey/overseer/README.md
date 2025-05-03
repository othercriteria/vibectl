# Chaos Monkey Overseer

The overseer component provides a web-based dashboard for monitoring the chaos monkey demo, including:

- Real-time Kubernetes cluster monitoring
- Service availability tracking and health metrics
- Service health history and status timelines
- Visualization of uptime and overall system health
- Live logs from both the blue (defender) and red (attacker) agents

## Features

- **Cluster Status Dashboard**: Comprehensive view of Kubernetes nodes, namespaces, and pods
- **Service Status Dashboard**: Real-time display of frontend service availability
- **Uptime Visualization**: Historical data on system uptime and reliability
- **Agent Activity Monitoring**: Live logs from both blue and red agents
- **Interactive Charts**: Visual representation of service health over time
- **Responsive Design**: Works on desktop and mobile devices
- **Tabbed Interface**: Easy navigation between cluster status and service monitoring

## Technical Implementation

The overseer is built using:

- **Flask**: Lightweight web server framework
- **Socket.IO**: Real-time bidirectional communication
- **Chart.js**: Interactive data visualization
- **Bootstrap**: Responsive UI components
- **Docker**: Containerized deployment
- **Kubernetes API**: Indirect access via k8s-sandbox container

## Architecture

The overseer:

1. **Initializes early** in the demo sequence to provide immediate visibility
2. **Monitors Kubernetes cluster** state, nodes, and pods
3. **Scrapes status data** from the poller service
4. **Follows logs** from both red and blue agents
5. **Maintains history** of service availability
6. **Provides visualization** via web dashboard
7. **Updates in real-time** using Socket.IO

## Usage

The overseer is automatically started as part of the demo when you run:

```bash
./run.sh
```

Once running, you can access the dashboard at:

```
http://localhost:8080
```

For dedicated cluster status monitoring:

```
http://localhost:8080/cluster-status
```

## Configuration

Configuration is handled via environment variables:

| Environment Variable    | Description                           | Default Value              |
| ----------------------- | ------------------------------------- | -------------------------- |
| `KUBECONFIG`          | Path to kubeconfig file               | (None)                     |
| `PASSIVE_DURATION`    | Passive phase duration (minutes)    | 5                          |
| `ACTIVE_DURATION`     | Active phase duration (minutes)     | 25                         |
| `POLLER_INTERVAL`     | Frontend poll interval (seconds)    | 1                          |
| `FLASK_ENV`           | Flask environment                     | production                 |
| `VERBOSE`             | Enable verbose logging                | false                      |
| `PORT`                | Port to run the web server on         | 8080                       |
| `KIND_CONTAINER`      | Name of the Kind control plane cont.  | chaos-monkey-control-plane |
| `BLUE_AGENT_CONTAINER`| Name of the blue agent container    | chaos-monkey-blue-agent  |
| `RED_AGENT_CONTAINER` | Name of the red agent container     | chaos-monkey-red-agent   |

## API Endpoints

The overseer provides several API endpoints:

- **GET /api/cluster**: Current Kubernetes cluster status
- **GET /api/status**: Current service status
- **GET /api/history**: Service status history
- **GET /api/logs/blue**: Blue agent logs
- **GET /api/logs/red**: Red agent logs
- **GET /api/overview**: System health overview

## Cluster Monitoring

The cluster monitoring feature provides:

- Node status with CPU and memory capacity
- Pod status across all namespaces
- Container readiness status
- Resource allocation information
- Visual indicators for pod health states
- Namespace organization and status

This gives operators immediate visibility into the battle between the red and blue agents as it unfolds within the Kubernetes environment.
