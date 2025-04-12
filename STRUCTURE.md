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
- `memory.py` - Context memory for cross-command awareness
- `model_adapter.py` - Abstraction layer for LLM model interactions
- `utils.py` - Utility functions and helpers
- `__init__.py` - Package initialization and version information

### Testing (`tests/`)
- Test files and test resources
- Coverage tracking with pytest-cov
- `.coveragerc` - Coverage measurement configuration

### Type Information (`typings/`)
- Custom type definitions and type stubs

### Documentation (`docs/`)
- `MODEL_KEYS.md` - Comprehensive guide for model API key management
- Additional documentation files

### Configuration
- `.vscode/` - VS Code editor settings
- `.cursor/` - Cursor IDE configuration and rules
  - `rules/` - Project-specific Cursor rules
    - `feature-worktrees.mdc` - Guidelines for using Git worktrees for feature development
    - `autonomous-commits.mdc` - Defines criteria and behavior for autonomous commits
    - `test-coverage.mdc` - Enforces high test coverage standards with documented exceptions
    - `slow-tests.mdc` - Monitors and enforces resolution of slow tests
    - `dry-test-fixtures.mdc` - Enforces DRY principles in test fixtures
    - `project-structure.mdc` - Standards for maintaining project structure documentation
    - `no-bazel.mdc` - Prohibits Bazel usage and recommendations
    - `python-venv.mdc` - Python project setup guidelines
    - `ruff-preferred.mdc` - Python linting standards with Ruff
    - `rules.mdc` - Standards for organizing Cursor rule files
    - `no-llm-in-tests.mdc` - Prohibits unmocked LLM calls in test code
    - `test-mocking.mdc` - Requirements for mocking external dependencies in tests
- `.pre-commit-config.yaml` - Pre-commit hook configuration
- `pyproject.toml` - Python project configuration and dependencies
- `Makefile` - Build and development automation
- `flake.nix` & `flake.lock` - Nix development environment
- `.envrc` - direnv configuration for environment activation

## Key Files

- `README.md` - Project overview and getting started guide
- `STRUCTURE.md` - This file, documenting project organization
- `LICENSE` - Project license information
- `RULES.md` - Documentation of Cursor rules system
- `docs/MODEL_KEYS.md` - Guide for configuring model API keys
- `CHANGELOG.md` - Documentation of notable changes for each version
- `DISTRIBUTION.md` - Guide for publishing to PyPI
- `bump_version.py` - Script for semantic version management

## Architecture

### Console Management
1. `console.py` - Typed output methods with theme support
2. `output_processor.py` - Format detection and intelligent processing
3. `command_handler.py` - Standardized command execution

### Command Systems
1. `cli.py` - Core command-line interface implementations
   - Get command with standard and vibe-based resource retrieval
   - Describe command for detailed resource information
   - Delete command with confirmation safety and vibe-based deletion
   - Scale command for scaling resource replicas
   - Rollout command group for managing deployment rollouts
   - Memory management commands
   - Configuration and theme commands
2. `prompt.py` - Command-specific prompt templates
   - `PLAN_DELETE_PROMPT` for planning deletions safely
   - `delete_resource_prompt()` for summarizing deletion results
   - `PLAN_SCALE_PROMPT` for planning scaling operations
   - `scale_resource_prompt()` for summarizing scaling results
   - `PLAN_ROLLOUT_PROMPT` for planning rollout operations
   - `rollout_status_prompt()`, `rollout_history_prompt()`, and `rollout_general_prompt()` for summarizing rollout operations
3. `command_handler.py` - Generic command execution patterns
   - Handle confirmation for destructive operations
   - Execute kubectl commands safely
   - Process command output for user feedback

### Memory System
1. `memory.py` - Core memory management with functions for:
   - Getting and setting memory content
   - Enabling/disabling memory updates
   - Clearing memory
   - Updating memory based on command execution
   - Including memory in LLM prompts
2. `config.py` - Memory persistence in configuration
   - Stores memory content as a string
   - Manages memory settings like max length and enabled state
3. `prompt.py` - Memory integration in prompts
   - `memory_update_prompt` for creating memory from command execution
   - `memory_fuzzy_update_prompt` for manually updating memory
   - `include_memory_in_prompt` inserts memory context into prompts intelligently
4. `command_handler.py` - Memory updates after command execution
   - Updates memory with command context
   - Tracks command execution flow
5. `cli.py` - Memory CLI commands
   - Dedicated memory command group with subcommands
   - Memory-related flags in all main commands
   - Configuration for memory behavior

### Model Key Management System
1. `model_adapter.py` - Manages model API keys and validation
   - `ModelEnvironment` context manager for safely handling model environment variables
   - Key format validation on startup with helpful warnings
   - Model provider detection based on model name prefix
   - Environment variable management for multiple providers (OpenAI, Anthropic, Ollama)
2. `config.py` - Stores and retrieves model keys with precedence:
   - Environment variables (e.g., `VIBECTL_ANTHROPIC_API_KEY`)
   - Environment variable key files (e.g., `VIBECTL_ANTHROPIC_API_KEY_FILE`)
   - Configuration file keys (via `vibectl config set model_keys.anthropic`)
   - Configuration file key paths (via `vibectl config set model_key_files.anthropic`)
   - Legacy environment variables (e.g., `ANTHROPIC_API_KEY`)
3. `cli.py` - Key validation at application startup
   - Validates model keys when commands are executed
   - Displays warnings for missing or suspicious keys
   - Skips validation for `config` and `help` commands
   - Provides detailed instructions for resolving key issues

Detailed documentation about model key configuration can be found in [Model API Key Management](docs/MODEL_KEYS.md).

### Type Safety
- Extensive type annotations throughout codebase
- Generic type parameters and TypeVar for flexible interfaces
- Requires Python 3.10+, uses Python 3.10 features like match statements and union operators

### Configuration System
- Type-safe configuration with validation
- Theme configuration and custom prompt instructions
- Memory settings management
- Model key management and validation

### Model Interaction System
1. `model_adapter.py` - Abstraction for LLM model interactions
   - Abstract `ModelAdapter` interface defining common operations
   - `LLMModelAdapter` implementation for the llm package
   - Model instance caching for performance
   - Simplified access via module-level functions
   - Consistent error handling
   - Model key management and validation
   - Provider detection from model name prefixes
   - Context manager for environment variable handling
2. `command_handler.py` - Uses model adapter for command execution
   - Processes command output with model summaries
   - Handles vibe requests with model planning
   - Provides consistent error handling for LLM interactions
3. `memory.py` - Uses model adapter for memory updates
   - Updates memory context based on command execution
   - Uses model adapter instead of direct LLM calls
4. `prompt.py` - Defines prompt templates used by model adapters
   - Command-specific prompt templates
   - Formatting instructions
   - Consistent prompt structure for all LLM interactions

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
- Documentation in `docs/` directory

Installation options:
1. Standard pip installation for users (`pip install vibectl`)
2. Development installation with Flake/Nix

Dependencies are managed through:
1. `pyproject.toml` for Python dependencies
2. `flake.nix` for development environment
3. Virtual environment in `.venv/`
4. Distribution managed via PyPI (see `DISTRIBUTION.md`)
