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
- `types.py` - Custom type definitions
- `logutil.py` - Logging setup and configuration
- `proxy.py` - Proxy-related functionality
- `py.typed` - Marker file for PEP 561 compliance
- `subcommands/` - Command implementation modules
  - `auto_cmd.py` - Auto command implementation
  - `vibe_cmd.py` - Vibe command implementation
  - `describe_cmd.py` - Describe command implementation
  - `version_cmd.py` - Version command implementation
  - `get_cmd.py` - Get command implementation
  - `wait_cmd.py` - Wait command implementation
  - `port_forward_cmd.py` - Port-forward command implementation
  - `scale_cmd.py` - Scale command implementation
  - `rollout_cmd.py` - Rollout command implementation
  - `just_cmd.py` - Just command implementation
  - `delete_cmd.py` - Delete command implementation
  - `logs_cmd.py` - Logs command implementation
  - `events_cmd.py` - Events command implementation
  - `create_cmd.py` - Create command implementation
  - `cluster_info_cmd.py` - Cluster-info command implementation

### Testing (`tests/`)
- Test files and test resources
- Coverage tracking with pytest-cov
- `.coveragerc` - Coverage measurement configuration
- `conftest.py` - Pytest fixtures and configuration
- `fixtures.py` - Shared test fixtures
- `TESTING.md` - Test documentation and guidelines

### Examples (`examples/`)
- Example usage scenarios and demo environments
- `k8s-sandbox/` - Kubernetes sandbox environments:
  - `ctf/` - CTF-style Docker sandbox demonstrating vibectl autonomy. See [examples/k8s-sandbox/ctf/STRUCTURE.md](examples/k8s-sandbox/ctf/STRUCTURE.md) for details.
  - `chaos-monkey/` - Red team vs. blue team competitive scenario with vibectl agents. See [examples/k8s-sandbox/chaos-monkey/STRUCTURE.md](examples/k8s-sandbox/chaos-monkey/STRUCTURE.md) for details.
  - `bootstrap/` - Self-contained k3d (K3s in Docker) + Ollama environment, with vibectl configured to use the local LLM and automated demonstration of Kubernetes analysis. See [examples/k8s-sandbox/bootstrap/STRUCTURE.md](examples/k8s-sandbox/bootstrap/STRUCTURE.md) for details.
  - `kafka-throughput/` - Demonstrates `vibectl` tuning Kafka broker performance (heap, threads) in K3d based on producer/consumer metrics (latency, rates). Includes adaptive producer, UI for monitoring. See [examples/k8s-sandbox/kafka-throughput/STRUCTURE.md](examples/k8s-sandbox/kafka-throughput/STRUCTURE.md) for details.

### Type Information (`typings/`)
- Custom type definitions and type stubs

### Documentation (`docs/`)
- `MODEL_KEYS.md` - Comprehensive guide for model API key management
- `CONFIG.md` - Configuration options and settings
- `PORT_FORWARD.md` - Documentation for port-forwarding functionality
- Additional documentation files

### Configuration
- `.vscode/` - VS Code editor settings
- `.cursor/` - Cursor IDE configuration and rules
  - `rules/` - Project-specific Cursor rules (see `RULES.md` for a complete description of all rules)
- `.pre-commit-config.yaml` - Pre-commit hook configuration
- `pyproject.toml` - Python project configuration and dependencies
- `Makefile` - Build and development automation
- `flake.nix` & `flake.lock` - Nix development environment
- `.envrc` - direnv configuration for environment activation

### Scripts (`scripts/`)
- Helper scripts for development and maintenance

## Key Files

- `README.md` - Project overview and getting started guide
- `STRUCTURE.md` - This file, documenting project organization
- `LICENSE` - Project license information
- `RULES.md` - Documentation of Cursor rules system
- `docs/MODEL_KEYS.md` - Guide for configuring model API keys
- `CHANGELOG.md` - Documentation of notable changes for each version
- `DISTRIBUTION.md` - Guide for publishing to PyPI
- `TESTING.md` - Documentation for testing practices
- `TODO.md` - Task tracker and planned work
- `UPDATES.md` - Recent updates and changes tracking
- `PLANNED_CHANGES.md` - Feature planning document
- `bump_version.py` - Script for semantic version management

## Architecture

### Command Systems
1. `cli.py` - Core command-line interface definitions and routing
2. `subcommands/` - Implementations of individual commands:
   - `auto_cmd.py` - Autonomous command execution
   - `vibe_cmd.py` - AI-assisted command execution
   - `describe_cmd.py` - Resource description
   - `get_cmd.py` - Resource retrieval
   - `delete_cmd.py` - Resource deletion
   - `scale_cmd.py` - Resource scaling
   - `rollout_cmd.py` - Deployment rollout management
   - `wait_cmd.py` - Waiting for resource conditions
   - `port_forward_cmd.py` - Port forwarding
   - `logs_cmd.py` - Container logs retrieval
   - `events_cmd.py` - Event retrieval
   - `create_cmd.py` - Resource creation
   - `cluster_info_cmd.py` - Cluster information
   - `just_cmd.py` - Plain execution with memory
   - `version_cmd.py` - Version information

### Console Management
1. `console.py` - Typed output methods with theme support
2. `output_processor.py` - Format detection and intelligent processing
3. `command_handler.py` - Standardized command execution

### Prompt System
1. `prompt.py` - Command-specific prompt templates
   - Resource-specific prompts for each command
   - Memory integration templates
   - System messages and context

### Common Command Patterns
1. `command_handler.py` - Generic command execution patterns
   - Handle confirmation for destructive operations
   - Execute kubectl commands safely
   - Process command output for user feedback
   - Port-forwarding functionality
   - Memory integration

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
5. Subcommands - Memory integration in commands
   - Memory flags in all main commands
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

### Logging System
1. `logutil.py` - Logging configuration and setup
   - Standardized logging format
   - Log level configuration
   - Environment variable control for logging
2. Command implementations - Consistent logging patterns
   - Error handling with appropriate logging
   - User-facing vs. debug logging separation
   - Traceback control based on log level

### Type Safety
- Extensive type annotations throughout codebase (`types.py` and inline)
- Generic type parameters and TypeVar for flexible interfaces
- Requires Python 3.10+, uses Python 3.10 features like match statements and union operators
- PEP 561 compliance with `py.typed` marker

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

### Proxy Support
1. `proxy.py` - Proxy handling for model requests
   - Environment variable detection and configuration
   - HTTP/HTTPS proxy support
   - SSL certificate verification options

## Development Workflow

1. Git worktrees for parallel feature development
   - Feature branches created from main
   - Worktrees placed in `../worktrees/` directory
   - One feature per worktree for isolated development
   - **Always use the improved worktree workflow in `.cursor/rules/feature-worktrees.mdc` for all new features.**
2. Nix/direnv for reproducible development environments
3. pre-commit hooks for code quality
4. pytest for testing with coverage requirements
   - Performance-optimized test execution with parallel options
   - Fast test markers for quick development feedback
   - See [tests/TESTING.md](tests/TESTING.md) for details
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
- Examples and demos in `examples/` directory

Installation options:
1. Standard pip installation for users (`pip install vibectl`)
2. Development installation with Flake/Nix

Dependencies are managed through:
1. `pyproject.toml` for Python dependencies
2. `flake.nix` for development environment
3. Virtual environment in `.venv/`
4. Distribution managed via PyPI (see `DISTRIBUTION.md`)
