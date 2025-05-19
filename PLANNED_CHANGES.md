# Planned Changes for feature/vibectl-check

## 1. Subcommand Definition: `vibectl check <predicate>` - Partially Implemented

- **Objective**: Evaluate a given predicate about the Kubernetes cluster state and return an exit code indicating truthiness (0 for true, non-zero for false or error).
- **Autonomous Loop**: Similar to `vibectl auto`, it will autonomously execute a plan (sequence of kubectl commands) to determine the predicate's truthiness. - Partially Implemented (Works for predicates resolvable from memory; does not yet execute command sequences for data gathering).
- **Read-Only Operations**:
    - Strictly limited to "read-only" kubectl verbs (e.g., `get`, `describe`, `logs`, `events`). - Implemented (in planner schema and prompting, but command execution for data gathering not yet observed for `check`).
    - Prompting for the LLM planner will emphasize this read-only intent and caution against side-effects, even with safe verbs (e.g., in complex CRD/operator scenarios). - Implemented
- **Exit Code Semantics**: - Implemented (Observed working for 0, 1, and 3).

## 2. LLM Planner Enhancements - Implemented

- **New Action Type**: Introduce a `DONE` action in the planner's schema. - Implemented (Observed working with correct exit codes for memory-based checks).

## 3. Core Logic for `vibectl check` - Partially Implemented

- **Predicate Parsing/Understanding**: The LLM will be responsible for interpreting the natural language `<predicate>`. - Implemented (Works for predicates resolvable from memory; ability to form plans for data-dependent predicates needs verification).
- **Planner Integration**:
    - A new planner instance or configuration will be used for `vibectl check`. - Implemented
    - It will use the enhanced schema with the `DONE` action. - Implemented
    - The system prompt for this planner will be tailored to the "check" task, emphasizing read-only actions and the goal of determining predicate truthiness. - Implemented (Current tailoring might be too restrictive, preventing multi-step command plans for data gathering).
- **Execution Loop**:
    - Similar to `vibectl auto`, it will parse LLM responses, execute commands, and feed back results. - Partially Implemented (Loop correctly processes `DONE` actions. However, execution of `COMMAND` actions for information gathering before deciding "Cannot Determine" is not occurring as expected for data-dependent predicates).
    - The loop terminates when a `DONE` action is received from the LLM. - Implemented
    - The `vibectl` process will then exit with the `exit_code` specified in the `DONE` action (or a default if not specified/error). - Implemented
- **Error Handling**: Robust error handling for LLM communication, command execution, and predicate evaluation. - Implemented (for paths observed).

## 4. CLI Implementation (Click) - Implemented

- Add a new `click` command for `check`.
- Define arguments and options (e.g., `<predicate>`, potentially flags for verbosity, LLM model selection if applicable).

## 5. Prompt Engineering - Implemented (Needs Review)

- Carefully craft the system prompt for the `vibectl check` planner:
    - Emphasize the goal: determine if `<predicate>` is true.
    - Enforce read-only kubectl verbs.
    - Instruct on using the `DONE` action with an appropriate `exit_code`.
    - Guide on handling ambiguity or unanswerable predicates (leading to non-zero exit codes).
    - Note: Current prompting may be too restrictive, leading the LLM to avoid planning necessary read-only commands and prematurely exiting with 'Cannot Determine' for data-dependent predicates.

## 6. Testing - Partially Implemented

- Unit tests for schema changes. - Implemented
- Unit tests for the new `DONE` action handling. - Implemented
- Integration tests for the `vibectl check` subcommand with various predicates:
    - Simple true/false cases. - Implemented (Verified working for memory-based predicates).
    - Cases requiring multiple steps. - Needs Verification (Current behavior suggests these are not working as intended; command execution for data gathering is not occurring, leading to exit code 3).
    - Cases involving `WAIT`. - Implemented (as part of general WAIT action capability, but applicability within `check` for multi-step plans is unverified).
    - Cases leading to "poorly posed" or "cannot determine" outcomes. - Implemented (Exit code 3 path is active).
    - Tests for correct exit codes. - Implemented (Verified for 0, 1, 3).

## Open Questions/Considerations: - All addressed/confirmed

