# Planned Changes for feature/vibectl-check

## 1. Subcommand Definition: `vibectl check <predicate>`

- **Objective**: Evaluate a given predicate about the Kubernetes cluster state and return an exit code indicating truthiness (0 for true, non-zero for false or error).
- **Autonomous Loop**: Similar to `vibectl auto`, it will autonomously execute a plan (sequence of kubectl commands) to determine the predicate's truthiness.
- **Read-Only Operations**:
    - Strictly limited to "read-only" kubectl verbs (e.g., `get`, `describe`, `logs`, `events`).
    - Prompting for the LLM planner will emphasize this read-only intent and caution against side-effects, even with safe verbs (e.g., in complex CRD/operator scenarios).
- **Exit Code Semantics**:
    - `0`: Predicate is confirmed to be true.
    - `1` (or other non-zero): Predicate is confirmed to be false.
    - Other non-zero codes (e.g., 2, 3) for:
        - Predicate is poorly posed or ambiguous.
        - Insufficient information or capability to confirm/deny the predicate (fail-safe).
- **Temporal Aspect**:
    - Predicates are evaluated for the present state by default.
    - Predicates with explicit temporal conditions (e.g., "on 2028-01-01, ...") will involve `WAIT` actions.
- **Fail-Safe Behavior**: Favor non-0 exit codes when unsure.

## 2. LLM Planner Enhancements

- **New Action Type**: Introduce a `DONE` action in the planner's schema.
    - `DONE` action will signify the end of the evaluation for `vibectl check`.
    - It will include an optional `exit_code` field (integer) to specify the intended exit code for `vibectl`. If not provided, a default non-zero might be assumed or determined by the planner's final assessment.
- **Schema Refactoring for LLM Responses**:
    - Evaluate current `LLMCommandResponse` (likely in `vibes.schema.llm_command_response`).
    - Consider renaming `LLMCommandResponse` to something more specific like `LLMVibePlanResponse` or `LLMAutoCommandResponse`.
    - Create a base schema for LLM plan responses.
    - The existing planner response (for `vibectl auto` and `vibectl diff`) would extend this base schema, possibly adding the `FEEDBACK` action type.
    - The new planner response for `vibectl check` would extend the base schema by adding the `DONE` action type.
    - This modularity should allow different subcommands to use tailored LLM planner schemas while sharing common elements (e.g., `THOUGHT`, `COMMAND`, `WAIT`).

## 3. Core Logic for `vibectl check`

- **Predicate Parsing/Understanding**: The LLM will be responsible for interpreting the natural language `<predicate>`.
- **Planner Integration**:
    - A new planner instance or configuration will be used for `vibectl check`.
    - It will use the enhanced schema with the `DONE` action.
    - The system prompt for this planner will be tailored to the "check" task, emphasizing read-only actions and the goal of determining predicate truthiness.
- **Execution Loop**:
    - Similar to `vibectl auto`, it will parse LLM responses, execute commands, and feed back results.
    - The loop terminates when a `DONE` action is received from the LLM.
    - The `vibectl` process will then exit with the `exit_code` specified in the `DONE` action (or a default if not specified/error).
- **Error Handling**: Robust error handling for LLM communication, command execution, and predicate evaluation.

## 4. CLI Implementation (Click)

- Add a new `click` command for `check`.
- Define arguments and options (e.g., `<predicate>`, potentially flags for verbosity, LLM model selection if applicable).

## 5. Prompt Engineering

- Carefully craft the system prompt for the `vibectl check` planner:
    - Emphasize the goal: determine if `<predicate>` is true.
    - Enforce read-only kubectl verbs.
    - Instruct on using the `DONE` action with an appropriate `exit_code`.
    - Guide on handling ambiguity or unanswerable predicates (leading to non-zero exit codes).

## 6. Testing

- Unit tests for schema changes.
- Unit tests for the new `DONE` action handling.
- Integration tests for the `vibectl check` subcommand with various predicates:
    - Simple true/false cases.
    - Cases requiring multiple steps.
    - Cases involving `WAIT`.
    - Cases leading to "poorly posed" or "cannot determine" outcomes.
    - Tests for correct exit codes.
- Mock LLM interactions extensively.

## Open Questions/Considerations:

1.  **Naming**: `vibectl check`. This naming is confirmed as suitable.
2.  **Exit Code Specificity**: The following scheme is confirmed:
    - `0`: Predicate TRUE.
    - `1`: Predicate FALSE.
    - `2`: Predicate poorly posed/ambiguous.
    - `3`: Cannot determine / timeout / planner gave up before confirming TRUE/FALSE.
3.  **Default `exit_code` for `DONE` action**: If the `DONE` action omits `exit_code`, it will default to `3` (cannot determine). This is confirmed.
4.  **Maximum Loop Iterations/Timeout**: `vibectl check` will have configurable maximum loop iterations and a timeout to prevent indefinite loops and ensure it can reach a "cannot determine" state (exit code 3). These will be configurable via CLI flags.
    - TODO: Implement a token budget for LLM interactions as well.
5.  **Schema Refactoring - Pydantic Models**: The approach of defining a base `LLMAction` Pydantic model, with specific actions (`ThoughtAction`, `CommandAction`, `WaitAction`, `FeedbackAction`, `DoneAction`) inheriting from it, and `LLMPlannerResponse` (renamed from `LLMCommandResponse`) containing `actions: list[LLMAction]`, is confirmed as a good approach for modularity and type safety.
6.  **"Safe" Verbs with Side Effects**: The initial approach will be to guide the LLM via prompt engineering to avoid side effects with "safe" verbs. If issues persist with specific CRDs/operators, more targeted restrictions can be considered later. This is confirmed.

## Phased Implementation Strategy

To manage complexity, the implementation of `vibectl check` will proceed in phases:

1.  **Phase 1: One-Shot Evaluation**
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

2.  **Phase 2: Iterative Execution Loop**
    *   **Objective**: Introduce the autonomous execution loop, allowing `vibectl check` to perform a sequence of read-only `kubectl` commands.
    *   **Behavior**:
        *   The system will iteratively call the LLM planner, execute `COMMAND` actions, handle `WAIT` actions, and feed results back to the LLM.
        *   The loop will terminate upon receiving a `DONE` action or an `ERROR` action from the LLM, or if the maximum iterations/timeout is reached.
    *   **Focus**:
        *   Implementing the main execution loop logic, similar to `vibectl auto` but restricted to read-only operations and the new planner schema.
        *   Handling the maximum loop iterations and timeout configurations.
        *   Refining the system prompt for iterative, read-only planning.
        *   Thorough testing of various predicate scenarios, including those requiring multiple steps and temporal conditions.
