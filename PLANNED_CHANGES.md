# Planned Changes - JSON Schema for LLM Command Generation

**Goal:** Improve reliability and structure of LLM responses for command planning by using JSON schemas.

**Status:** Core implementation complete. Integrated into most planning prompts (`create_planning_prompt`). Basic testing and fixes applied.

**Decisions & Compromises During Implementation:**

- **MVP First:** Focused implementation on `vibectl get vibe` initially, then expanded.
- **Happy Path Focus:** Primarily tested successful schema generation/parsing, with some error handling tests.
- **Schema Tooling:** Leveraged `llm` library's schema support.
- **Command Joining:** Derives `kubectl` arguments from `commands: List[str]`. Confirmed robust handling via `subprocess` list argument passing; no issues found.

**Outstanding Work / Next Steps:**

1.  **`PLAN_VIBE_PROMPT` Refactoring:**
    - Apply the schema pattern to the general `PLAN_VIBE_PROMPT` used by `vibectl vibe`.
2.  **Refine Argument Handling (If Needed):**
    - Re-evaluate the `commands` list joining based on testing with more complex command types.
4.  **Testing & Coverage:**
    - Add specific unit/integration tests for `vibectl/schema.py`.
    - Expand test coverage for `handle_vibe_request` (more scenarios for all `ActionType`s).
    - Increase test coverage towards 100% for `vibectl/memory.py`.
5.  **Robustness & Refinement:**
    - Test planning prompts with more complex/varied requests.
    - Monitor LLM schema adherence and adjust prompts if necessary.
