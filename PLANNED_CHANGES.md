# Planned Changes for feature/consistent-prompt-injection

## Goal
Improve consistency in how custom instructions and memory are injected into planning, summary, and other prompts.

## Planned Tasks (remaining)
The baseline config-naming work and the planner-schema update are ✅ **complete**.

### Completed
• Central `build_context_fragments` helper implemented and core unit-tested.
• Summary-prompt migration started: `create_summary_prompt` and `vibe_autonomous_prompt` now consume the helper; legacy `get_formatting_fragments` no longer required there.
• Test suite updated – removed obsolete "rich.Console() markup" expectations; all tests green again.
• Optional `presentation_hints` field added to `LLMPlannerResponse` (+ round-trip schema tests).
• `create_planning_prompt` docs updated to reference `presentation_hints`.
• **Execution pipeline wired** – `presentation_hints` now flows from planner → execution → summary helpers. Refactored `handle_command_output` with guard-clauses and helper functions (`_vibe_recovery_result`, `_vibe_summary_result`, etc.) to cut nesting and E501 violations; all unit-tests updated and pass.

### Remaining (high-level)
1. **Prompt Modules** – Continue migrating remaining prompt builders (`get`, `describe`, `logs`, `events`, `scale`, `wait`, rollout helpers, etc.) to `build_context_fragments`, then delete `get_formatting_fragments`.
2. **Prompt Template Updates** – Ensure every *_plan_prompt includes the new `presentation_hints` field in its schema/example block.
3. **Exotic Workflows** – Migrate `check`, `edit`, `auto`, `audit`, etc. to the new pattern.
4. **Refactor Runtime Path (remaining)** – Extract `run_llm()` helper to remove remaining duplication across execution modules.
5. **Test & Docs Sweep** – Remove obsolete tests, add integration tests for planner→summary round-trip, update docs (`STRUCTURE.md`, README).

## Implementation Roadmap (high-level)

1. Baseline cleanup ✅  *(complete)*
   • Replaced all uses of the legacy `custom_instructions` key with the namespaced `system.custom_instructions`.
   • Introduced a migration shim in `Config.get()` that warns on legacy access and forwards reads — **remove this shim in Phase 5 once the branch is merged and user configs are upgraded.**

   Remaining trace work ➜ During Step 2 we'll delete the now-redundant ad-hoc lookup in `prompts/edit.py` when the new helper lands.

2. Central PromptContext helper *(in progress)*
   2.1  **✅ Implement helper** – `vibectl/prompts/context.py` now provides `build_context_fragments()`.
   2.2  **✅ Unit tests** – Core permutations covered (edge-case tests still TODO).
   2.3  **↪ Ongoing migration** – First two call-sites switched (`create_summary_prompt`, `vibe_autonomous_prompt`). Remaining modules listed in Remaining #1.
   2.4  Delete the special-case code path in `prompts/edit.py` once its migration is done.
   2.5  Remove `get_formatting_fragments` after final migration; update docs (`STRUCTURE.md`, design docs).
   2.6  Ensure tests referencing old formatting text are removed or updated (done for current suite).

3. Planner changes *(partially complete)*
   • Extend `LLMPlannerResponse` schema with optional `presentation_hints: str | None` to carry UI/formatting guidance. (Decided to keep it a **plain string** for MVP; structure can evolve later.)
   • Update every planning prompt creator to include a *placeholder* for the hints in its schema description so the LLM knows it can emit them.
   • Update tests and execution code that parse planner results (e.g. `vibectl/execution/*`) to extract `presentation_hints` into a variable, store it alongside the Action.

4. Summary/execution prompt pipeline
   • Every execution module (apply, get, log, etc.) currently calls
      ```python
      summary_system, summary_user = X_summary_prompt(current_memory=mem)
      ```
      Replace with
      ```python
      summary_system, summary_user = X_summary_prompt(
          current_memory=mem,
          presentation_hints=presentation_hints,
      )
      ```
      (The prompt helper will attach a fragment using those hints.)
   • Add fallback so that if no hints are available the previous behavior is kept (prevents unrelated tests/users from breaking mid-migration).

