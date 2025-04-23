#!/usr/bin/env bash
# This script works with both bash and zsh
#
# Usage: ./cleanup.sh
#
# Only the bootstrap-status volume is removed. Ollama model persistence is not supported in this demo.

# Continue on errors but with warnings
set -uo pipefail

echo "=== Cleaning up vibectl bootstrap demo ==="

# Clean up containers directly
echo "Cleaning up containers..."
docker rm -f vibectl-k3d-demo 2>/dev/null || true
docker rm -f vibectl-bootstrap 2>/dev/null || true  # Legacy name

# Remove k3d containers related to the demo
for cname in k3d-vibectl-demo-serverlb k3d-vibectl-demo-server-0; do
    if docker ps -a --format '{{.Names}}' | grep -q "^$cname$"; then
        echo "Removing k3d container: $cname"
        docker rm -f "$cname" 2>/dev/null || true
    fi
done

# Remove volumes associated with the demo
echo "Removing docker volume: bootstrap-status"
if docker volume rm -f bootstrap-status 2>/dev/null; then
    echo "Removed volume: bootstrap-status"
else
    echo "Warning: Could not remove volume: bootstrap-status (it may not exist or is in use)"
fi

# Clean up any port-forwarding processes
echo "Stopping any kubectl port-forward processes..."
if pkill -f "kubectl port-forward.*ollama" 2>/dev/null; then
    echo "Stopped kubectl port-forward processes."
else
    echo "No kubectl port-forward processes found."
fi

echo "=== Cleanup complete! ==="
