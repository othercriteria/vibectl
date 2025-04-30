# Changelog

All notable changes to the vibectl project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- New `yaml_manifest` field to `LLMCommandResponse` schema to handle YAML input for commands like `create -f -`.
- Implement JSON schema (`LLMCommandResponse`) for structured LLM command planning responses.
- Update command planning prompts (get, describe, logs, version, etc.) to request JSON output conforming to the schema.
- Update `ModelAdapter` to support passing JSON schemas to compatible LLM models.
- Update `handle_vibe_request` to generate schema, parse JSON response, and dispatch based on `action_type`.
- Add basic schema validation via Pydantic model and handler checks.
- Correct prompt formatting in `semiauto` mode to properly include memory context, preventing incorrect LLM requests.
- Resolved `AttributeError` related to asyncio patching in tests.
- Corrected assertions for error string handling in `command_handler` memory tests.
- Fixed `IndexError` and lint warnings in `port-forward` keyboard interrupt tests.
- Added missing `summary_prompt_func` arguments to internal subcommand calls.

### Changed
- Refactored `create_planning_prompt` to assume command verb is implied by context.
  - Prompt now focuses LLM on extracting target resource(s) and arguments.
  - Updated prompt instructions and structure.
- Updated most `PLAN_*_PROMPT` constants (get, describe, delete, logs, scale, rollout, wait, port-forward, version, cluster-info, events) to use the refactored prompt structure.
  - Examples now focus on target description, removing action verbs.
- Updated `PLAN_CREATE_PROMPT` examples to include a mix of implicit and explicit creation requests.
- Updated `handle_vibe_request` and `_execute_command` to process `yaml_manifest` from LLM response.
- Refined `_handle_command_confirmation` to restore full option handling (`a`, `e`) and improve prompt clarity.
- Simplified `port-forward` handler tests for improved stability and clarity.
- **[Demo]** Update `examples/k8s-sandbox/ctf` demo to install `vibectl` from local source via `pip install -e .`.

### Fixed
- Updated numerous tests (`test_prompt.py`, `test_command_handler_edge_cases.py`) to align with prompt refactoring and confirmation logic changes.
- Fixed redundant AI explanation print during command confirmation flow.
- Replaced debug `print` statement with `logger.debug` in `handle_vibe_request`.
- Fixed `AttributeError` for `print_command_info` by using `print_processing`.
- Resolved persistent Mypy assignment errors in `command_handler.py`.
- Removed unused `flags` parameter from `create_planning_prompt`.
- Resolve prompt formatting issues when embedding JSON schema definition.
- Ensure correct command verb is used when executing LLM-planned commands.
- Correct `update_memory` calls within `handle_vibe_request` for errors and autonomous mode.
- Handle potential JSON parsing (`JSONDecodeError`) and validation (`ValidationError`) errors from LLM responses.
- Fix various test failures related to schema integration, error handling, and mock interactions.
- Correct type hints and resolve linter errors in related modules and tests.
- Refactor command confirmation logic for clarity.

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
- New `vibectl auto` subcommand to reify the looping `vibectl vibe --yes`
