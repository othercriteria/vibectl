# Planned Changes for Apply and Diff Subcommands

## Kubectl Apply Subcommand (Detailed Plan)

**High-Level Goal for `vibectl apply vibe "<user_input_string>"`:**

1.  **Scope Files (LLM):** Determine files/directories and remaining intent from the user's request.
2.  **Gather & Validate (Local):** Collect actual file paths and perform initial syntactic validation.
3.  **Summarize Valid (LLM):** For valid manifests, create summaries and build an operation-specific memory.
4.  **Correct/Generate Invalid (LLM):** For invalid/non-manifest files, use an LLM to attempt correction or generation into valid manifests, saving them to temporary locations.
5.  **Plan Final Apply (LLM):** Use all validated original and corrected temporary manifests, plus the remaining user intent, to plan the final `kubectl apply` command(s).
6.  **Execute & Cleanup (Local):** Execute the planned commands and clean up temporary files.

**Detailed Steps:**

**Core Module:** `vibectl.subcommands.apply_cmd.py` (housing a main async function like `handle_apply_vibe_request`)

**Key Data Structures (managed within `handle_apply_vibe_request`):**
*   `user_input_string: str`
*   `llm_scoped_files: list[str]`
*   `llm_remaining_request: str`
*   `discovered_manifest_sources: list[Path]`
*   `valid_manifest_paths: list[Path]`
*   `invalid_sources_to_correct: list[tuple[Path, str | None]]`
*   `corrected_temp_manifest_paths: list[Path]`
*   `unresolvable_sources: list[tuple[Path, str]]`
*   `apply_operation_memory: str`

**Step 1: Initial Scoping & Intent Extraction (LLM)**
*   **Prompt:** `PLAN_APPLY_FILESCOPE_PROMPT` (new)
    *   **Input:** Raw `<user_input_string>`.
    *   **Instruction:** Analyze request. Identify file paths, directory paths, or patterns for `kubectl apply`. Extract remaining non-file-specific instructions.
    *   **Output Schema (`ApplyFileScopeResponse` - new in `schema.py`):**
        ```python
        class ApplyFileScopeResponse(BaseModel):
            file_selectors: list[str]
            remaining_request_context: str
        ```
*   **Action in `apply_cmd.py`:** Call LLM, store results.

**Step 2: File Discovery & Initial Validation (Local)**
*   **Action in `apply_cmd.py`:**
    1.  Expand `llm_scoped_files` to `discovered_manifest_sources`.
    2.  For each file in `discovered_manifest_sources`:
        *   Try parsing (e.g., `yaml.safe_load_all`).
        *   If valid: add to `valid_manifest_paths`.
        *   If invalid/not YAML/JSON: add to `invalid_sources_to_correct`.

**Step 3: Summarize Valid Manifests & Build Operation Memory (LLM)**
*   **Prompt:** `SUMMARIZE_APPLY_MANIFEST_PROMPT` (new)
    *   **Input:** Manifest content, current `apply_operation_memory`.
    *   **Instruction:** Summarize resource(s). Consider previous summaries.
    *   **Output:** Plain text summary.
*   **Action in `apply_cmd.py`:**
    1.  Initialize `apply_operation_memory`.
    2.  For each file in `valid_manifest_paths`: Call LLM, append summary to `apply_operation_memory`.

**Step 4: Correction/Generation Loop for Invalid Sources (LLM)**
*   **Prompt:** `CORRECT_APPLY_MANIFEST_PROMPT` (new)
    *   **Input:** Original path, content, error reason, `apply_operation_memory`, `llm_remaining_request`.
    *   **Instruction:** Generate/fix manifest YAML based on input.
    *   **Output:** Proposed YAML manifest string.
*   **Action in `apply_cmd.py`:**
    1.  Loop through `invalid_sources_to_correct` (with retries):
        *   Call LLM.
        *   If response is valid YAML:
            *   Save to temp file, add path to `corrected_temp_manifest_paths`.
            *   *(Recommended)* Summarize new manifest, update `apply_operation_memory`.
            *   *(Optional)* Show diff, await confirmation if not `--yes`.
        *   Else (invalid YAML/retries exhausted): Add to `unresolvable_sources`.

**Step 5: Plan Final `kubectl apply` Command(s) (LLM)**
*   **Prompt:** `PLAN_FINAL_APPLY_COMMAND_PROMPT` (new)
    *   **Input:** `valid_original_manifest_paths`, `corrected_temp_manifest_paths`, `llm_remaining_request`, `apply_operation_memory`, `unresolvable_sources`.
    *   **Instruction:** Formulate `kubectl apply` command(s) using all manifests. Output `list[LLMCommandResponse]`. Specify `allowed_exit_codes`.
    *   **Output Schema:** `list[LLMCommandResponse]`.
*   **Action in `apply_cmd.py`:**
    1.  Gather all manifests for apply.
    2.  Call LLM. Parse response.
    3.  For each planned command: Display, confirm (if needed), execute via `_execute_command`, process output.

**Step 6: Cleanup and Reporting (Local)**
*   **Action in `apply_cmd.py` (finally block):** Delete temp files.
*   **Final Report:** Summarize outcomes, list unresolvable sources.

**Key Considerations:**
*   **Prompt Engineering:** Success depends on the 4 new prompts.
*   **User Interaction:** Balance automation with user confirmation for LLM changes.
*   **Natural Language Handling:** Scope for "text to manifest" needs careful definition.
*   **Server-Side Validation:** Consider `kubectl apply --dry-run=server` in Step 4.
*   **Performance:** Multiple LLM calls will add latency.
*   **Error Handling:** Robustness is key at each step.
*   **Kustomize:** Current plan focuses on `-f`/`-R`. Future `-k` support would need changes in Step 1 & 2.

## Shared Functionality
- Develop common utilities for file handling and resource parsing.
- Ensure consistent error handling and reporting.
