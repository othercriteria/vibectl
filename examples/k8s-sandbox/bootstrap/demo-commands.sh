#!/usr/bin/env bash
set -uo pipefail

container_name="vibectl-k3d-demo"

echo
echo "==== Running demo commands ===="
echo

echo "1. Checking vibectl environment"
docker exec -it $container_name vibectl config show
echo

echo "2. Basic LLM-powered Kubernetes commands"
docker exec -it $container_name vibectl get pods
docker exec -it $container_name vibectl describe deployment
echo

echo "3. Natural language and AI-powered commands"
docker exec -it $container_name vibectl vibe --yes "How can I optimize my Kubernetes deployments?"
docker exec -it $container_name vibectl vibe --yes "Show me pods with high restarts"
echo

echo "4. Memory features"
docker exec -it $container_name vibectl memory show
docker exec -it $container_name vibectl memory set "Running backend deployment in staging namespace"
docker exec -it $container_name vibectl memory show
docker exec -it $container_name vibectl vibe --yes
docker exec -it $container_name vibectl memory show
echo
