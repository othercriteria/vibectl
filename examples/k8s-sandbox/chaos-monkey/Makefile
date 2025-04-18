.PHONY: run clean build logs help status restart stop

# Default values for environment variables
export SESSION_DURATION ?= 30
export METRICS_INTERVAL ?= 15
export VERBOSE ?= false

# Help command
help:
	@echo "Chaos Monkey Demo - Make Commands:"
	@echo ""
	@echo "Usage:"
	@echo "  make [command]"
	@echo ""
	@echo "Commands:"
	@echo "  run           Run the demo (default)"
	@echo "  build         Build all containers without starting"
	@echo "  clean         Stop and remove all containers"
	@echo "  logs          View logs from all containers"
	@echo "  status        Check status of containers"
	@echo "  restart       Restart all containers"
	@echo "  stop          Stop all containers"
	@echo "  blue-logs     View logs from blue agent"
	@echo "  red-logs      View logs from red agent"
	@echo "  overseer-logs View logs from overseer"
	@echo "  poller-logs   View logs from poller"
	@echo "  services-logs View logs from services"
	@echo ""
	@echo "Environment Variables:"
	@echo "  SESSION_DURATION     Session duration in minutes (default: 30 min)"
	@echo "  METRICS_INTERVAL     Metrics collection interval in seconds (default: 15 sec)"
	@echo "  VERBOSE              Enable verbose logging (default: false)"
	@echo ""
	@echo "Examples:"
	@echo "  make run SESSION_DURATION=60 VERBOSE=true"
	@echo "  make logs"
	@echo "  make blue-logs"

# Default target
run:
	./run.sh $(if $(filter true,$(VERBOSE)),--verbose) \
             --session-duration $(SESSION_DURATION)

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
