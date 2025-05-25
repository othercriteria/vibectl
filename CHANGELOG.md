# Changelog

All notable changes to the vibectl project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

## [0.8.4] - 2025-05-25

### Added
- `vibectl edit` command with intelligent editing capabilities
  - Standard kubectl edit functionality when `intelligent_edit` config is disabled
  - Intelligent editing workflow when enabled: fetch resource → summarize to natural language → user edits text → LLM generates patch → apply patch
  - Integration with existing vibe mode and patch command logic
  - Support for both standard usage and natural language editing via `click.edit()` interface

## [0.8.3] - 2025-05-23

### Added
- **`vibectl patch` Command**: Complete implementation of intelligent Kubernetes resource patching with natural language support.
  - Supports strategic merge patches, JSON merge patches, and JSON patches
  - Can patch resources by file or by type/name
  - Includes "vibe mode" for natural language patch descriptions (e.g., "scale the frontend deployment to 3 replicas", "add label environment=prod to the frontend service")
  - Comprehensive test coverage with 13 tests achieving 100% code coverage
  - Full integration with existing vibectl CLI options and output formatting

### Fixed
- **[Demo]** Chaos Monkey configuration and model selection:
  - Fixed inconsistent `VIBECTL_MODEL` defaults across files (unified to `claude-3.7-sonnet`)
  - Simplified configuration flow by removing redundant defaults in docker-compose.yaml
  - Fixed documentation gaps by adding missing `--vibectl-model` flag to README
  - Fixed library version pinning that was blocking claude-4-sonnet support
  - Resolved over-engineered configuration system that was preventing proper model selection

### Changed

## [0.8.2] - 2025-05-23

### Added
- Implemented streaming for LLM responses in Vibe commands, providing real-time output and a `show_streaming` flag (configurable globally and via `OutputFlags`) to control live display of intermediate Vibe output streams.
- Added test coverage for LLM response streaming, including scenarios where streaming display is suppressed (`show_streaming=False`).

### Changed
- Enabled Vibe summarization and memory updates even when the underlying `kubectl` command returns empty output. This allows for contextual memory updates (e.g., "No PVCs found in namespace X") where previously summaries were suppressed.
- Refactored `vibectl events` command to use `handle_standard_command` and `handle_watch_with_live_display` for better consistency and simplified logic.
- Modified `configure_output_flags` to include `show_streaming` and updated all subcommand callsites.
- Updated `ConsoleManager.print_vibe` to handle `use_panel` argument for controlling panel display, especially for streamed vs. non-streamed Vibe output.

## [0.8.1] - 2025-05-21

### Added
- **`vibectl check <predicate>` Subcommand**:
    - Implemented a new subcommand for autonomous, read-only evaluation of Kubernetes cluster state predicates.
    - Returns specific exit codes: `0` for TRUE, `1` for FALSE, `2` for poorly posed/ambiguous predicate, `3` for cannot determine/timeout.
    - Employs an iterative LLM-based planning loop:
        - Gathers information using read-only `kubectl` commands.
        - Feeds results back into LLM memory.
        - Continues until the predicate is resolved or max iterations/timeout is reached.
    - Includes utility functions to strictly enforce read-only `kubectl` operations.
    - Added `docs/predicate_evaluation.md` with a worked example.

### Changed
- **LLM Planner Schema & Prompting**:
    - Introduced a `DONE` action to the LLM planner schema, allowing the planner to signify completion of predicate evaluation and provide an `explanation` and `exit_code`.
    - Added an `explanation` field to the `CommandAction` and `explanation`/`suggestion` fields to `FeedbackAction` in the schema.
    - Revised system prompts and few-shot examples (using a new `MLExampleItem` structure) for the `vibectl check` planner to be more precise, emphasizing read-only operations and clear action usage.
    - Updated general planner prompts to leverage new schema fields for improved clarity.
- **Core Logic & Error Handling**:
    - Refactored core `check` logic into `vibectl.execution.check.py`.
    - Refactored `handle_vibe_request` into `vibectl.execution.vibe.py`.
    - Improved error handling for unhandled LLM actions, max iteration limits, malformed LLM commands, and improperly formed predicates.
    - Standardized exit codes for the `check` command using a `PredicateCheckExitCode` enum.
