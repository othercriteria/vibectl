# Project Structure

This document provides an overview of the project's structure and organization.

## Directory Layout

### Core Package (`vibectl/`)

- `cli.py` - Command-line interface implementation
- `config.py` - Configuration management and settings
- `console.py` - Console output formatting and management. Includes methods for live streaming of Vibe AI responses (e.g., `start_live_vibe_panel`, `update_live_vibe_panel`, `stop_live_vibe_panel`).
- `command_handler.py` - Common command handling patterns (confirmation, output processing), delegates kubectl execution to `k8s_utils`, and live display to relevant modules. Manages `allowed_exit_codes` for commands. Handles streaming Vibe AI output. Core Vibe.AI LLM interaction loop (`handle_vibe_request`) moved to `execution/vibe.py`.
- `k8s_utils.py` - Utilities for interacting with Kubernetes, including core `kubectl` execution logic (standard, YAML input) and async process creation. `run_kubectl` always captures output and uses an `allowed_exit_codes` parameter (defaulting to `(0,)`) to treat certain non-zero exits as success.
- `output_processor.py` - Token limits and output preparation
- `memory.py` - Context memory for cross-command awareness
- `model_adapter.py` - Abstraction layer for LLM model interactions.
- `proxy_model_adapter.py` - Client-side adapter for connecting to LLM proxy servers via gRPC (92% test coverage)
- `config_utils.py` - Configuration utilities including YAML handling, deep merge, and environment variable support (95% test coverage)
- `py.typed` - Marker file for PEP 561 compliance
- `schema.py` - Pydantic models for structured LLM output schemas (e.g., `LLMPlannerResponse`, `CommandAction` with `explanation`, `FeedbackAction` with `explanation` and `suggestion`). Includes `allowed_exit_codes` in `CommandAction`.
- `live_display.py` - Handlers for Rich Live display features (e.g., port-forward, wait), now also respects `allowed_exit_codes`.
- `live_display_watch.py` - Interactive live display implementation for watch/follow commands, now also respects `allowed_exit_codes`.
- `types.py` - Custom type definitions (e.g., `ActionType` enum for schema, `Success` and `Error` result types. `Success` objects include `original_exit_code`, `Error` objects now include `original_exit_code`).
- `utils.py` - Utility functions and helpers
- `__init__.py` - Package initialization and version information
- `logutil.py` - Logging setup and configuration
- `server/` - LLM proxy server components (gRPC-based centralized LLM access). See [vibectl/server/STRUCTURE.md](vibectl/server/STRUCTURE.md) for detailed architecture.
  - `main.py` - Server entry point and configuration management (99% test coverage)
  - `grpc_server.py` - gRPC server infrastructure and lifecycle management (100% test coverage)
  - `llm_proxy.py` - Core LLM proxy service implementation (93% test coverage)
  - `jwt_auth.py` - JWT authentication implementation (100% test coverage)
  - `jwt_interceptor.py` - gRPC authentication interceptor (100% test coverage)
  - `__init__.py` - Package initialization
- `proto/` - Protocol buffer definitions for gRPC communication
  - `llm_proxy_pb2.py` - Generated protocol buffer message definitions
  - `llm_proxy_pb2_grpc.py` - Generated gRPC service stubs and server interfaces
- `execution/` - Modules related to command execution logic.
  - `vibe.py` - Handles the core Vibe.AI LLM interaction loop, including `handle_vibe_request`.
  - `apply.py` - Handles intelligent apply workflow execution logic, including file discovery, validation, correction/generation, and command planning.