5. Exotic workflows alignment
   • `vibectl/execution/check.py` – adopt same planner/summary flow.
   • `edit` intelligent workflow – planner already exists (plan_edit_scope); add `presentation_hints` output and wire through subsequent summarization prompts.
   • `auto` / `audit` – evaluate if they need hint propagation; apply same pattern if yes.

6. Remove duplication / DRY runtime path
   • Many execution modules duplicate code to pass memory & config into prompt helpers and LLM execution. Extract into
     `vibectl.execution.common.run_llm(model_adapter, prompt_func, ...)` helper that:
     – handles context building,
     – runs the adapter,
     – parses JSON when required,
     – logs metrics.
     Execution modules become thin orchestration wrappers.

7. Test & doc sweep
   • Delete failing prompt-layout unit tests.
   • Add *integration-ish* tests that run planner→summary round-trip using a stubbed ModelAdapter returning canned responses (no real LLM calls).
   • Update `STRUCTURE.md` to document new helper locations.
   • Update `README.md` "Extending prompts" section with presentation-hint guidance.

## Phase Ordering & CI Strategy

We will land the refactor in a series of PRs behind the feature branch:

1️⃣ Baseline cleanup + helper introduction (tests continue to fail for planners)
2️⃣ Planner schema + prompt updates (planners now pass tests, summaries still red)
3️⃣ Summary helpers & execution wiring (tests green again)
4️⃣ Exotic workflow migration
5️⃣ Remove shims / delete legacy keys
6️⃣ Documentation polish & final test hardening

Throughout this sequence **CI failures due to obsolete prompt expectations are tolerated** until the corresponding phase is complete. Only at the end of the phase do we restore green.

## Notes
This feature focuses on improving the internal consistency of prompt generation rather than adding new functionality.

**Fearless breaking-changes policy:** We will prioritise a clean, maintainable design over short-term test stability. It is acceptable—and expected—for existing prompt-focused tests to fail during this refactor. Treat red CI as a signal of unfinished migration work, not as a blocker. Rewrite or remove outdated tests once the new standard is implemented.

### Schema & Prompt Updates for `presentation_hints`

*Schema changes*
1.  `vibectl/schema.py`
    • Add optional field `presentation_hints: str | None = Field(None, description="Formatting / style hints for downstream prompts.")` to `LLMPlannerResponse`.
    • Keep `extra = "forbid"` so unknown keys are still rejected; field is part of the model so parse succeeds when provided.
2.  `vibectl/prompts/schemas.py`
    • Regenerate `_SCHEMA_DEFINITION_JSON` after the model change (`LLMPlannerResponse.model_json_schema()`).
3.  Update helper `create_planning_prompt` (and any hard-coded schema fragments) so that the explanatory block lists this new key and what it means.

*Planning prompt templates*
4.  Each `*_plan_prompt` in `vibectl/prompts/*` must mention the optional `presentation_hints` field in the JSON example & description so the LLM knows it can populate it.
    – easiest: factor a `fragment_presentation_hints_doc(schema_json)` helper used by create_planning_prompt.

*Execution logic*
5.  Parsing: No change required—`LLMPlannerResponse.model_validate_json()` will now yield `.presentation_hints` when present.
6.  Propagation path:
    • `vibectl/execution/vibe._get_llm_plan` → on Success return, capture `response.presentation_hints` alongside `response.action`.
    • Thread a new variable `presentation_hints` through `_confirm_and_execute_plan`, `handle_command_output`, `_process_vibe_output`, etc.
    • Signature changes:
      ```python
      `SummaryPromptFragmentFunc = Callable[[Config | None, str | None, str | None], PromptFragments]` (third arg is `presentation_hints`).
      ```
      where the 3rd param is `presentation_hints` (may be None).
    • Update each summary prompt helper to accept `presentation_hints` and, if present, append a `Fragment(f"Presentation hints: {presentation_hints}")` to its *system* fragment list (or user, TBD).

*Backward compatibility*
7.  Until all callers supply the third arg, summary helpers should default it to `None` so existing code keeps working during phased rollout.

*Tests*
8.  Adjust schema-based tests to account for the new field (allow it, but not required).
9.  Add tests that verify a planner response containing `presentation_hints` round-trips through `model_validate_json` and that summary prompt builder incorporates it.

This chunk fits into Phase 2 (planner schema) & Phase 3 (summary update) in the roadmap above.