1.  **Naming**: `vibectl check`. This naming is confirmed as suitable.
2.  **Exit Code Specificity**: The following scheme is confirmed:
    - `0`: Predicate TRUE.
    - `1`: Predicate FALSE.
    - `2`: Predicate poorly posed/ambiguous.
    - `3`: Cannot determine / timeout / planner gave up before confirming TRUE/FALSE.
3.  **Default `exit_code` for `DONE` action**: If the `DONE` action omits `exit_code`, it will default to `3` (cannot determine). This is confirmed.
4.  **Maximum Loop Iterations/Timeout**: `vibectl check` will have configurable maximum loop iterations and a timeout to prevent indefinite loops and ensure it can reach a "cannot determine" state (exit code 3). These will be configurable via CLI flags. - Implemented
    - TODO: Implement a token budget for LLM interactions as well. (Deferred to future enhancement)
5.  **Schema Refactoring - Pydantic Models**: The approach of defining a base `LLMAction` Pydantic model, with specific actions (`ThoughtAction`, `CommandAction`, `WaitAction`, `FeedbackAction`, `DoneAction`) inheriting from it, and `LLMPlannerResponse` (renamed from `LLMCommandResponse`) containing `actions: list[LLMAction]`, is confirmed as a good approach for modularity and type safety. - Implemented
6.  **"Safe" Verbs with Side Effects**: The initial approach will be to guide the LLM via prompt engineering to avoid side effects with "safe" verbs. If issues persist with specific CRDs/operators, more targeted restrictions can be considered later. This is confirmed. - Implemented (via prompt engineering)

## Phased Implementation Strategy - Phase 1 Completed, Phase 2 Partially Implemented

To manage complexity, the implementation of `vibectl check` will proceed in phases:

1.  **Phase 1: One-Shot Evaluation - Completed and Verified**
    *   **Objective**: Implement the core predicate evaluation logic without a command execution loop. This is equivalent to having zero loop iterations remaining.
    *   **Behavior**:
        *   The LLM will be prompted to evaluate the `<predicate>` based on the current state of its memory (if any, though likely minimal for the first interaction).
        *   The system prompt will strongly encourage the LLM to respond with a `DONE` action (with the appropriate `exit_code`) or an `ERROR` action if the predicate cannot be immediately assessed or is invalid.
        *   If the LLM responds with `COMMAND` or `WAIT` actions in this phase, `vibectl check` will interpret this as an inability to determine the predicate's truthiness with the single allowed interaction, and will therefore exit with code `3` (Cannot determine).
    *   **Focus**: This phase will concentrate on:
        *   Setting up the new CLI command (`vibectl check`).
        *   Implementing the new `DONE` action in the schema.
        *   Crafting the initial system prompt for one-shot evaluation.
        *   Ensuring correct exit code handling for `DONE` and `ERROR` responses, and for the implicit "cannot determine" case if `COMMAND`/`WAIT` is returned.
    *   **Status**: Verified as working correctly, especially for predicates resolvable from existing memory context.

2.  **Phase 2: Iterative Execution Loop - Partially Implemented**
    *   **Objective**: Introduce the autonomous execution loop, allowing `vibectl check` to perform a sequence of read-only `kubectl` commands.
    *   **Behavior**:
        *   The system will iteratively call the LLM planner, execute `COMMAND` actions, handle `WAIT` actions, and feed results back to the LLM.
        *   The loop will terminate upon receiving a `DONE` action or an `ERROR` action from the LLM, or if the maximum iterations/timeout is reached.
    *   **Focus**:
        *   Implementing the main execution loop logic, similar to `vibectl auto` but restricted to read-only operations and the new planner schema.
        *   Handling the maximum loop iterations and timeout configurations.
        *   Refining the system prompt for iterative, read-only planning.
        *   Thorough testing of various predicate scenarios, including those requiring multiple steps and temporal conditions.
    *   **Status**: The loop structure and `DONE`/`ERROR` termination are likely in place. However, the critical functionality of executing `COMMAND` actions to gather new information for data-dependent predicates is not working as expected; the system currently defaults to "Cannot Determine" (exit 3) in such cases instead of attempting to run commands. Configuration of loop iterations/timeout for `check` may also need review.
