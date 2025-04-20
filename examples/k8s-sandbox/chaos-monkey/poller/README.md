# Chaos Monkey Poller

The poller is a crucial monitoring component in the Chaos Monkey demo that provides real-time visibility into Kubernetes service health. It continuously monitors the availability and performance of the frontend service, reporting its status with color-coded indicators.

## Architecture

The poller runs as a standalone container within the Chaos Monkey environment and integrates with the Kubernetes cluster via:

1. **Shared Kubernetes Configuration** - Mounts the same kubeconfig volume used by other components
2. **Docker Socket Access** - Has access to the Docker socket to communicate with the sandbox container
3. **Status Reporting** - Maintains a status file that can be consumed by other components

```
┌─────────────────┐      ┌───────────────────┐      ┌────────────────┐
│  Poller Service │──────▶ Kubernetes API    │──────▶ Frontend Service│
└─────────────────┘      └───────────────────┘      └────────────────┘
        │                         │                         │
        │                         │                         │
        ▼                         ▼                         ▼
┌─────────────────┐      ┌───────────────────┐      ┌────────────────┐
│  Status Reports │      │ Pod Status Checks │      │ HTTP Validation │
└─────────────────┘      └───────────────────┘      └────────────────┘
```

## Functionality

The poller performs the following key functions:

1. **Service Health Monitoring**
   - Checks HTTP endpoints to verify service availability
   - Measures response times to detect degradation
   - Validates response content for correctness

2. **Pod Status Tracking**
   - Monitors the number of ready pods
   - Reports pod readiness ratios (ready/total)

3. **Status Reporting**
   - Outputs color-coded status to console logs
   - Updates a status file for integration with other tools
   - Categorizes health as HEALTHY, DEGRADED, or DOWN

## Operation Sequence

1. Waits for the Kubernetes configuration to become available
2. Identifies the sandbox container running the Kubernetes cluster
3. Checks if the Kubernetes cluster is running properly
4. Polls the frontend service for health status
5. Updates and reports service status
6. Repeats the process at configured intervals

## Configuration

The poller can be configured via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `POLL_INTERVAL_SECONDS` | Time between service checks | 15 |
| `DELAY_SECONDS` | Initial delay before starting checks | 15 |
| `SESSION_DURATION` | Total duration in minutes | 30 |
| `KUBECONFIG` | Path to Kubernetes config file | /config/kube/config |
| `STATUS_DIR` | Directory for status reporting | /tmp/status |
| `KIND_CONTAINER` | Name prefix for the KIND container | chaos-monkey-control-plane |
| `VERBOSE` | Enable verbose logging | false |

## Status Reporting

The poller classifies service health into three categories:

- **HEALTHY** (🟢): Service is fully operational with good response times
- **DEGRADED** (🟡): Service is responding but with issues (slow or partial functionality)
- **DOWN** (🔴): Service is unavailable or critically impaired

Status information is stored in JSON format with details about:
- Current status
- Response time
- Error messages (if any)
- Endpoint information
- Pod readiness statistics

## Integration

The poller integrates with the Chaos Monkey demo by:

1. Running as a service defined in the docker-compose configuration
2. Sharing the Kubernetes configuration volume with other services
3. Using Docker socket access to communicate with the sandbox
4. Providing status information that can be consumed by other components

## Reliability Features

- Graceful startup with dependency checking
- Proper error handling and reporting
- Automatic recovery from temporary failures
- Session duration enforcement
- Regular status updates for monitoring progress

## Usage

The poller starts automatically when running the Chaos Monkey demo:

```bash
make start
```

To view poller logs:

```bash
make poller-logs
```

To manually check the current status:

```bash
docker exec chaos-monkey-poller cat /tmp/status/frontend-status.json
```
