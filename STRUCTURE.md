# Project Structure

This document provides a comprehensive overview of the project's structure and
organization.

## Directory Layout

### Core Package (`vibectl/`)
- `cli.py` - Main command-line interface implementation
  - Core commands: get, describe, logs, create, cluster-info, version
  - Configuration and utility functions
- `prompt.py` - Prompt templates and LLM interaction logic
  - Templates for each command type
  - Formatting instructions
- `config.py` - Configuration management and settings
- `__init__.py` - Package initialization and version information

### Testing (`tests/`)
Contains test files and test resources for the project.

### Type Information (`typings/`)
Custom type definitions and type stubs.

### Development Configuration
- `.vscode/` - VS Code editor settings
- `.cursor/` - Cursor IDE configuration and rules
  - `rules/` - Project-specific Cursor rules
- `.pre-commit-config.yaml` - Pre-commit hook configuration
- `pyproject.toml` - Python project configuration and dependencies
- `Makefile` - Build and development automation

### Nix Development Environment
- `flake.nix` - Nix development environment definition
- `flake.lock` - Locked dependencies for Nix environment
- `.envrc` - direnv configuration for environment activation

### Cache Directories
- `.mypy_cache/` - MyPy type checking cache
- `.ruff_cache/` - Ruff linter cache
- `.pytest_cache/` - pytest cache
- `.venv/` - Python virtual environment
- `__pycache__/` - Python bytecode cache

## Key Files

### Project Configuration
- `pyproject.toml` - Defines project metadata, dependencies, and tool configurations
- `.pre-commit-config.yaml` - Git hooks for code quality checks
- `Makefile` - Development workflow automation

### Documentation
- `README.md` - Project overview and getting started guide
- `STRUCTURE.md` - This file, documenting project organization
- `LICENSE` - Project license information

## Development Workflow

The project uses several tools for development:
1. Nix/direnv for reproducible development environments
2. pre-commit hooks for code quality
3. pytest for testing
4. MyPy for type checking
5. Ruff for linting
6. VS Code/Cursor as recommended IDEs

## Build and Deployment

The project is structured as a Python package with:
- Source code in `vibectl/`
- Development tools configured in project root
- Tests separated in `tests/` directory
- Type information in `typings/`

Dependencies are managed through:
1. `pyproject.toml` for Python dependencies
2. `flake.nix` for development environment
3. Virtual environment in `.venv/`
