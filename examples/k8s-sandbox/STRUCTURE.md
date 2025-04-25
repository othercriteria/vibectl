# Kubernetes Sandbox Environments

This directory contains sandbox environments for testing and demonstrating vibectl's capabilities in Kubernetes environments. Currently, it includes three main demos:

1. **CTF (Capture The Flag)**: A challenge-based learning environment
2. **Chaos Monkey**: A red team vs. blue team competitive scenario
3. **Bootstrap Demo**: Self-contained k3d (K3s in Docker) + Ollama environment, with vibectl configured to use the local LLM and automated demonstration of Kubernetes analysis

## Directory Structure

- `ctf/`: Capture The Flag style sandbox (original k8s-sandbox demo)
  - See [ctf/STRUCTURE.md](ctf/STRUCTURE.md) for detailed documentation
- `chaos-monkey/`: Red team vs. blue team competitive environment
  - See [chaos-monkey/STRUCTURE.md](chaos-monkey/STRUCTURE.md) for detailed documentation
- `bootstrap/`: Self-contained k3d (K3s in Docker) + Ollama environment, with vibectl configured to use the local LLM and automated demonstration of Kubernetes analysis
  - See [bootstrap/STRUCTURE.md](bootstrap/STRUCTURE.md) for detailed documentation

## Common Features

Both environments share several characteristics:

- Docker-based isolation for running Kubernetes clusters
- Kind for creating lightweight Kubernetes clusters
- Docker Compose for orchestrating multi-container demos
- API key management for vibectl model access
- Clean shutdown and resource management

## Key Differences

### CTF Environment
- Focus on learning and completing challenges
- Single vibectl agent working on predefined tasks
- Success measured by completing all challenges
- Difficulty levels adjust challenge complexity
- Stateless model: each run starts fresh with predefined challenges

### Chaos Monkey Environment
- Focus on system resilience and response to disruption
- Two competing vibectl agents (red and blue teams)
- Success measured by service uptime and recovery metrics
- Real-time performance tracking by an overseer component
- Dynamic environment where both agents adapt to each other's actions

## Container Setup

Both environments use Docker containers, but with different approaches:

- CTF: Single container with Kind and vibectl for solving challenges
- Chaos Monkey: Multiple containers:
  - Service container for the workload and Kind cluster
  - Blue agent container for the defender
  - Red agent container for the attacker
  - Poller container for uptime tracking
  - Overseer container for dashboard, metrics and coordination

## Getting Started

Each environment has its own README.md with specific setup instructions. In general:

1. Choose which environment to run (ctf, chaos-monkey, or bootstrap)
2. Navigate to the chosen directory
3. Follow the setup instructions in the README.md file
4. Ensure you have the required API keys configured
