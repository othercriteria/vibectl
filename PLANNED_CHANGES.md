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

1.  **Naming**: `vibectl check` seems acceptable unless a strong counter-argument arises.
2.  **Exit Code Specificity**: Suggested scheme:
    - `0`: Predicate TRUE.
    - `1`: Predicate FALSE.
    - `2`: Predicate poorly posed/ambiguous.
    - `3`: Cannot determine / timeout / planner gave up before confirming TRUE/FALSE.
    *(This needs your confirmation or alternative proposal.)*
3.  **Default `exit_code` for `DONE` action**: If `DONE` action omits `exit_code`, what should it default to? Perhaps `3` (cannot determine)?
4.  **Maximum Loop Iterations/Timeout**: `vibectl check` should likely have a configurable maximum number of iterations or a timeout to prevent indefinite loops and ensure it can reach a "cannot determine" state (exit code 3).
5.  **Schema Refactoring - Pydantic Models**:
    - Propose defining a base `LLMAction` Pydantic model.
    - Specific actions (`ThoughtAction`, `CommandAction`, `WaitAction`, `FeedbackAction`, `DoneAction`) inherit from `LLMAction`.
    - `LLMPlannerResponse` (renamed from `LLMCommandResponse`) would contain `actions: list[LLMAction]`.
    *(This seems like a good approach for modularity and type safety.)*
6.  **"Safe" Verbs with Side Effects**: Start with prompt engineering to guide the LLM. If issues arise with specific CRDs/operators causing side effects even with `get`, we can consider more targeted restrictions later (e.g., deny-listing certain GVKs for the `check` subcommand).
