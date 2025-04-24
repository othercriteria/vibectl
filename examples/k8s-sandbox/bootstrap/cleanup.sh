#!/usr/bin/env bash
# This script works with both bash and zsh
#
# Usage: ./cleanup.sh
#
# Cleans up all demo containers, build containers, and volumes. Optionally removes custom images.

# Continue on errors but with warnings
set -uo pipefail

echo "=== Cleaning up vibectl bootstrap demo ==="

# Remove main demo container(s)
for cname in $(docker ps -a --format '{{.Names}}' | grep '^vibectl-k3d-demo$'); do
    echo "Cleaning up container: $cname"
    docker rm -f "$cname" 2>/dev/null || true
done

# Remove build containers (ollama-model)
for cname in $(docker ps -a --format '{{.Names}}' | grep '^bootstrap-ollama-model'); do
    echo "Cleaning up build container: $cname"
    docker rm -f "$cname" 2>/dev/null || true
done

# Remove volumes associated with the demo
if docker volume ls -q | grep -q "^bootstrap-status$"; then
    echo "Removing docker volume: bootstrap-status"
    docker volume rm -f bootstrap-status 2>/dev/null || true
fi

# Clean up any port-forwarding processes
if pgrep -f "kubectl port-forward.*ollama" > /dev/null; then
    echo "Stopping kubectl port-forward processes."
    pkill -f "kubectl port-forward.*ollama" 2>/dev/null || true
fi

# Optionally remove custom vibectl-ollama images
OLLAMA_IMAGES=$(docker images --format '{{.Repository}}:{{.Tag}}' | grep '^vibectl-ollama:')
if [ -n "$OLLAMA_IMAGES" ]; then
    echo
    echo "The following custom vibectl-ollama images are present:"
    echo "$OLLAMA_IMAGES"
    read -p "Do you want to remove these images as well? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        for img in $OLLAMA_IMAGES; do
            echo "Removing image: $img"
            docker rmi -f "$img" 2>/dev/null || true
        done
    else
        echo "Leaving custom images in place."
    fi
fi

# Optionally remove k3d system containers
K3D_CONTAINERS=$(docker ps -a --format '{{.Names}}' | grep '^k3d-vibectl-demo-')
if [ -n "$K3D_CONTAINERS" ]; then
    echo
    echo "The following k3d system containers are still running:"
    echo "$K3D_CONTAINERS"
    read -p "Do you want to remove these k3d containers as well? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        for cname in $K3D_CONTAINERS; do
            echo "Removing k3d system container: $cname"
            if ! docker rm -f "$cname" 2>/dev/null; then
                echo "Warning: Failed to remove container $cname. You may need to remove it manually."
            fi
        done
    else
        echo "Leaving k3d system containers in place."
    fi
fi

echo "=== Cleanup complete! ==="
