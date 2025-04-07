# Project Structure

This document provides an overview of the project's structure and organization.

## Directory Layout

### Core Package (`vibectl/`)
- `cli.py` - Command-line interface implementation
- `prompt.py` - Prompt templates and LLM interaction logic
- `config.py` - Configuration management and settings
- `console.py` - Console output formatting and management
- `command_handler.py` - Common command handling patterns
- `output_processor.py` - Token limits and output preparation
- `__init__.py` - Package initialization and version information

### Testing (`tests/`)
- Test files and test resources
- Coverage tracking with pytest-cov
- `.coveragerc` - Coverage measurement configuration

### Type Information (`typings/`)
- Custom type definitions and type stubs

### Configuration
- `.vscode/` - VS Code editor settings
- `.cursor/` - Cursor IDE configuration and rules
  - `rules/` - Project-specific Cursor rules
    - `feature-worktrees.mdc` - Guidelines for using Git worktrees for feature development
- `.pre-commit-config.yaml` - Pre-commit hook configuration
- `pyproject.toml` - Python project configuration and dependencies
- `Makefile` - Build and development automation
- `flake.nix` & `flake.lock` - Nix development environment
- `.envrc` - direnv configuration for environment activation

## Key Files

- `README.md` - Project overview and getting started guide
- `STRUCTURE.md` - This file, documenting project organization
- `LICENSE` - Project license information

## Architecture

### Console Management
1. `console.py` - Typed output methods with theme support
2. `output_processor.py` - Format detection and intelligent processing
3. `command_handler.py` - Standardized command execution

### Type Safety
- Extensive type annotations throughout codebase
- Generic type parameters and TypeVar for flexible interfaces

### Configuration System
- Type-safe configuration with validation
- Theme configuration and custom prompt instructions

## Development Workflow

1. Git worktrees for parallel feature development
   - Feature branches created from main
   - Worktrees placed in `../worktrees/` directory
   - One feature per worktree for isolated development
2. Nix/direnv for reproducible development environments
3. pre-commit hooks for code quality
4. pytest for testing with coverage requirements
5. MyPy for type checking
6. Ruff for linting
7. VS Code/Cursor as recommended IDEs

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
