.PHONY: run build up down logs blue-logs red-logs poller-logs overseer-logs sandbox-logs clean help

# Default values for environment variables
export PASSIVE_DURATION ?= 5
export ACTIVE_DURATION ?= 25
export VERBOSE ?= false
export USE_STABLE_VERSIONS ?= false

# Help command
help:
	@echo "Usage: make [target] [VARIABLE=value]..."
	@echo ""
	@echo "Targets:"
	@echo "  run                   Run the full demo (builds if necessary)"
	@echo "  build                 Build all Docker images"
	@echo "  up                    Start services without building (requires prior build)"
	@echo "  down                  Stop and remove containers"
	@echo "  logs                  Tail logs for all services"
	@echo "  blue-logs             Tail logs for the blue agent"
	@echo "  red-logs              Tail logs for the red agent"
	@echo "  poller-logs           Tail logs for the poller"
	@echo "  overseer-logs         Tail logs for the overseer"
	@echo "  sandbox-logs          Tail logs for the k8s-sandbox setup"
	@echo "  clean                 Remove containers, volumes, and Kind cluster"
	@echo "  help                  Show this help message"
	@echo ""
	@echo "Variables:"
	@echo "  PASSIVE_DURATION     Passive phase duration in minutes (default: 5)"
	@echo "  ACTIVE_DURATION      Active phase duration in minutes (default: 25)"
	@echo "  VERBOSE              Enable verbose logging (true/false, default: false)"
	@echo "  USE_STABLE_VERSIONS  Use stable PyPI packages (true/false, default: false)"
	@echo ""
	@echo "Examples:"
	@echo "  make run PASSIVE_DURATION=10 ACTIVE_DURATION=50 VERBOSE=true"
	@echo "  make logs"
	@echo "  make clean"

# Default target
run:
	@echo "Running Chaos Monkey Demo..."
	./run.sh \
		--passive-duration $(PASSIVE_DURATION) \
		--active-duration $(ACTIVE_DURATION) \
		$$( [ "$(VERBOSE)" = "true" ] && echo "--verbose" ) \
		$$( [ "$(USE_STABLE_VERSIONS)" = "true" ] && echo "--use-stable-versions" )

# Build containers
build:
	docker compose build

# Stop and remove containers
clean:
	docker compose down -v

# View logs
logs:
	docker compose logs -f

# Check status
status:
	docker compose ps

# Restart containers
restart:
	docker compose restart

# Stop containers
stop:
	docker compose stop

# Individual container logs
blue-logs:
	docker compose logs -f blue-agent

red-logs:
	docker compose logs -f red-agent

overseer-logs:
	docker compose logs -f overseer

poller-logs:
	docker compose logs -f poller

services-logs:
	docker compose logs -f k8s-sandbox

# Default target is help if no arguments are provided
ifeq ($(MAKECMDGOALS),)
.DEFAULT_GOAL := run
endif
