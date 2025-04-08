.PHONY: help format lint typecheck test test-coverage check clean update-deps install install-dev install-pre-commit
.DEFAULT_GOAL := help

PYTHON_FILES = vibectl tests

help:  ## Display this help message
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} \
		/^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } \
		/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Installation and Setup

install:  ## Install package and dependencies
	python -m pip install -e "."

install-dev:  ## Install development dependencies and pre-commit hooks
	python -m pip install -e ".[dev]"
	python -m pip install pydantic  # Ensure pydantic is installed
	$(MAKE) install-pre-commit

install-pre-commit:  ## Install pre-commit hooks
	python -m pip install pre-commit
	pre-commit install

update-deps:  ## Update pip and all dependencies
	python -m pip install --upgrade pip
	python -m pip install --upgrade -e ".[dev]"

##@ Development Tools

format:  ## Format code using ruff
	pre-commit run ruff --all-files
	pre-commit run ruff-format --all-files

lint:  ## Lint and fix code using ruff and all pre-commit hooks
	pre-commit run --all-files

typecheck:  ## Run static type checking using mypy
	mypy $(PYTHON_FILES)

##@ Testing

test:  ## Run tests using pytest
	pytest

test-coverage:  ## Run tests with coverage report
	pytest --cov=vibectl --cov-report=term --cov-report=html --cov-report=xml

##@ Quality and Verification

check: install-dev format lint typecheck test  ## Run all code quality checks and tests

##@ Cleanup

clean:  ## Clean up python cache files and build artifacts
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name "*.egg" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name "dist" -exec rm -rf {} +
	find . -type d -name "build" -exec rm -rf {} +
	rm -rf htmlcov/
	rm -f coverage.xml
	@echo "Cleaned up build artifacts and cache files"
