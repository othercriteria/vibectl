# Planned Changes - JSON Schema for LLM Command Generation

**Goal:** Improve reliability and structure of LLM responses for command planning by using JSON schemas.

**Status:** MVP Implemented for `vibectl get vibe` command.

**Completed Items:**

- ✅ **Define JSON schema:**
  - Created `vibectl/types.py` with `ActionType` enum (`COMMAND`, `ERROR`, `WAIT`, `FEEDBACK`).
  - Created `vibectl/schema.py` with `LLMCommandResponse` Pydantic model including fields:
    - `action_type: ActionType`
    - `commands: Optional[List[str]]`
    - `explanation: Optional[str]`
    - `error: Optional[str]`
    - `wait_duration_seconds: Optional[int]`
  - Added Pydantic validators to ensure field presence based on `action_type`.
- ✅ **Update `get` command planning prompt:**
  - Modified `create_planning_prompt` in `vibectl/prompt.py` to accept a schema definition.
  - Updated the prompt structure to request JSON output matching the schema.
  - Updated `PLAN_GET_PROMPT` to utilize the schema.
  - **Fix:** Resolved prompt formatting issues caused by `{}` in the schema string by using a unique placeholder (`__REQUEST_PLACEHOLDER__`) and `.replace()` instead of `.format()`.
  - **Refinement:** Clarified instructions for the `commands` field to explicitly state it should contain arguments *following* `kubectl get`.
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
  - **Fix:** Added explicit string-to-enum conversion for `action_type` after parsing to handle cases where Pydantic returned a string instead of an enum member.
  - **Fix:** Ensured the original command verb (e.g., `get`) is passed down correctly.
  - **Fix:** Corrected `update_memory` calls within `handle_vibe_request` (e.g., missing arguments, correct arguments in autonomous mode).
- ✅ **Add basic schema validation:**
  - Pydantic model handles basic validation during parsing.
  - Added checks for required fields based on `action_type` within the handler.
- ✅ **Testing (Initial Pass):**
  - Added and fixed various tests in `tests/test_command_handler_edge_cases.py` covering:
    - JSON parsing/validation errors (`test_handle_vibe_request_command_parser_error`).
    - Autonomous mode success path (`test_handle_vibe_request_autonomous_mode`).
    - Handling of missing/empty commands in `COMMAND` action type.
    - Handling of LLM returning an empty response or an error.
  - Fixed issues identified during testing related to mock interactions and assertion logic.

**Decisions & Compromises:**

- **MVP First:** Focused implementation on `vibectl get vibe` command planning (`PLAN_GET_PROMPT`) to prove the concept.
- **Happy Path Focus:** Primarily tested and addressed issues related to successful schema generation and parsing, assuming the model supports and follows the schema instruction. Added some specific error handling tests.
- **Schema Tooling:** Leveraged the `llm` library's built-in support for schema arguments with compatible models (like Claude 3.7 Sonnet).
- **Command Joining:** Currently deriving `kubectl_verb` and `kubectl_args` from the `commands: List[str]` in `handle_vibe_request`. This works for simple `get` args but might need refinement for commands requiring more complex argument handling (e.g., quoted strings, heredocs handled via YAML). This is acceptable technical debt for the MVP.

**Deferred Items / Technical Debt:**

- **Fallback Mechanism:** Did not implement fallback for models that don't support native schema prompting. Currently assumes the model works or fails during the `model_adapter.execute` call.
- **Complex Argument Handling:** As noted above, the derivation/joining of `commands` might be insufficient for all command types.

**Next Steps:**

- **Testing:**
  - Add comprehensive unit/integration tests for `vibectl/schema.py`.
  - **Refine/Expand tests for `handle_vibe_request`:** While edge cases were added/fixed, consider more scenarios for `COMMAND`, `ERROR`, `WAIT`, `FEEDBACK` action types. Ensure robust testing of argument handling.
  - **TODO:** Increase test coverage for `vibectl/command_handler.py` towards 100%.
  - **TODO:** Increase test coverage for `vibectl/memory.py` towards 100%.
- **Refinement:**
  - Test `get vibe` with more complex requests to ensure prompt instructions and `commands` list handling are robust.
  - Monitor LLM adherence to the schema and adjust prompts if needed.
- **Expansion:**
  - Apply the schema pattern to other command planning prompts (e.g., `PLAN_VIBE_PROMPT`, `PLAN_DESCRIBE_PROMPT`, etc.).
  - Re-evaluate and potentially refactor the `commands` list handling if needed for other command types.
- **Fallback Implementation (Post-MVP):** Design and implement the fallback mechanism for models lacking direct schema support.
