# `vibectl check` - Predicate Evaluation for Kubernetes

This document outlines the functionality of the `vibectl check <predicate>` command and tracks its development.

## How `vibectl check` Works (System Overview)

The `vibectl check <predicate>` command evaluates a given natural language predicate about the Kubernetes cluster's state. It returns an exit code indicating the predicate's truthiness (0 for true, non-zero for false or error).

### Core Functionality

- **Predicate Evaluation**: The command takes a user-supplied natural language `<predicate>` as input.
- **Autonomous Loop**: Similar to `vibectl auto`, it can autonomously execute a sequence of `kubectl` commands to gather the necessary information to determine the predicate's truthiness.
- **Read-Only Operations**: The command is strictly limited to read-only `kubectl` verbs (e.g., `get`, `describe`, `logs`, `events`). This is enforced through prompt engineering and schema validation. The LLM planner is instructed to avoid any actions that would modify cluster state.
- **LLM Planner Integration**:
  - A dedicated planner configuration is used for `vibectl check`.
  - The planner utilizes an enhanced schema that includes a `DONE` action, allowing the LLM to signal the completion of predicate evaluation with a specific exit code.
  - The system prompt for this planner is tailored to the "check" task, emphasizing read-only actions and the primary goal of determining the truthiness of the *original user-supplied predicate*.
