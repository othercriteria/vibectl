# Chaos Monkey Demo Structure

This directory contains a "chaos monkey" style sandbox environment simulating a red team vs. blue team scenario within a Kubernetes cluster using `vibectl` agents.

## Overview

The demo orchestrates several components via Docker Compose:
- A **Kind Kubernetes cluster** (`k8s-sandbox`) hosting intentionally vulnerable services.
- A **Blue Agent** (`blue-agent`) using `vibectl` to defend the services.
- A **Red Agent** (`red-agent`) using `vibectl` to attack the services.
- A **Poller** (`poller`) service monitoring the health of the target services.
- An **Overseer** (`overseer`) web dashboard displaying real-time status, logs, and metrics.

## Directory Structure

```
examples/k8s-sandbox/chaos-monkey/
├── README.md                  # Main documentation for the demo
├── STRUCTURE.md               # This file: structure of the chaos-monkey demo
├── run.sh                     # Primary script to launch the demo environment
├── docker-compose.yaml        # Docker Compose configuration for all demo services
├── Makefile                   # Build and development utilities
│
├── k8s-sandbox/               # Kind cluster setup and target service manifests
│   └── kubernetes/            # Kubernetes resource definitions (services, RBAC, etc.)
│
├── agent/                     # Shared Dockerfile and entrypoint for Blue/Red agents
│   ├── blue-memory-init.txt   # Initial memory for blue agent
│   ├── red-memory-init.txt    # Initial memory for red agent
│   ├── blue-custom-instructions.txt # Persistent instructions for blue agent
│   ├── red-custom-instructions.txt  # Persistent instructions for red agent
│   └── ... (playbooks)        # Agent strategy guides
│
├── poller/                    # Service availability checker code and Dockerfile
│
└── overseer/                  # Overseer dashboard code (Flask backend, React frontend)
    └── STRUCTURE.md           # Detailed structure of the overseer component
```

## Key Files & Directories

- **`run.sh`**: The main entry point to start and stop the entire demo environment. Handles argument parsing and Docker Compose orchestration.
- **`docker-compose.yaml`**: Defines the five core services (k8s-sandbox, blue-agent, red-agent, poller, overseer), their builds, dependencies, networks, and configurations.
- **`Makefile`**: Provides convenience targets for building, running, logging, and cleaning the demo environment.
- **`k8s-sandbox/`**: Contains the setup for the Kind Kubernetes cluster. Key files include:
    - `k8s-entrypoint.sh`: Script run inside the sandbox container to create the Kind cluster, apply manifests, and manage phase transitions.
    - `Dockerfile`: Defines the sandbox container image.
    - `kubernetes/kind-config.yaml`: Configuration for the Kind cluster itself.
    - `kubernetes/resource-quotas.yaml`: Defines CPU/memory quotas for namespaces.
    - `kubernetes/agent-serviceaccounts.yaml`: Defines the stable ServiceAccount objects for the Blue and Red agents.
    - `kubernetes/demo-*.yaml`: Manifests for the vulnerable demo services deployed within the cluster.
    - `kubernetes/*-rbac.yaml`: RBAC definitions (Roles and Bindings) for the agents (passive and active).
- **`agent/`**: Contains the unified Docker setup for both Blue and Red agents. Includes the `agent-entrypoint.sh` which handles role-specific logic, and the text files defining agent memory, instructions, and playbooks.
- **`poller/`**: Contains the Python script and Dockerfile for the service that continuously monitors the health of the target applications in the Kubernetes cluster.
- **`overseer/`**: Contains the Flask backend and React frontend for the monitoring dashboard. See `overseer/STRUCTURE.md` for its internal details.

## Unified Agent Architecture

Both Blue and Red agents utilize the same Docker image built from `agent/Dockerfile` and the same `agent/agent-entrypoint.sh`. Their distinct behaviors are configured via:
- Environment variables (`AGENT_ROLE`).
- Role-specific memory initialization (`blue-memory-init.txt`, `red-memory-init.txt`).
- Role-specific custom instructions (`blue-custom-instructions.txt`, `red-custom-instructions.txt`).
- Role-specific playbooks (`defense-playbook.txt`, `attack-playbook.txt`).
- Different Kubernetes RBAC permissions defined in `k8s-sandbox/kubernetes/rbac.yaml`.

## Demo Configuration

Key parameters for running this demo (primarily set via `run.sh` arguments or environment variables passed to `docker-compose.yaml`):

- **`PASSIVE_DURATION`**: How long the initial passive (read-only) phase runs (minutes).
- **`ACTIVE_DURATION`**: How long the main active (attack/defense) phase runs (minutes).
- **`VERBOSE`**: Enables detailed logging for agents and other components.
- **`USE_STABLE_VERSIONS`**: Flag to use published PyPI packages (`true`) instead of local development code (`false`) for `vibectl` and dependencies.
- **`VIBECTL_MODEL`**: Specifies the Anthropic model used by the `vibectl` agents.
- **Agent Parameters**:
    - `BLUE_MEMORY_MAX_CHARS`/`RED_MEMORY_MAX_CHARS`: Controls context window size.
    - `BLUE_ACTION_PAUSE_TIME`/`RED_ACTION_PAUSE_TIME`: Pause between agent actions.

*(Note: API Key configuration (`VIBECTL_ANTHROPIC_API_KEY`) is handled according to the main project's standards and passed via environment variables).*

## Safety Measures

- The demo runs in an isolated Docker network.
- The Red Agent operates under specific RBAC constraints defined in `k8s-sandbox/kubernetes/rbac.yaml` to prevent actions outside the intended scope (e.g., attacking the monitoring infrastructure or the host system).
- The entire environment can be easily created and destroyed via `run.sh` or `make`.