- `prompts/` - Modular prompt system with command-specific prompt modules.
  - `__init__.py` - Package initialization for prompts directory.
  - `shared.py` - Common prompt utilities and decorator functions for plugin support (`create_planning_prompt`, `create_summary_prompt`, `with_planning_prompt_override`, `with_summary_prompt_override`, etc.).
  - `schemas.py` - Centralized schema definitions for LLM interactions (`_SCHEMA_DEFINITION_JSON`, `_EDIT_RESOURCESCOPE_SCHEMA_JSON`).
  - `edit.py` - Prompts specific to the edit command (`edit_plan_prompt`, `edit_resource_prompt`).
  - `apply.py` - Prompts specific to the apply command (`plan_apply_filescope_prompt_fragments`, `summarize_apply_manifest_prompt_fragments`, `correct_apply_manifest_prompt_fragments`, `plan_final_apply_command_prompt_fragments`, `apply_output_prompt`, `PLAN_APPLY_PROMPT`).
  - `scale.py` - Prompts specific to the scale command (`scale_plan_prompt`, `scale_resource_prompt`).
  - `rollout.py` - Prompts specific to the rollout command (`rollout_plan_prompt`, `rollout_general_prompt`, `rollout_history_prompt`, `rollout_status_prompt`).
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
  - `diff_cmd.py` - Diff command implementation
  - `check_cmd.py` - Check command implementation (evaluates predicates about cluster state)
  - `edit_cmd.py` - Edit command implementation with intelligent edit capabilities
  - `patch_cmd.py` - Patch command implementation
  - `apply_cmd.py` - Apply command implementation
  - `setup_proxy_cmd.py` - Setup and configuration commands for the LLM proxy server (14% test coverage - needs improvement)

### Testing (`tests/`)

- Test files and test resources
- Coverage tracking with pytest-cov
- `.coveragerc` - Coverage measurement configuration
- `conftest.py` - Pytest fixtures and configuration
- `fixtures.py` - Shared test fixtures
- `TESTING.md` - Test documentation and guidelines
- `subcommands/` - Test modules for individual subcommands
  - `test_diff_cmd.py` - Tests for the `vibectl diff` subcommand.
  - `test_apply_cmd.py` - Tests for the `vibectl apply` subcommand.
- `execution/` - Test modules for execution logic
  - `test_apply.py` - Tests for the `vibectl/execution/apply.py` module.
- `test_prompts_apply.py` - Tests for the `vibectl/prompts/apply.py` module.

### Examples (`examples/`)

- Example usage scenarios and demo environments
- `manifests/` - Example Kubernetes manifest files for testing various `vibectl` features.
  - `apply/` - Manifests for testing `vibectl apply vibe` intelligent features.
  - `diff/` - Manifests for testing `vibectl diff` functionality.
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
  - `scripts/` - Helper shell scripts used by Cursor rules to enable complex, multi-step actions or to work around tool limitations with multi-line commands. Scripts in this directory are typically called by the `command` field in a rule's action block.
- `.pre-commit-config.yaml` - Pre-commit hook configuration
- `pyproject.toml` - Python project configuration and dependencies
- `Makefile` - Build and development automation
- `flake.nix` & `flake.lock` - Nix development environment
- `.envrc` - direnv configuration for environment activation

### Dependency Management

The project uses **uv** for fast, deterministic dependency resolution and locking:

#### Key Files

- `pyproject.toml` - Contains project dependencies and development dependencies
- `uv.lock` - Locked dependency versions generated by uv (committed to version control)
- `flake.nix` - Nix development environment includes uv tooling

#### Workflow

- **Add dependencies**: Edit `pyproject.toml` dependencies or `[project.optional-dependencies].dev`
- **Update lock file**: Run `make lock` to regenerate `uv.lock` with resolved versions
- **Install dependencies**: The Nix dev shell automatically installs from the lock file

#### Key Commands

- `make lock` - Regenerate uv.lock file from pyproject.toml
- `uv pip compile pyproject.toml --extra=dev --output-file=uv.lock` - Direct uv command

The lock file ensures reproducible builds across different environments and is committed to version control for consistency.

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
- `TODO-SERVER.md` - Server-specific roadmap and outstanding tasks
- `UPDATES.md` - Recent updates and changes tracking
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
   - `port_forward_cmd.py` - Port forwarding (partially delegated to live_display)
   - `logs_cmd.py` - Container logs retrieval
   - `events_cmd.py` - Event retrieval
   - `create_cmd.py` - Resource creation
   - `cluster_info_cmd.py` - Cluster information
   - `just_cmd.py` - Plain execution with memory
   - `diff_cmd.py` - Diff configurations against live state or Vibe.AI plans.
   - `check_cmd.py` - Evaluates predicates about cluster state using read-only commands.
   - `edit_cmd.py` - Resource editing with intelligent features (configurable via `intelligent_edit`)
   - `patch_cmd.py` - Resource patching with merge and JSON patches
   - `apply_cmd.py` - Resource application with intelligent features
   - `version_cmd.py` - Version information

