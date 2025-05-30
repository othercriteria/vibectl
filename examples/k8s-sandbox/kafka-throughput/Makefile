# Makefile for Kafka Throughput Demo

# Determine docker compose command (handles docker-compose vs docker compose)
COMPOSE_CMD := docker-compose
ifeq (, $(shell command -v docker-compose 2> /dev/null))
    COMPOSE_CMD := docker compose
endif

# Ensure run.sh is executable
RUN_SH := ./run.sh
$(shell chmod +x $(RUN_SH) > /dev/null 2>&1)

# Get Docker GID using the helper flag in run.sh -> REMOVED: run.sh handles this internally now.
# We need to export it so it's available to the compose command in the build target
# export DOCKER_GID := $(shell $(RUN_SH) --get-gid)

# Get list of services from compose file
# Filter out top-level network/volume definitions if any
# Ignore stderr to suppress unset variable warnings during parsing
# SERVICES := $(shell $(COMPOSE_CMD) config --services 2>/dev/null)
# Hardcode services to avoid potential side effects of `config` command
SERVICES := k8s-sandbox producer consumer kafka-demo-ui kminion

# Default target: Show help
.PHONY: help
help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'
	@echo ""
	@echo "Available services for logs-<service> and shell-<service> actions:"
	@echo "  $(SERVICES)"

# Build images
# Pass DOCKER_GID as build-arg, using the value detected via run.sh
.PHONY: build
build: ## Build all Docker images (using DOCKER_GID=$(DOCKER_GID))
	@echo "🛠️ Building Docker images via ./run.sh --build-only..."
	./run.sh --build-only

# Start services via run.sh
.PHONY: up
up: ## Start services via run.sh (handles GID, API key, Cluster ID, build, up, wait)
	@echo "🚀 Launching demo via ./run.sh..."
	./run.sh

# Stop services but keep k3d cluster
.PHONY: down
down: ## Stop services but keep k3d cluster (use clean-cluster to remove everything)
	@echo "🛑 Stopping demo services (keeping k3d cluster)..."
	$(COMPOSE_CMD) -f compose.yml down --remove-orphans --timeout 30 2>/dev/null || true

# Full cleanup (using Docker commands) for k3d cluster (no k3d binary assumed)
.PHONY: docker-clean-k3d
docker-clean-k3d: ## Remove (force) all k3d containers, networks, and volumes (using Docker commands)
	@echo "🧹 (Docker) Cleaning up k3d cluster (containers, networks, volumes) ..."
	@docker ps -a --filter "name=k3d-" -q | xargs --no-run-if-empty docker rm -f
	@docker network ls --filter "name=k3d-" -q | xargs --no-run-if-empty docker network rm
	@docker volume ls --filter "name=k3d-" -q | xargs --no-run-if-empty docker volume rm

# Full cleanup (stop services and remove k3d cluster via Docker)
.PHONY: clean-cluster
clean-cluster: down docker-clean-k3d ## Stop services and remove k3d cluster (using Docker commands)
	@echo "✅ Demo services stopped and k3d cluster (containers, networks, volumes) removed."

# Show status
.PHONY: ps
ps: ## Show status of running services
	$(COMPOSE_CMD) ps

# Follow all logs
.PHONY: logs
logs: ## Follow logs for all services
	$(COMPOSE_CMD) logs -f

# Generate log targets for each service dynamically
.PHONY: $(addprefix logs-,$(SERVICES))
$(addprefix logs-,$(SERVICES)): logs-%: ## Follow logs for a specific service (e.g., make logs-producer)
	@echo "🪵 Following logs for $*..."
	$(COMPOSE_CMD) logs -f $*

# Generate shell targets for each service dynamically
# Tries /bin/bash first, then falls back to /bin/sh
.PHONY: $(addprefix shell-,$(SERVICES))
$(addprefix shell-,$(SERVICES)): shell-%: ## Open a shell in a specific service (e.g., make shell-producer)
	@echo "🐚 Opening shell in $*..."
	$(COMPOSE_CMD) exec $* /bin/bash || $(COMPOSE_CMD) exec $* /bin/sh

# Prevent Make from deleting intermediate files and show commands
.SECONDARY:
.VERBOSE:

# Explicitly declare pattern rules as .PHONY if they aren't file targets
.PHONY: logs-% shell-%