- **Execution Loop**:
  - The system iteratively communicates with the LLM planner.
  - It executes `COMMAND` actions proposed by the LLM to gather data.
  - Results from command executions are fed back to the LLM for subsequent planning steps.
  - The loop terminates when a `DONE` action (indicating the predicate's evaluation is complete) or an `ERROR` action is received, or if maximum iterations/timeout are reached.
- **CLI Implementation**: A `click` command (`vibectl check`) provides the user interface, accepting the `<predicate>` and other flags (e.g., for verbosity, LLM model selection).
- **Error Handling**: The system includes robust error handling for LLM communication, command execution failures, and issues in predicate evaluation.

### Exit Code Semantics

The command uses the following exit codes, formally defined in `vibectl.types.PredicateCheckExitCode`:

- `0` (`PredicateCheckExitCode.TRUE`): Predicate is TRUE.
- `1` (`PredicateCheckExitCode.FALSE`): Predicate is FALSE.
- `2` (`PredicateCheckExitCode.POORLY_POSED`): Predicate is poorly posed or ambiguous in a Kubernetes context.
- `3` (`PredicateCheckExitCode.CANNOT_DETERMINE`): Cannot determine truthiness (e.g., insufficient information, timeout, planner gave up, or an error occurred during execution). This is the default if a `DONE` action omits an `exit_code`.

### Configuration

- **Maximum Loop Iterations/Timeout**: `vibectl check` has configurable maximum loop iterations and a timeout to prevent indefinite loops and to allow it to reach a "cannot determine" state (exit code `PredicateCheckExitCode.CANNOT_DETERMINE`) if necessary. These are configurable via CLI flags.

## Key Design Aspects & Prompt Engineering Notes

### Addressing Semantic Drift

A significant challenge during development was "semantic drift," where the LLM would deviate from the original user-supplied predicate after a few interactions or data gathering steps.

- **Initial Observation of Drift**:
  For a predicate like "there are pods in the current namespace with the 'CrashLoopBackOff' status":
  1. LLM correctly issued `kubectl get pods -n sandbox -o wide`. The output showed no pods in `CrashLoopBackOff`.
  2. Instead of concluding, the LLM then issued `kubectl get deployments -n sandbox` (seeking broader, less relevant context).
  3. Subsequently, the LLM errored, stating "I need a specific predicate to evaluate," having completely lost the original task.

- **Mitigation Strategy - Anchoring the Predicate**:
  The primary mitigation has been to ensure that the *original user-supplied predicate* is consistently re-introduced into the LLM's "Request Context" during each iteration of the planning loop. This provides a constant anchor, reminding the LLM of its primary goal.

- **System Prompt Reinforcement**:
  The system prompt for the `vibectl check` planner strongly emphasizes:
  - The goal: determine if the *original user-supplied* `<predicate>` is true.
  - The need to maintain focus on this predicate throughout the evaluation.
  - Instructions on using the `DONE` action with an appropriate `exit_code` based *only* on the evaluation of the original predicate.
  - Guidance on handling ambiguity or unanswerable predicates.

Ongoing monitoring and refinement of prompts are essential to ensure robust and accurate predicate evaluation across diverse scenarios.

### Schema Notes

- The `CommandAction.commands` field in `schema.py` is `list[str]`, representing the arguments for a single `kubectl` command. The LLM correctly adheres to this.

## Current Implementation Status (Summary of Initial Plan Items)

The initial phased implementation plan has largely been completed:

- **Phase 1 (One-Shot Evaluation)**: Core predicate evaluation without a command execution loop (equivalent to zero iterations) was implemented and verified. This included the new CLI command, the `DONE` action, initial system prompt, and exit code handling.
- **Phase 2 (Iterative Execution Loop)**: The autonomous execution loop, allowing sequences of read-only commands, is implemented.
  - The loop structure, action handling (`DONE`, `ERROR`, `THOUGHT`, `WAIT`, `COMMAND`), and command execution are functional.
  - Maximum loop iterations and timeout configurations are in place.
  - Significant progress has been made on addressing semantic drift through prompt engineering, as described above.

**Overall status of originally planned items:**

- **Subcommand Definition**: Implemented.
- **LLM Planner Enhancements (`DONE` action)**: Implemented.
- **Core Logic (Predicate Parsing, Planner Integration, Execution Loop, Error Handling)**: Implemented, with ongoing focus on semantic accuracy refinement.
- **CLI Implementation (Click)**: Implemented.

## Outstanding Work & Future Enhancements

1. **Comprehensive Testing & Semantic Accuracy Validation**:
    - **Action**: Expand test coverage significantly for `vibectl check`.
    - **Details**:
        - Create more unit tests for schema changes and action handling.
        - Develop a comprehensive suite of integration tests for `vibectl check` covering diverse predicates:
            - Simple true/false cases (both memory-based and data-dependent), specifically verifying the `DoneAction.explanation` for semantic fidelity to the *original* predicate.
            - Cases requiring multiple `kubectl` command execution steps, ensuring the LLM maintains focus on the original predicate across these steps.
            - Scenarios involving `WAIT` actions (if applicable within complex checks).
            - Predicates designed to lead to "poorly posed" (exit code `PredicateCheckExitCode.POORLY_POSED`) or "cannot determine" (exit code `PredicateCheckExitCode.CANNOT_DETERMINE`) outcomes, verifying the reasoning aligns with the original predicate.
            - Thoroughly test the correctness of all exit codes (`PredicateCheckExitCode.TRUE`, `PredicateCheckExitCode.FALSE`, `PredicateCheckExitCode.POORLY_POSED`, `PredicateCheckExitCode.CANNOT_DETERMINE`).
            - Test error handling for failed `kubectl` commands (e.g., ensuring they lead to a "cannot determine" state with appropriate explanation related to the original predicate).
        - **Critical**: Design and implement tests specifically to detect and prevent "semantic drift" regressions.

2. **Ongoing Prompt Refinement & Robustness**:
    - **Action**: Continuously monitor `vibectl check` behavior with various complex predicates and real-world scenarios.
    - **Details**:
        - Refine system and user prompts as needed to further improve clarity, accuracy, and robustness against semantic drift.
        - Ensure the LLM's explanations in `DoneAction` clearly articulate how the gathered information confirms or denies the *original user-supplied predicate*.

3. **Verify Structural Wiring of CLI Entry Point**:
    - **Action**: Explicitly verify or (if necessary) modify `vibectl/subcommands/check_cmd.py`.
    - **Details**: Confirm that its `run_check_command` function correctly calls the specialized execution loop found in `vibectl.execution.check.run_check_command` and not a generic handler. Ensure all necessary parameters (predicate, output flags, etc.) are correctly passed.
    - **Impact**: Guarantees the correct execution logic for `vibectl check` is always used.

4. **Schema Clarity Enhancement (Minor)**:
    - **Action**: In `vibectl/schema.py`.
    - **Details**: Rename `CommandAction.commands` to `CommandAction.args` to better reflect that it contains arguments for a single command.
    - **Impact**: Improves code readability and maintainability. (This is a non-blocking cleanup task).

5. **Token Budget Implementation (Future Enhancement)**:
    - **Action**: Implement a token budget for LLM interactions within the `vibectl check` loop.
    - **Details**: This will help manage costs and prevent unexpectedly long interactions if other loop termination conditions aren't met.
    - **Status**: Deferred from the initial plan, to be considered as a future enhancement.