### Console Management

1. `console.py` - Typed output methods with theme support. Includes methods for live streaming of Vibe AI responses.
2. `output_processor.py` - Format detection and intelligent processing
3. `command_handler.py` - Standardized command execution
   - Process command output for user feedback, including streaming Vibe AI responses.
   - Port-forwarding functionality (partially delegated to live_display)
   - Memory integration
   - Handles `allowed_exit_codes` for commands.

### Prompt System

1. `prompts/` - Modular prompt system for LLM interactions:
   - `shared.py` - Common prompt utilities and plugin support decorators:
     - Functions that return `PromptFragments` (tuples of `SystemFragments` and `UserFragments`)
     - Plugin override decorators (`with_planning_prompt_override`, `with_summary_prompt_override`)
     - Helper functions for building prompts:
       • `build_context_fragments` – **new canonical helper** for injecting memory, custom instructions and optional `presentation_hints`.
       • `create_planning_prompt`, `create_summary_prompt` – scaffold standardised planning/summary templates.
     - Configuration-driven prompt variations with `Config` objects
   - `schemas.py` - Centralized schema definitions (`_SCHEMA_DEFINITION_JSON`, `_EDIT_RESOURCESCOPE_SCHEMA_JSON`)
   - Command-specific modules (`edit.py`, `apply.py`, `scale.py`, `rollout.py`) with decorated functions for plugin support
2. Plugin Support - Commands use decorated prompt functions for extensibility:
   - Planning functions (e.g., `scale_plan_prompt`, `rollout_plan_prompt`) can be overridden by plugins
   - Summary functions (e.g., `scale_resource_prompt`, `rollout_general_prompt`) provide consistent interfaces
   - Memory integration is handled by including memory content within relevant fragments
3. Schema Integration (`schema.py`, `types.py`, `execution/vibe.py`)
   - Defines Pydantic models (`LLMPlannerResponse`, `CommandAction`, `FeedbackAction`, etc.) and enums (`ActionType`) for desired LLM output structure. Key highlights:
     • `LLMPlannerResponse` now includes an optional `presentation_hints` string enabling planners to pass UI/formatting guidance to downstream prompts.
     • `CommandAction` can specify `allowed_exit_codes` and `explanation`.
     • `FeedbackAction` can include `explanation` and `suggestion`.
   - `model_adapter.py` uses these schemas for LLM interaction.
   - `types.py` includes `Error` model now with `original_exit_code`.

### Common Command Patterns

1. `command_handler.py` - Generic command execution patterns
   - Handle confirmation for destructive operations
   - Dispatches kubectl execution to `k8s_utils.py`
   - Process command output for user feedback, including streaming Vibe AI responses.
   - Port-forwarding functionality (partially delegated to live_display)
   - Memory integration
   - Handles `allowed_exit_codes` for commands.
   - Note: Core Vibe.AI LLM interaction loop (`handle_vibe_request`) moved to `vibectl/execution/vibe.py`.
2. `vibectl/execution/vibe.py` - Handles the core Vibe.AI LLM interaction loop.
   - `handle_vibe_request` is the primary entry point for LLM-driven command planning and execution.
   - Uses `model_adapter.py` for LLM calls.
   - Integrates with `prompts/shared.py` for generating LLM requests.
   - Works with `schema.py` for parsing LLM responses.

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
3. `prompts/shared.py` - Memory integration in prompts
   - `memory_update_prompt` for creating memory from command execution (returns `PromptFragments`).
   - `memory_fuzzy_update_prompt` for manually updating memory (returns `PromptFragments`).
   - The **preferred** way to inject memory (and custom instructions) into prompts is via `prompts/context.build_context_fragments`, which returns standardised system fragments. Legacy helpers like `include_memory_in_prompt` are deprecated.
