# Planned Changes - JSON Schema for LLM Command Generation

**Goal:** Improve reliability and structure of LLM responses for command planning by using JSON schemas.

**Status:** MVP Implemented for `vibectl get vibe` command. Extended to most other planning prompts.

**Completed Items:**

- ✅ **Define JSON schema:**
  - Created `vibectl/types.py` with `ActionType` enum (`COMMAND`, `ERROR`, `WAIT`, `FEEDBACK`).
  - Created `vibectl/schema.py` with `LLMCommandResponse` Pydantic model including fields:
    - `action_type: ActionType`
    - `commands: Optional[List[str]]`
    - `yaml_manifest: Optional[str]`
    - `explanation: Optional[str]`
    - `error: Optional[str]`
    - `wait_duration_seconds: Optional[int]`
  - Added Pydantic validators to ensure field presence based on `action_type` (incl. `commands` OR `yaml_manifest` for `COMMAND`).
- ✅ **Update `create_planning_prompt` in `vibectl/prompt.py`:**
  - Modified prompt structure to request JSON output matching the schema.
  - Updated instructions to focus on extracting *target* resources/arguments, assuming the *action* (verb) is implied by the context.
  - Clarified instructions for the `commands` field to explicitly state it must be a JSON array of strings.
  - Updated example format to show full JSON output.
- ✅ **Refactor Planning Prompts (`PLAN_*_PROMPT` constants):**
  - Migrated most planning prompts (`get`, `describe`, `delete`, `logs`, `scale`, `rollout`, `wait`, `port-forward`, `version`, `cluster-info`, `events`) to use `create_planning_prompt`.
  - Updated examples in these prompts to remove action verbs and focus on target descriptions.
  - Updated `PLAN_CREATE_PROMPT` examples to include a mix of implicit and explicit creation requests.
- ✅ **Integrate schema usage with LLM calls:**
  - Updated `ModelAdapter.execute` and `LLMModelAdapter.execute` in `vibectl/model_adapter.py` to accept an optional `schema: dict` argument.
  - Modified `LLMModelAdapter` to pass the schema to the underlying `llm.prompt()` call if provided.
- ✅ **Implement JSON response parsing and handling:**
  - Modified `handle_vibe_request` in `vibectl/command_handler.py` to:
    - Generate the JSON schema dict from the Pydantic model.
    - Call `model_adapter.execute` with the schema.
    - Parse the response string using `LLMCommandResponse.model_validate_json()`.
    - Handle `JSONDecodeError` and Pydantic `ValidationError`.
    - Dispatch logic based on `response.action_type`.
    - Handle `yaml_manifest` field for `COMMAND` actions, passing it to `_execute_command`.
  - Modified `_execute_command` to use `run_kubectl_with_yaml` when `yaml_manifest` is present.
  - **Fix:** Resolved prompt formatting issues caused by `{}` in the schema string by using a unique placeholder (`__REQUEST_PLACEHOLDER__`) and `.replace()` instead of `.format()`.
  - **Fix:** Added explicit string-to-enum conversion for `action_type` after parsing.
  - **Fix:** Ensured the original command verb (e.g., `get`) is passed down correctly.
  - **Fix:** Corrected `update_memory` calls within `handle_vibe_request`.
- ✅ **Add basic schema validation:**
  - Pydantic model handles basic validation during parsing.
  - Added checks for required fields based on `action_type` within the handler.
- ✅ **Testing:**
  - Added and fixed various tests in `tests/test_command_handler_edge_cases.py` covering JSON parsing/validation errors, autonomous mode, etc.
  - Updated tests in `tests/test_prompt.py` to align with the refactored `create_planning_prompt` and new example formats.
- ✅ **Refinements & Fixes:**
  - Clarified `kubectl events` usage in `PLAN_EVENTS_PROMPT`.
  - Removed redundant `flags` argument from `create_planning_prompt`.
  - Fixed redundant AI explanation print during command confirmation.
  - Replaced debug `print` with `logger.debug`.
  - Fixed `AttributeError` in `_handle_command_confirmation`.
  - Fixed persistent Mypy assignment errors.

**Decisions & Compromises:**

- **MVP First:** Focused implementation on `vibectl get vibe` command planning (`PLAN_GET_PROMPT`) initially, then expanded to other commands.
- **Happy Path Focus:** Primarily tested and addressed issues related to successful schema generation and parsing. Added some specific error handling tests.
- **Schema Tooling:** Leveraged the `llm` library's built-in support for schema arguments.
- **Command Joining:** Currently deriving `kubectl_verb` and `kubectl_args` from the `commands: List[str]` in `handle_vibe_request`. This works reasonably well but might need refinement for commands requiring more complex argument handling (e.g., quoted strings, heredocs handled via YAML).

**Deferred Items / Technical Debt:**

- **Fallback Mechanism:** Did not implement fallback for models that don't support native schema prompting. Currently assumes the model works or fails during the `model_adapter.execute` call.
- **Complex Argument Handling:** As noted above, the derivation/joining of `commands` might be insufficient for all command types.
- **`PLAN_VIBE_PROMPT`:** This general planning prompt still uses the old format and needs refactoring.

**Next Steps:**

- **Testing:**
  - Add comprehensive unit/integration tests for `vibectl/schema.py`.
  - **Refine/Expand tests for `handle_vibe_request`:** Consider more scenarios for `COMMAND`, `ERROR`, `WAIT`, `FEEDBACK` action types.
  - **TODO:** Increase test coverage for `vibectl/command_handler.py` towards 100%.
  - **TODO:** Increase test coverage for `vibectl/memory.py` towards 100%.
- **Refinement:**
  - Test planning prompts with more complex requests to ensure robustness.
  - Monitor LLM adherence to the schema and adjust prompts if needed.
- **Expansion:**
  - Apply the schema pattern to `PLAN_VIBE_PROMPT`.
  - Re-evaluate and potentially refactor the `commands` list handling if needed for other command types.
- **Fallback Implementation (Post-MVP):** Design and implement the fallback mechanism for models lacking direct schema support.
