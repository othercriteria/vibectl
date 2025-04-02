.PHONY: help format lint typecheck test check clean install install-dev install-pre-commit
.DEFAULT_GOAL := help

PYTHON_FILES = vibectl tests

help:  ## Display this help message
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} \
		/^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } \
		/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

install:  ## Install development dependencies
	pip install -e ".[dev]"

install-dev: install-pre-commit
	python -m pip install -e ".[dev]"
	python -m pip install pydantic  # Ensure pydantic is installed

install-pre-commit:
	python -m pip install pre-commit
	pre-commit install

format:  ## Format code using ruff
	pre-commit run ruff --all-files
	pre-commit run ruff-format --all-files

lint:  ## Lint and fix code using ruff
	pre-commit run --all-files

typecheck:  ## Run static type checking using mypy
	mypy $(PYTHON_FILES)

test:  ## Run tests using pytest
	pytest

check: install format lint typecheck test  ## Run all code quality checks and tests

clean:  ## Clean up python cache files
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
