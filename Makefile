.PHONY: help format lint typecheck dmypy-status dmypy-start dmypy-stop dmypy-restart test test-serial test-coverage ci-check wheel release publish check-coverage clean update-deps install install-dev install-pre-commit update-changelog grpc-gen grpc-clean grpc-check dev-install lock bump-patch bump-minor bump-major
.DEFAULT_GOAL := help

# Determine project virtualenv Python
VENV_PY=.venv/bin/python
# Use uv's pip wrapper to install into the project virtualenv
PIP=uv pip install -p $(VENV_PY) --break-system-packages

# --- New: ensure virtual environment exists before any pip operations ---
.PHONY: venv
venv: ## Create local Python virtual environment (.venv) if it does not exist
	@if [ ! -d .venv ]; then \
		uv venv .venv; \
	fi

PYTHON_FILES = vibectl tests

help:  ## Display this help message
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} \
		/^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } \
		/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Installation and Setup

install: venv  ## Install package and dependencies
	$(PIP) -e "."

install-dev: venv  ## Install development dependencies and pre-commit hooks
	# Ensure latest pip with system package overrides
	$(PIP) --upgrade pip
	$(PIP) -e ".[dev]"
	$(PIP) pydantic  # Ensure pydantic is installed (workaround for pydantic stubs)
	$(MAKE) install-pre-commit

install-pre-commit:  ## Install pre-commit hooks
	$(PIP) pre-commit
	pre-commit install

update-deps:  ## Update pip and all dependencies
	$(PIP) --upgrade pip
	$(PIP) --upgrade -e ".[dev]"

##@ Development Tools

format:  ## Format code using ruff
	pre-commit run ruff --all-files
	pre-commit run ruff-format --all-files

lint:  ## Lint and fix code using ruff and all pre-commit hooks
	pre-commit run --all-files

# Static type checking -----------------------------------------------------
# Use dmypy for speed **but** force it to run with the exact Python interpreter
# inside our project virtualenv.  This avoids mismatches that previously caused
# missing-plugin errors (e.g. pydantic).

MYPY_DMYPY = $(VENV_PY) -m mypy.dmypy

typecheck: venv dmypy-start  ## Run static type checking using dmypy, fallback to mypy
	@$(MYPY_DMYPY) run -- $(PYTHON_FILES) || { \
		echo "dmypy failed, falling back to regular mypy"; \
		$(VENV_PY) -m mypy $(PYTHON_FILES); \
	}

##@ Type Checking Daemon Management
dmypy-status: venv  ## Show dmypy status (uses virtualenv interpreter)
	@$(MYPY_DMYPY) status || true

dmypy-start: venv  ## Start dmypy daemon with venv interpreter if not running
	@# Install mypy inside .venv on CI cold-start if it is missing
	@if [ ! -x "$(VENV_PY%/python)%/mypy" ] && ! $(VENV_PY) -m pip show mypy >/dev/null 2>&1; then \
		$(PIP) mypy; \
	fi
	@$(MYPY_DMYPY) status >/dev/null 2>&1 || $(MYPY_DMYPY) start

dmypy-stop: venv  ## Stop dmypy daemon
	@$(MYPY_DMYPY) status >/dev/null 2>&1 && $(MYPY_DMYPY) stop || true

dmypy-restart: dmypy-stop dmypy-start  ## Restart dmypy daemon

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

# Consolidated CI check target – run lint, typecheck, and full test suite (no auto-formatting)
ci-check: lint typecheck test-coverage  ## Run linter, static checks, and tests with coverage (intended for CI)

check: install-dev format lint typecheck test  ## Local convenience target that also formats code

check-coverage: install-dev format lint typecheck test-coverage  ## Local convenience target with coverage report

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

# Version bump targets removed – use manual edit or future make publish flow

##@ Packaging & Release

# Build wheel and sdist using the standard Python build module
wheel:  ## Build wheel and sdist into dist/
	$(PIP) --upgrade build  # ensure build is present
	python -m build

# ---------------------------------------------------------------------------
# Maintenance helpers
# ---------------------------------------------------------------------------

clean: ## Remove build artifacts and caches
	rm -rf build dist *.egg-info .pytest_cache

# Dry-run release convenience wrapper (build + basic checks)
release: clean ci-check wheel  ## Build distributions, show next manual tag command
	@VERSION=$$(python scripts/version.py); \
	 echo "Distributions built in dist/ (version $$VERSION)."; \
	 echo "Run: python scripts/version.py --tag --push --no-dry-run  to tag & push when ready.";

# gRPC code generation
grpc-gen: ## Generate gRPC Python stubs from proto definitions
	@echo "Generating gRPC Python stubs..."
	$(VENV_PY) -m grpc_tools.protoc \
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
	@$(VENV_PY) -c "import grpc_tools.protoc; print('✓ grpc_tools available')" || (echo "✗ grpc_tools not available - install grpcio-tools" && exit 1)
	@$(VENV_PY) -c "import grpc; print('✓ grpc available')" || (echo "✗ grpc not available - install grpcio" && exit 1)
	@echo "All gRPC dependencies available"

# Ensure .venv exists with uv and generate gRPC stubs after deps
dev-install: venv install-dev grpc-check grpc-gen ## Install development dependencies and generate gRPC code

## Dependency management (uv.lock is canonical; pylock.toml is derived)
lock:  ## Regenerate lock files (uv.lock + pylock.toml)
	uv lock --upgrade
	uv pip compile pyproject.toml --extra=dev \
		--output-file=pylock.toml \
		--format=pylock.toml \
		--python 3.11

# optional DRY_RUN env var controls whether bump writes to file
DRY_RUN?=1
BUMP_FLAGS=$(if $(filter 0,$(DRY_RUN)),--no-dry-run,)

bump-patch: update-changelog ## Bump patch version via scripts/version.py
	python scripts/version.py --bump patch $(BUMP_FLAGS)

bump-minor: update-changelog ## Bump minor version via scripts/version.py
	python scripts/version.py --bump minor $(BUMP_FLAGS)

bump-major: update-changelog ## Bump major version via scripts/version.py
	python scripts/version.py --bump major $(BUMP_FLAGS)

# Publish to PyPI (requires credentials in ~/.pypirc or env vars). Controlled by PUBLISH_DRY_RUN (default 1)
PUBLISH_DRY_RUN?=1
PUBLISH_FLAGS=$(if $(filter 0,$(PUBLISH_DRY_RUN)),--no-dry-run,)

publish: release ## Build & upload to PyPI, then tag & push git tag
	@VERSION=$$(python scripts/version.py); \
	 echo "Publishing version $$VERSION to PyPI (PUBLISH_DRY_RUN=$(PUBLISH_DRY_RUN))"; \
	 if [ "$(PUBLISH_DRY_RUN)" = "0" ]; then twine upload dist/*; else echo "[dry-run] twine upload dist/*"; fi; \
	 python scripts/version.py --tag --push $(PUBLISH_FLAGS)
