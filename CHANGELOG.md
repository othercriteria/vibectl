# Changelog

All notable changes to the vibectl project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Correct prompt formatting in `semiauto` mode to properly include memory context, preventing incorrect LLM requests.
- Resolved `AttributeError` related to asyncio patching in tests.
- Corrected assertions for error string handling in `command_handler` memory tests.
- Fixed `IndexError` and lint warnings in `port-forward` keyboard interrupt tests.
- Added missing `summary_prompt_func` arguments to internal subcommand calls.

### Changed
- Simplified `port-forward` handler tests for improved stability and clarity.

## [0.5.3] - 2025-04-27

### Added
- Added initial Kafka throughput optimization demo (`examples/k8s-sandbox/kafka-throughput/`) featuring:
  - K3d Kubernetes cluster running a single-node KRaft Kafka instance.
  - Python producer/consumer applications generating load and reporting P99 latency.
  - A `vibectl` agent configured with the goal to maximize throughput and minimize latency by tuning Kafka broker environment variables (`KAFKA_HEAP_OPTS`, `KAFKA_NUM_NETWORK_THREADS`, `KAFKA_NUM_IO_THREADS`).
  - Resource limits on the sandbox container and de-optimized Kafka defaults to create a clear optimization scenario.
  - Makefile for easy management (`make up`, `make down`, `make logs`, etc.).
- Added basic Flask web UI (`kafka-demo-ui`) to the Kafka throughput demo, displaying key metrics (latency, producer stats, component health) using SocketIO for real-time updates.

### Changed
- Updated root `STRUCTURE.md` to include Kafka demo.

## [0.5.2] - 2025-04-26

### Changed
- Refactored output processing and truncation logic for better modularity and testability (`output_processor.py`, `truncation_logic.py`).
- Implemented budget-aware YAML truncation, distributing character limits across top-level sections.
- Improved log truncation to iteratively adjust lines kept based on character budget.
- Enhanced YAML output processing (`OutputProcessor`) with budget-based secondary truncation for better LLM context management.
- Improved robustness of `extract_yaml_sections` for various YAML structures, including multi-document files.
- Refined iterative log truncation logic (`_truncate_logs_by_lines`) for improved character budget adherence.

### Added
- Increased test coverage for output processing, YAML section handling, and log truncation edge cases.
- Extensive new unit tests for `OutputProcessor` focusing on YAML section extraction, budget calculation, and multi-document handling.
- Additional test coverage for `truncation_logic` edge cases.

### Fixed
- Addressed previously failing/skipped tests related to output processing.

## [0.5.1] - 2025-04-25

### Added
- New bootstrap demo in examples/k8s-sandbox featuring:
  - Self-contained k3d (K3s in Docker) cluster with Ollama LLM
  - Single-container setup with Docker-in-Docker
  - Vibectl configured to use local Ollama instance via kubectl port-forward
  - Support for installing from local source or stable PyPI packages
  - Automated demonstration of vibectl K8s analysis capabilities
  - Single-command unattended setup and execution

### Changed
- Improved feature-worktrees rule to prevent branch conflicts and enforce correct worktree-based feature development workflow

### Fixed
- Fixed handling of unknown model names with proper error messages
- Fixed potential KeyError when prompt contains {memory_context} placeholder but memory_context is empty
- Improved string format handling to handle malformed format strings in memory context

## [0.5.0] - 2025-04-22

### Added
- New `vibectl auto` subcommand to reify the looping `vibectl vibe --yes` pattern
- New `vibectl semiauto` subcommand as sugar for `auto` with negated `--yes` behavior
- Enhanced confirmation dialog with new options:
  - `yes [A]nd` for accepting with fuzzy memory update
  - `no [B]ut` for rejecting with fuzzy memory update
  - `[E]xit` option (in semiauto mode) to exit the loop cleanly

### Changed
- Updated `chaos-monkey` example to use the new `vibectl auto` subcommand
- Improved interactive-commands rule to clarify the proper usage of `--no-pager` with git commands

### Fixed
- Fixed error messages shown when a user selects [E]xit in semiauto mode
  - Updated exception handling to properly handle normal exits without displaying error messages
  - Improves user experience by ensuring clean exit behavior
- Fixed `vibectl auto` breaking on API errors like "overloaded_error"
  - Added detection of API-related errors and marked them as non-halting
  - Auto loop now continues despite transient API issues like rate limiting or service overload
  - Improved resilience for automated/scheduled usage of vibectl
- Fixed recovery suggestions not being integrated into memory state
  - Added update_memory call when recovery suggestions are generated
  - Ensures that suggestions from one command are available for subsequent commands in auto mode
  - Improves the continuity of error recovery in multi-step workflows

## [0.4.1] - 2025-04-19

### Added
- New chaos-monkey demo in examples/k8s-sandbox featuring:
  - Red team vs. blue team competitive scenario
  - Blue agent for maintaining system stability
  - Red agent for simulating service disruptions
  - Metrics collection and performance evaluation
  - Containerized vibectl agents interacting with K8s cluster

### Fixed
- Fixed KeyError when prompts contain format placeholders like `{spec}` that conflict with formatting operations
  - Added fallback string replacement method for robust prompt handling
  - Prevents crash in chaos-monkey agent when generating Kubernetes YAML templates
- Resolved linting issues in chaos-monkey overseer component
  - Fixed line length violations for improved code quality
  - Ensured code adheres to project's style standards

## [0.4.0] - 2025-04-18

### Added
- Basic structured logging to vibectl for improved observability and debugging
  - Configurable log levels for different verbosity needs
  - Console and file output support
  - Structured logging for machine-readable output
- Configurable log level via config or VIBECTL_LOG_LEVEL environment variable
- User-facing warnings and errors are surfaced via the console
- Logging test pattern and fixtures for reliable assertions on log output

## [0.3.2] - 2025-04-15

### Added
- New `port-forward` command for Kubernetes service port forwarding
  - Supports standard kubectl port-forward functionality
  - Features rich progress display with connection status
  - Includes vibe-based natural language request support
  - Provides configurable proxy monitoring warnings
- New `wait` command for Kubernetes condition monitoring
  - Supports standard kubectl wait functionality
  - Includes vibe-based natural language request support

### Changed
- Implemented asyncio for `wait`
