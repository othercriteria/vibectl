# Changelog

All notable changes to the vibectl project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Planned: Implement streaming LLM responses for Vibe, starting with `vibe` command output. (WIP)

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
- Update `handle_vibe_request` to generate schema, parse JSON response, and dispatch based on `action_type`.
- Add basic schema validation via Pydantic model and handler checks.
- Correct prompt formatting in `semiauto` mode to properly include memory context, preventing incorrect LLM requests.
- Resolved `AttributeError` related to asyncio patching in tests.
- Corrected assertions for error string handling in `command_handler` memory tests.
- Fixed `IndexError` and lint warnings in `port-forward` keyboard interrupt tests.
- Added missing `summary_prompt_func` arguments to internal subcommand calls.

### Changed

- Refactor `PLAN_VIBE_PROMPT` to use the JSON schema approach for planning.
- Update `model_adapter.py` to use `schema=` parameter for `llm` library compatibility.
- Update error handling in `command_handler` to use `RecoverableApiError` and improve error reporting during Vibe processing.
- Refine logic for determining `kubectl` verb/args in `handle_vibe_request` based on original command context.
- Improve prompt display in `_handle_command_confirmation`.
- Adjust `autonomous_mode` logic in `vibe_cmd.py`.
- Refactor exception handling in `auto_cmd.py` loop.
- Remove automatic confirmation bypass for `semiauto` mode.
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
- **[Demo]** Major enhancements to Chaos Monkey demo:
  - Improved overseer dashboard with real-time cluster resource data (nodes, pods, namespaces, resource quotas), pod age/restarts, and better formatting.
  - Enhanced poller with more robust Kubernetes checks, deployment readiness waits, and `PENDING` status.
  - Refined monitoring intervals and background task handling in overseer.
  - Added UI staleness detection and warning banner.
  - Updated README with detailed component descriptions, configuration, and troubleshooting.
  - Switched demo phases from session duration to distinct passive/active phases.
  - Updated `run.sh` script with new duration parameters and stable version definitions.
  - **[Demo]** Refined Chaos Monkey demo components:
    - Added `chaos-monkey-system` namespace for agents, poller, overseer.
    - Agents, Poller, Overseer now use dedicated kubeconfigs generated by sandbox entrypoint.
    - Updated RBAC rules and sandbox entrypoint logic for phased permissions.
    - Updated Kind version and added `jq` dependency.
    - Adjusted resource quotas and agent instructions.
    - Removed redundant `OVERSEER_HOST`/`PORT` env vars from non-Overseer components.
    - Added new Overseer configuration variables (`METRICS_INTERVAL`, etc.).
    - Updated Docker health check for the sandbox.
    - Updated README to reflect new setup, configuration, and troubleshooting details.

### Fixed

- Fix test failures related to `schema=` parameter change in `model_adapter`.
- Correct `execute` method signatures in test mock adapters to align with base class and resolve mypy errors.
- Correct `BaseModel` imports in test files (`pydantic` vs `typing`).
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
  - Makefile for easy management (`make up`, `make down`, `
