#!/usr/bin/env bash
# This script works with both bash and zsh

# Fail immediately on any error
set -euo pipefail

# Default values
: "${OLLAMA_MODEL:=tinyllama}"
: "${K3D_CLUSTER_NAME:=vibectl-demo}"
: "${RESOURCE_LIMIT_CPU:=}"
: "${RESOURCE_LIMIT_MEMORY:=6Gi}"
: "${USE_STABLE_VERSIONS:=false}"
: "${VIBECTL_VERSION:=0.5.0}"
: "${LLM_VERSION:=0.24.2}"

# Try to determine the docker group ID for proper permissions
if command -v getent &> /dev/null; then
    # Linux systems with getent
    DOCKER_GID=$(getent group docker | cut -d: -f3)
elif command -v stat &> /dev/null; then
    # macOS or other systems with stat
    DOCKER_GID=$(stat -f "%g" /var/run/docker.sock 2>/dev/null)
else
    # Try to get directly
    DOCKER_GID=$(stat -c "%g" /var/run/docker.sock 2>/dev/null)
fi

# Default to 999 if detection fails
DOCKER_GID=${DOCKER_GID:-999}
echo "Detected Docker GID: ${DOCKER_GID}"

# Process command-line arguments
for arg in "$@"; do
    case $arg in
        --use-stable-versions)
            USE_STABLE_VERSIONS=true
            shift
            ;;
        --help)
            echo "Usage: $0 [options]"
            echo "Options:"
            echo "  --use-stable-versions  Use stable versions from PyPI instead of source"
            echo "  --help                 Show this help message"
            echo
            echo "Environment variables:"
            echo "  OLLAMA_MODEL           The Ollama model to use (default: ${OLLAMA_MODEL})"
            echo "  K3D_CLUSTER_NAME       The name of the K3D cluster (default: ${K3D_CLUSTER_NAME})"
            echo "  RESOURCE_LIMIT_CPU     CPU limit for Ollama (default: ${RESOURCE_LIMIT_CPU})"
            echo "  RESOURCE_LIMIT_MEMORY  Memory limit for Ollama (default: ${RESOURCE_LIMIT_MEMORY})"
            echo "  VIBECTL_VERSION        Version of vibectl to install (default: ${VIBECTL_VERSION})"
            echo "  LLM_VERSION            Version of llm to install (default: ${LLM_VERSION})"
            echo "  DOCKER_GID             Docker group ID (detected: ${DOCKER_GID})"
            exit 0
            ;;
    esac
done
# Clear positional arguments so they are not passed to docker compose
set --

# Check for docker
if ! command -v docker &> /dev/null; then
    echo "Error: docker is not installed or not in PATH"
    exit 1
fi

# Check for docker socket
if [ ! -S /var/run/docker.sock ]; then
    echo "Error: Docker socket /var/run/docker.sock not found"
    exit 1
fi

# Check docker socket permissions
if [ ! -r /var/run/docker.sock ]; then
    echo "Warning: Docker socket may not be readable by your user"
    echo "You may need to run this script with sudo or add your user to the docker group"
fi

# Check for docker compose
if ! (command -v docker-compose &> /dev/null || docker compose version &> /dev/null); then
    echo "Error: docker compose is not installed or not in PATH"
    exit 1
fi

# Check for sufficient memory - simplified to avoid bc
if command -v free &> /dev/null; then
    AVAILABLE_MEM_KB=$(free | grep Mem | awk '{print $7}')
    # Simple integer division to get GB (removes decimals)
    AVAILABLE_MEM_GB=$((AVAILABLE_MEM_KB / 1024 / 1024))
    MIN_MEM_GB=5

    if [[ ${AVAILABLE_MEM_GB} -lt ${MIN_MEM_GB} ]]; then
        echo "Warning: Only ${AVAILABLE_MEM_GB}GB of memory available"
        echo "Recommendation: At least ${MIN_MEM_GB}GB of memory is recommended for running this demo"
        echo
        read -p "Do you want to continue anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Exiting as requested"
            exit 1
        fi
    fi
fi

# Ensure we're in the script directory
cd "$(dirname "$0")"

