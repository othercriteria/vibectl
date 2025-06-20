.PHONY: help format lint typecheck test test-serial test-coverage check check-coverage clean update-deps install install-dev install-pre-commit pypi-build pypi-test pypi-upload pypi-release pypi-check bump-patch bump-minor bump-major update-changelog grpc-gen grpc-clean grpc-check dev-install
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

test:  ## Run tests in parallel (default for development)
	./scripts/run_parallel_tests.sh

test-serial:  ## Run tests serially using pytest (slower but more compatible)
	pytest

test-coverage:  ## Run tests with coverage report
	pytest --cov=vibectl --cov-report=term --cov-report=html --cov-report=xml

test-fast:  ## Run tests marked as 'fast' (quick feedback during development)
	pytest -m fast -v

# Even quicker: run all tests except ones marked "slow" and skip coverage collection
test-quick:  ## Ultra-fast feedback – run pytest quietly excluding slow tests, no coverage
	pytest -q -m "not slow"

##@ Quality and Verification

check: install-dev format lint typecheck test  ## Run all code quality checks and tests (with parallel execution)

check-coverage: install-dev format lint typecheck test-coverage  ## Run code quality checks and tests with coverage report

pypi-check:  ## Run code quality checks without reinstalling (for CI/release)
	pre-commit run --all-files
	mypy $(PYTHON_FILES)
	pytest -v  # Run tests with verbose output to easily spot failures

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

##@ Version Management

update-changelog:  ## Update CHANGELOG.md for a new release
	@echo "Please prepare CHANGELOG.md for release by:"
	@echo "  1. Moving 'Unreleased' changes to a new version section with today's date (YYYY-MM-DD)"
	@echo "  2. Organizing changes by type (Added, Changed, Fixed, etc.)"
	@echo "  3. Adding a fresh 'Unreleased' section at the top"
	@read -p "Have you updated the CHANGELOG.md file? (y/n) " answer; \
	if [ "$$answer" != "y" ]; then \
		echo "Please update CHANGELOG.md before continuing"; \
		exit 1; \
	fi

bump-patch: update-changelog  ## Bump patch version (0.0.x)
	@if command -v bump-version >/dev/null 2>&1; then \
		bump-version patch; \
	else \
		python ./bump_version.py patch; \
	fi

bump-minor: update-changelog  ## Bump minor version (0.x.0)
	@if command -v bump-version >/dev/null 2>&1; then \
		bump-version minor; \
	else \
		python ./bump_version.py minor; \
	fi

bump-major: update-changelog  ## Bump major version (x.0.0)
	@if command -v bump-version >/dev/null 2>&1; then \
		bump-version major; \
	else \
		python ./bump_version.py major; \
	fi

##@ PyPI Distribution (NixOS)

pypi-build:  ## Build package distributions for PyPI
	@if command -v pypi-dist >/dev/null 2>&1; then \
		pypi-dist build; \
	else \
		echo "NixOS pypi-dist not found. Running alternate build command..."; \
		python -m pip install --upgrade build; \
		python -m build; \
	fi

pypi-test:  ## Test package in a clean environment
	@if command -v pypi-dist >/dev/null 2>&1; then \
		pypi-dist test; \
	else \
		echo "NixOS pypi-dist not found. Running alternate test command..."; \
		python -m pip install --upgrade build virtualenv; \
		VERSION=$$(grep -Po '^version = "\K[^"]+' pyproject.toml); \
		python -m virtualenv test_env; \
		. test_env/bin/activate && \
		pip install dist/vibectl-$$VERSION-py3-none-any.whl || { pip install llm-anthropic && vibectl --version; }; \
		rm -rf test_env; \
	fi

pypi-upload:  ## Upload package to PyPI
	@if command -v pypi-dist >/dev/null 2>&1; then \
		pypi-dist pypi; \
	else \
		echo "NixOS pypi-dist not found. Running alternate upload command..."; \
		python -m pip install --upgrade twine; \
		twine upload dist/*; \
	fi

pypi-release: clean pypi-check pypi-build pypi-test pypi-upload  ## Run all checks and publish to PyPI
	@echo "Package successfully published to PyPI"
	@if command -v pypi-dist >/dev/null 2>&1; then \
		pypi-dist tag; \
	else \
		echo "NixOS pypi-dist not found. Creating tag manually..."; \
		VERSION=$$(grep -Po '^version = "\K[^"]+' pyproject.toml); \
		git tag "v$$VERSION"; \
		git push origin "v$$VERSION"; \
	fi
	@echo "Release v$$(grep -Po '^version = "\K[^"]+' pyproject.toml) completed!"

# gRPC code generation
grpc-gen: ## Generate gRPC Python stubs from proto definitions
	@echo "Generating gRPC Python stubs..."
	python -m grpc_tools.protoc \
		--python_out=. \
		--grpc_python_out=. \
		--proto_path=. \
		vibectl/proto/llm_proxy.proto
	@echo "gRPC stubs generated successfully"

grpc-clean: ## Clean generated gRPC files
	@echo "Cleaning generated gRPC files..."
	rm -f vibectl/proto/*_pb2.py
	rm -f vibectl/proto/*_pb2_grpc.py
	@echo "Generated gRPC files cleaned"

grpc-check: ## Check if gRPC dependencies are available
	@echo "Checking gRPC dependencies..."
	@python -c "import grpc_tools.protoc; print('✓ grpc_tools available')" || (echo "✗ grpc_tools not available - install grpcio-tools" && exit 1)
	@python -c "import grpc; print('✓ grpc available')" || (echo "✗ grpc not available - install grpcio" && exit 1)
	@echo "All gRPC dependencies available"

# Add grpc-gen as a dependency for development setup
dev-install: install-dev grpc-check grpc-gen ## Install development dependencies and generate gRPC code
