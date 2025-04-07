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
  - Type-safe configuration handling
  - Validation and type conversion
  - Theme and output settings management
- `console.py` - Console output management and formatting
  - Typed methods for different output types (errors, warnings, notes, etc.)
  - Theme support and styling configuration
  - Reusable methods for common output patterns
- `command_handler.py` - Common command handling patterns
  - Reusable utilities for command execution
  - Standardized error handling and output processing
  - Common kubectl interaction patterns
- `output_processor.py` - Token limits and output preparation
  - Specialized processing for different output types (logs, YAML, JSON)
  - Intelligent output format detection
  - Token limit management and smart truncation
- `__init__.py` - Package initialization and version information

### Testing (`tests/`)
Contains test files and test resources for the project.

- Coverage tracking with pytest-cov
- Target of 100% test coverage for all code
- `.coveragerc` - Configuration for coverage measurement and reporting
- Exclusions must be documented with inline comments
- Coverage reports generated in XML and terminal formats

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

## Architecture

### Console Management
The project implements a structured console management system for output:

1. `console.py` provides a `ConsoleManager` class with:
   - Typed methods for different output types (errors, warnings, notes)
   - Theme support with multiple pre-defined themes (default, dark, light, accessible)
   - Formatted messages with consistent styling
   - Table rendering for structured data

2. `output_processor.py` handles specialized output processing:
   - Automatic detection of output format (JSON, YAML, logs, plain text)
   - Format-specific processing for Kubernetes resources
   - Smart truncation of large outputs for LLM consumption
   - Token limit management for LLM inputs

3. `command_handler.py` centralizes command execution:
   - Standardized kubectl interaction code
   - Common patterns for handling output and errors
   - Streamlined handling of LLM responses
   - Unified configuration and flag handling

### Type Safety
The codebase uses extensive type annotations:
- Generic type parameters for flexible and type-safe interfaces
- TypeVar for flexible return type annotation
- Type casting where appropriate
- Comprehensive type hints for function parameters and return values

### Configuration System
The project uses a structured configuration system:
- Config values with validation and type conversion
- Configuration persistence with file-based storage
- Theme configuration with multiple pre-defined themes
- Custom instructions for vibe prompts
- CLI commands for configuration management

## Development Workflow

The project uses several tools for development:
1. Nix/direnv for reproducible development environments
2. pre-commit hooks for code quality
3. pytest for testing
   - pytest-cov for coverage measurement
   - Coverage requirements enforced at commit time
   - Documented exclusions with `# pragma: no cover - reason`
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