# Use docker-compose or docker compose depending on what's available
if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    COMPOSE_CMD="docker compose"
fi

# Use a tempfile for the compose file in the current directory to ensure Docker build context works
COMPOSE_FILE=$(mktemp "$(pwd)/vibectl-compose-XXXXXX.yml")
trap 'rm -f "$COMPOSE_FILE"' EXIT

# Create the compose file
image_tag=$(echo "${OLLAMA_MODEL}" | tr ':/. ' '_')
export IMAGE_TAG=${image_tag}
cat > ${COMPOSE_FILE} <<EOF
services:
  ollama-model:
    build:
      context: .
      dockerfile: Dockerfile.ollama-model
      args:
        OLLAMA_MODEL: ${OLLAMA_MODEL}
    image: vibectl-ollama:${image_tag}

  bootstrap:
    build:
      context: .
      dockerfile: Dockerfile
      args:
        DOCKER_GID: ${DOCKER_GID}
    container_name: vibectl-k3d-demo
    privileged: true
    environment:
      - OLLAMA_MODEL=${OLLAMA_MODEL}
      - IMAGE_TAG=${IMAGE_TAG}
      - K3D_CLUSTER_NAME=${K3D_CLUSTER_NAME}
      - USE_STABLE_VERSIONS=${USE_STABLE_VERSIONS}
      - VIBECTL_VERSION=${VIBECTL_VERSION}
      - LLM_VERSION=${LLM_VERSION}
      - DOCKER_GID=${DOCKER_GID}
      - RESOURCE_LIMIT_CPU=${RESOURCE_LIMIT_CPU}
      - RESOURCE_LIMIT_MEMORY=${RESOURCE_LIMIT_MEMORY}
    volumes:
      - ../../..:/home/bootstrap/vibectl-src:ro
      - /var/run/docker.sock:/var/run/docker.sock
      - bootstrap-status:/tmp/status
    ports:
      - "11434:11434"
    working_dir: /home/bootstrap
    command: ./bootstrap-entrypoint.sh
    depends_on:
      - ollama-model

volumes:
  bootstrap-status:
EOF

# Build all images first
${COMPOSE_CMD} -f ${COMPOSE_FILE} build --build-arg DOCKER_GID=${DOCKER_GID} --build-arg OLLAMA_MODEL=${OLLAMA_MODEL}
${COMPOSE_CMD} -f ${COMPOSE_FILE} up -d

# Simplified health check: wait for both phase1_complete and phase2_complete
container_name="vibectl-k3d-demo"
max_attempts=600  # 10 minutes
attempt=1
echo "Waiting for bootstrap container to complete setup..."
while [ $attempt -le $max_attempts ]; do
    # Check if container is still running
    if ! docker ps | grep -q ${container_name}; then
        echo "Error: Bootstrap container is no longer running"
        echo "Showing container logs:"
        docker logs ${container_name}
        exit 1
    fi
    # Check for both phase status files
    if docker exec ${container_name} test -f /home/bootstrap/status/phase1_complete \
        && docker exec ${container_name} test -f /home/bootstrap/status/phase2_complete; then
        echo "Bootstrap setup completed successfully!"
        break
    fi
    if [ $((attempt % 10)) -eq 0 ]; then
        echo "Still waiting for bootstrap to complete... (${attempt}/${max_attempts})"
    fi
    attempt=$((attempt + 1))
    sleep 1
done
if [ $attempt -gt $max_attempts ]; then
    echo "Error: Bootstrap setup timed out after $max_attempts seconds"
    docker logs ${container_name}
    exit 1
fi

echo
echo "==== Demo launched successfully! ===="
echo "Kubernetes cluster with K3d is running within the container 'vibectl-k3d-demo'"
echo "Ollama is running inside the Kubernetes cluster and accessible at http://localhost:11434"
echo "You can continue to use vibectl by running:"
echo "  docker exec -it vibectl-k3d-demo vibectl <command>"
echo
echo "To stop and clean up the demo environment:"
echo "  ./cleanup.sh"

# Add a note about demo-commands.sh
echo "To run a guided demonstration of vibectl's capabilities, run:"
echo "  ./demo-commands.sh"
echo