4. `command_handler.py` - Memory updates after command execution
   - Updates memory with command context
   - Tracks command execution flow

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
- Requires Python 3.11+, uses modern features like `asyncio.TaskGroup`, `asyncio.timeout`, etc.
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
   - Processes command output with model summaries, supports streaming of LLM summary responses
   - Provides consistent error handling for LLM interactions
   - (Note: vibe requests / LLM planning loop now in `execution/vibe.py`)
3. `execution/vibe.py` - Central module for LLM-driven planning and execution loop (`handle_vibe_request`).
   - Uses `model_adapter.py` for LLM calls.
   - Integrates with `prompts/shared.py` for generating LLM requests.
   - Works with `schema.py` for parsing LLM responses.
4. `memory.py` - Uses model adapter for memory updates
   - Updates memory context based on command execution
   - Uses model adapter instead of direct LLM calls
5. `prompts/shared.py` - Defines prompt templates used by model adapters
   - Command-specific prompt template functions (e.g., `create_planning_prompt()`, `plan_vibe_fragments()`) now return `PromptFragments`.
   - Includes instructions for generating JSON output matching defined schemas (now including `explanation` and `suggestion` fields where appropriate).
   - Formatting instructions are managed via fragment helper functions.
   - Consistent prompt structure for all LLM interactions, built from fragments.
   - Plugin override decorators for extensibility.
6. Schema Integration (`schema.py`, `types.py`, `execution/vibe.py`)
   - Defines Pydantic models (`LLMPlannerResponse`, `CommandAction`, `FeedbackAction`, etc.) and enums (`ActionType`) for desired LLM output structure. Key highlights:
     • `LLMPlannerResponse` now includes an optional `presentation_hints` string enabling planners to pass UI/formatting guidance to downstream prompts.
     • `CommandAction` can specify `allowed_exit_codes` and `explanation`.
     • `FeedbackAction` can include `explanation` and `suggestion`.
   - `model_adapter.py` uses these schemas for LLM interaction.
   - `types.py` includes `Error` model now with `original_exit_code`.

### LLM Proxy Server System

1. **Server Architecture** (`vibectl/server/`) - High-performance gRPC-based LLM proxy
   - **Service Layer**: Core proxy service with streaming support and model resolution
   - **Authentication Layer**: JWT-based authentication with gRPC interceptors
   - **Infrastructure Layer**: Server lifecycle management and configuration
   - **Protocol Definition**: gRPC protocol buffers for client-server communication
   - See [vibectl/server/STRUCTURE.md](vibectl/server/STRUCTURE.md) for detailed architecture documentation

2. **Client Integration** (`proxy_model_adapter.py`) - Transparent proxy client
   - Implements `ModelAdapter` interface for seamless integration
   - Handles gRPC connection management and authentication
   - Provides automatic reconnection and failover capabilities
   - Supports both streaming and non-streaming LLM requests
   - 92% test coverage with comprehensive integration testing

3. **Configuration System** (`config_utils.py`) - Shared configuration management
   - YAML configuration file support with environment variable overrides
   - Deep merge functionality for hierarchical configuration
   - Type conversion and validation utilities
   - File-based secret management for secure key storage
   - 95% test coverage ensuring reliable configuration handling

4. **Setup Commands** (`subcommands/setup_proxy_cmd.py`) - Proxy management CLI
   - `configure` command: Set up proxy server connections and authentication
   - `status` command: Check proxy server health and configuration
   - `remove` command: Clean up proxy configurations
   - URL validation and connection testing
   - 14% test coverage (improvement needed)

5. **Protocol Components** (`vibectl/proto/`) - gRPC communication
   - **Protocol Buffer Definitions**: Structured message definitions for requests/responses
   - **Service Stubs**: Generated gRPC client and server interfaces
   - **Streaming Support**: Real-time response streaming capabilities
   - **Metadata Handling**: Authentication and request context passing

### Key Integration Benefits
- **Centralized LLM Access**: Multiple clients can share expensive LLM resources
- **Authentication & Security**: JWT-based secure access with configurable policies
- **Performance Optimization**: Connection pooling, caching, and streaming support
- **Transparent Integration**: Drop-in replacement for direct LLM access
- **Monitoring & Metrics**: Built-in request tracking and performance monitoring