- **Command Confirmation**:
    - Consolidated command confirmation logic, centralizing the decision based on whether a command is read-only using `is_kubectl_command_read_only`.
- **Testing**:
    - Added extensive tests for `vibectl check` logic and subcommand, including iterative evaluation, exit codes, and various predicate scenarios.
    - Improved test coverage for `vibectl.execution.check`.

## [0.8.0] - 2025-05-17

### Added

- `vibectl apply vibe` intelligent workflow: an LLM-powered feature that understands user requests for applying manifests, discovers and validates specified files (local or remote), builds an operational context by summarizing valid manifests, attempts to correct or generate manifests for invalid/incomplete sources, plans the final `kubectl apply` command(s) based on all inputs and context, and executes the plan. Includes cleanup of temporary files.
- `vibectl diff` subcommand to compare local configurations (files or stdin) or planned configurations against the live cluster state, with optional summarization of changes.
- Added comprehensive tests for the `vibectl diff` subcommand, achieving 100% code coverage for `vibectl/subcommands/diff_cmd.py`.

### Changed

- Refactored `allowed_exit_codes` handling throughout the application:
  - `LLMCommandResponse` schema now supports an optional `allowed_exit_codes` field, allowing Vibe.AI to specify which exit codes are considered successful for a planned command.
  - `run_kubectl` (in `vibectl/k8s_utils.py`) now consistently uses the `allowed_exit_codes` parameter.
  - `Success` result objects now include `original_exit_code` to preserve the actual exit code of the command.
  - Command handlers (`command_handler.py`, `live_display.py`, `live_display_watch.py`) now propagate `allowed_exit_codes` to `run_kubectl` and `run_kubectl_with_yaml`.
- Refactored `run_kubectl` (in `vibectl/k8s_utils.py`):
  - Now always captures stdout/stderr.
  - Accepts `allowed_exit_codes` parameter to treat specific non-zero exit codes as success (e.g., for `kubectl diff`).
  - `Success` result objects now include `original_exit_code`.
- Updated numerous tests and subcommand implementations to align with the `run_kubectl` refactoring and `allowed_exit_codes` propagation.

### Removed

- Removed `capture` parameter from `run_kubectl` and its call sites, as output is now always captured.

## [0.7.0] - 2025-05-14

### Added

- **LLM Interaction Optimization & Observability:**
  - Refactored prompt construction to use a fragment-based system (`PromptFragments` in `vibectl/prompt.py`, `vibectl/types.py`) for better structure, potential caching by the underlying `llm` library, and improved maintainability.
  - Enhanced LLM call instrumentation in `model_adapter.py` and `command_handler.py` to record and display metrics for token usage (input/output) and latency, including total processing duration for LLM-related operations.
  - Added `--show-metrics`/`--no-show-metrics` flag and corresponding configuration (`show_metrics`) to control the display of these LLM metrics.
  - Introduced `TimedOperation` context manager in `model_adapter.py` for standardized internal timing.

### Changed

- Major refactor of prompt generation and handling (`vibectl/prompt.py`, `vibectl/command_handler.py`):
  - Introduced `PromptFragments` (SystemFragments, UserFragments) for more structured and flexible prompt construction.
  - Updated most planning and summarization prompts to use this new fragment-based system (e.g., `plan_vibe_fragments`, `memory_update_prompt`, `vibe_autonomous_prompt`).
  - Replaced static `plan_prompt` strings in subcommand handlers with `plan_prompt_func` that return `PromptFragments`.
  - Removed `memory_context` as a direct argument to `handle_vibe_request`; memory is now incorporated into prompt fragments by the caller or within specific prompt functions.
  - Consolidated and clarified prompt examples and instructions.
- Improved consistency in passing `Config` objects for prompt generation and other configurations.
- Refactored `LLMModelAdapter.execute` in `vibectl/model_adapter.py` for improved robustness, error handling, and internal timing:
  - Implemented `_handle_prompt_execution_with_adaptation` for adaptive retries on `AttributeError` (e.g., schema/fragment issues).
  - Introduced `LLMAdaptationError` for exhausted adaptation attempts.
  - Enhanced error logging with more context (attempt counts, latencies).
  - Made `_determine_provider_from_model` more robust for Ollama models.
