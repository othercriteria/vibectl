# Predicate Evaluation with `vibectl check`

The `vibectl check <predicate>` command evaluates a given natural language predicate about the Kubernetes cluster's state. It returns an exit code indicating the predicate's truthiness (0 for true, non-zero for false or error), making it useful for scripting and automated checks.

## How `vibectl check` Works

The `vibectl check <predicate>` command leverages an AI model to determine if a statement you provide about your Kubernetes cluster is true or false.

### Core Functionality

- **Predicate Evaluation**: You provide a natural language `<predicate>` (a statement) as input, like `"all pods in the default namespace are running"` or `"the nginx deployment has at least 3 replicas"`.
- **Autonomous Loop**: Similar to `vibectl auto`, the `check` command can autonomously execute a sequence of `kubectl` commands. It uses these commands to gather the necessary information from your cluster to determine if your predicate is true.
- **Read-Only Operations**: To ensure safety, `vibectl check` is strictly limited to read-only `kubectl` operations (e.g., `get`, `describe`, `logs`). The AI planner is instructed to avoid any actions that would modify cluster state.
- **AI Planner Integration**:
    - A specialized AI planner configuration is used for `vibectl check`.
    - The planner aims to determine the truthiness of the *original user-supplied predicate*.
- **Execution Loop**:
    - The system iteratively communicates with the AI planner.
    - It executes `kubectl` commands proposed by the AI to gather data.
    - Results from command executions are fed back to the AI for subsequent planning steps.
    - The loop terminates when the AI signals it has an answer (`DONE` action), if an unrecoverable error occurs, or if maximum iterations/timeout are reached.
- **CLI Implementation**: The `vibectl check <predicate>` command provides the user interface, accepting the predicate and other flags (e.g., for verbosity, AI model selection).
- **Error Handling**: The system includes robust error handling for AI communication, command execution failures, and issues in predicate evaluation.

### Exit Code Semantics

The command uses the following exit codes, formally defined in `vibectl.types.PredicateCheckExitCode`:

- `0` (`PredicateCheckExitCode.TRUE`): Predicate is TRUE.
- `1` (`PredicateCheckExitCode.FALSE`): Predicate is FALSE.
- `2` (`PredicateCheckExitCode.POORLY_POSED`): Predicate is poorly posed or ambiguous in a Kubernetes context (e.g., "is the cluster happy?").
- `3` (`PredicateCheckExitCode.CANNOT_DETERMINE`): Cannot determine truthiness. This can happen if there's insufficient information, a timeout occurs, the AI planner gives up, or an error occurs during execution. This is also the default if the AI omits an `exit_code` when it finishes.

### Configuration

- **Maximum Loop Iterations/Timeout**: `vibectl check` has configurable maximum loop iterations and a timeout to prevent indefinite loops. If these limits are reached, it will typically exit with `PredicateCheckExitCode.CANNOT_DETERMINE`.

## Worked Example

The following demonstrates the iterative evaluation process for a complex predicate. `vibectl check` makes multiple calls to the AI, executing `kubectl` commands planned by the AI to gather information, and updating its working memory with the results. The original predicate and the updated memory are provided to the AI in each subsequent iteration until it can determine the predicate's truthiness.

**Predicate:** `"k8s server version is newer than v1.28.x and there are pods in the current working namespace with the 'Failed' status"`

**Execution Flow (Simplified):**

1.  **Iteration 1:**
    *   **AI Input:** Predicate + Initial (empty) Memory.
    *   **AI Plan:** `COMMAND: kubectl version --output=json` (to check server version).
    *   **Action:** `kubectl version` is executed.
    *   **Memory Update:** Output of `kubectl version` (e.g., server version is v1.32.4) is added to memory.

2.  **Iteration 2:**
    *   **AI Input:** Predicate + Updated Memory (containing server version info).
    *   **AI Plan:** `COMMAND: kubectl get pods --field-selector=status.phase=Failed` (to check for failed pods).
    *   **Action:** `kubectl get pods ...` is executed.
    *   **Memory Update:** Output of `kubectl get pods` (e.g., no pods found in 'Failed' state) is added to memory.

3.  **Iteration 3:**
    *   **AI Input:** Predicate + Further Updated Memory (containing server version and failed pod status).
    *   **AI Plan:** `DONE: exit_code=1` (Predicate is FALSE).
        *   **Explanation:** "The server version (v1.32.4) *is* newer than v1.28.x (TRUE). However, no pods were found in 'Failed' status (FALSE). Since one part of the AND condition is false, the entire predicate is FALSE."
    *   **Action:** Loop terminates. `vibectl` exits with code 1.

This example shows how the AI iteratively gathers information, using its memory to build context, until it can confidently evaluate the original, potentially complex, predicate.
