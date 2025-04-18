# Planned Changes: Chaos Monkey Demo

## Overview
Create a new red-team vs. blue-team demonstration in the K8s sandbox environment that simulates a "chaos monkey" scenario where:
- A "blue" agent tries to maintain service uptime and system stability
- A "red" agent attempts to disrupt the service through various attack vectors
- A poller continuously checks system availability
- An overseer coordinates and evaluates performance metrics

## Directory Structure
```
examples/
├── k8s-sandbox/
│   ├── ctf/          # (existing capture-the-flag demo)
│   │   └── ...
│   └── chaos-monkey/ # (new red vs. blue demo)
│       ├── README.md
│       ├── STRUCTURE.md
│       ├── docker-compose.yaml
│       ├── Makefile
│       ├── overseer/
│       │   └── ...
│       ├── poller/
│       │   └── ...
│       ├── services/
│       │   └── ...
│       ├── blue-agent/
│       │   └── ...
│       └── red-agent/
│           └── ...
```

## Key Components

### Services
- Deploy a distributed microservice architecture (e.g., a simple online store or content delivery system)
- Include standard components like:
  - Frontend application
  - Backend API service
  - Database
  - Cache
  - Load balancer

### Blue Agent
- Use vibectl to monitor and maintain system health
- Responsibilities:
  - Monitor system health and performance metrics
  - Detect anomalies in system behavior
  - Respond to failures by restarting services
  - Scale resources as needed
  - Restore backups when data corruption is detected
  - Implement security measures as attacks are discovered

### Red Agent
- Use vibectl to simulate various attack and disruption scenarios
- Attack vectors:
  - Resource exhaustion (CPU/memory consumption)
  - Network disruption (deleting routes, blocking ports)
  - Pod termination
  - Configuration tampering
  - Data corruption
  - Service degradation (introducing latency)
  - Simulated security exploits

### Poller
- Continuously access the service from outside the cluster
- Record response times and availability
- Send availability data to the overseer

### Overseer
- Coordinate the overall demonstration
- Track and display key metrics:
  - System uptime percentage
  - Mean time to recovery
  - Attack success/failure rates
  - Blue team response effectiveness
- Control game parameters:
  - Difficulty levels
  - Time limits
  - Attack frequency
  - Scoring rules

## Implementation Considerations

### Container Setup
- Deploy vibectl agents in separate containers from the K8s sandbox
- Ensure proper RBAC permissions for both agents to interact with the cluster
- Blue agent will need permissions to:
  - View and manage all resources
  - Scale deployments
  - Create/restore backups
- Red agent will need permissions to:
  - Modify/delete resources (within safety constraints)
  - Execute privileged operations on selected nodes

### Safety Measures
- Implement safeguards to prevent the red agent from:
  - Attacking the overseer or poller components
  - Breaking out of the sandbox environment
  - Making permanent or unrecoverable changes
- Add protection for critical infrastructure components

### Metrics and Evaluation
- Define clear success criteria for both agents
- Implement metrics collection for:
  - Service response times
  - Error rates
  - Recovery times
  - System resource utilization
- Visualize performance over time

### Documentation
- Create comprehensive setup instructions
- Document the architecture and components
- Provide a tutorial for running and customizing the demo
- Explain how to add new attack vectors or defense strategies

## Future Enhancements
- Multiple difficulty levels
- Different service architectures to protect
- AI-powered learning for both agents over multiple rounds
- Additional attack vectors and defense strategies
- Integration with security scanning tools