- Updated `LLMMetrics` in `vibectl/types.py` (removed `cache_hit`, added `total_processing_duration_ms`) and adjusted `command_handler.py` and `console.py` for consistent metrics display.

## [0.6.3] - 2025-05-12

### Changed

- **[Demo]** Kafka Throughput Demo:
  - Updated `README.md` and `STRUCTURE.md` to reflect the current implementation:
    - `README.md`: Removed outdated Makefile targets (e.g., `check-latency`) and the "Troubleshooting & Past Issues" section. Updated demo stop command to `make down && make clean-cluster`.
    - `STRUCTURE.md`: Added `k8s-sandbox/port_forward_manager.py` and the `k8s-sandbox/manifests/` directory. Updated descriptions for `compose.yml` (reflecting `status-volume` as a host bind mount and adding the `kminion` service) and `k8s-sandbox/entrypoint.sh` (mentioning `port_forward_manager.py` for Kafka port-forwarding).
  - Standardized `TARGET_LATENCY_MS` usage across components. This environment variable is now consistently used for latency thresholds and is propagated from the host to the producer.
  - Improved producer's adaptive rate logic: it now holds or adjusts its target send rate based on a comparison of actual consumer p99 latency against the `TARGET_LATENCY_MS`.
- **[Demo]** Refined Chaos Monkey agent RBAC permissions for Blue and Red agents:
  - Restricted Red Agent's ability to create/delete Deployments/ReplicaSets.
  - Scoped Red Agent's pod creation to the `services` namespace.
  - Hardened Blue and Red agent access to the `system-monitoring` namespace (no access to common resources).
  - Granted Blue Agent explicit read-only access to the `protected` namespace.
  - Ensured Blue Agent retains necessary defensive capabilities in the `services` namespace via a dedicated Role, while its ClusterRole is now primarily read-only cluster-wide.
  - Stabilized ServiceAccount (SA) handling in Chaos Monkey demo to ensure reliable token authentication:
    - Agent SAs (blue-agent, red-agent) are now created once via a dedicated manifest (`agent-serviceaccounts.yaml`).
    - SA definitions were removed from passive and active RBAC YAML files.
    - `k8s-entrypoint.sh` updated to apply the standalone SA manifest early.
    - Kubeconfig regeneration during the passive-to-active RBAC switch is now skipped, as the SA token remains valid.
    - This resolves intermittent "Unauthorized" errors previously faced by agents post-RBAC switch.

## [0.6.2] - 2025-05-08

### Fixed

- Update example Dockerfiles (bootstrap, ctf) to use Python 3.11+.
- Fix `TypeError` in `vibectl auto` command when `--yes` flag is used.
- Fix `click.Abort` error in non-interactive `auto` mode by correctly handling the `yes` flag during command confirmation for dangerous commands.
- Fix `No module named pip` error in bootstrap example Dockerfile by adding `ensurepip` step.

## [0.6.1] - 2025-05-07

### Added

- Interactive live display for commands using `--watch` (`get`, `events`) or `--follow` (`logs`), replacing simple pass-through. Includes keybindings for Exit (E), Pause (P), Wrap (W), Save (S), and Filter (F).
- Status bar for live display showing elapsed time, line count, and spinner.
- Live display feature for `vibectl get --watch` using Rich Live.
- Planned: Enhanced watch/follow functionality for relevant vibectl commands (WIP)

### Changed

- Refactored tests for `get` subcommand into `tests/subcommands/test_get_cmd.py`.
- Improved test coverage for `vibectl/subcommands/get_cmd.py`.
- Refactored watch/follow logic from `command_handler.py` into new `live_display_watch.py` module.
- Vibe summarization for watched/followed commands now occurs after the live display is exited, using the captured output.

## [0.6.0] - 2025-05-04

### Added

- Define `RecoverableApiError` exception and `RECOVERABLE_API_ERROR_KEYWORDS` for better handling of transient API issues (rate limits, etc.).
- New `yaml_manifest` field to `LLMCommandResponse` schema to handle YAML input for commands like `create -f -`.
- Implement JSON schema (`LLMCommandResponse`) for structured LLM command planning responses.
- Update command planning prompts (get, describe, logs, version, etc.) to request JSON output conforming to the schema.
- Update `ModelAdapter` to support passing JSON schemas to compatible LLM models.
- Update `
