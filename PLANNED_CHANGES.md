# Consistent Prompt-Injection Refactor – High-Level Plan

_Updated after completing core plumbing & test fixes (2025-06-20)._
This document tracks **only what still needs doing**. Finished items and low-level implementation notes have been archived in the PR description.

---

## Why we're doing this
1. Eliminate drift between different prompt builders.
2. Provide a single, explicit flow for `custom_instructions`, `memory`, and (new) `presentation_hints`.
3. Remove legacy helper `get_formatting_fragments` (✅ done) and eliminate ad-hoc context assembly.
4. Simplify execution code paths so future features plug in cleanly.

---

## Next actionable tasks

### 1. Prompt Builders (detailed checklist)

❗ **Goal**: every prompt builder—planning _and_ summary—uses `build_context_fragments` for context injection; no module composes fragments manually.

**Migration steps for each file**:
1. **Import**: add `from vibectl.prompts.context import build_context_fragments` (or rely on `shared.create_*` wrappers if already used).
2. **Planning functions** – usually fine; they already call `create_planning_prompt` which now injects hints; double-check any custom fragment assembly.
3. **Summary functions**:
   a. Replace manual memory/custom-instruction/timestamp blocks with:
   ```python
   system_fragments.extend(build_context_fragments(cfg, current_memory=current_memory))
   ```
   b. Remove direct calls to `fragment_current_time`, `fragment_memory_context`, etc.
4. **Presentation hints** – if the summary builder needs customised placement (e.g., logs vs events) accept the new `presentation_hints` param and inject accordingly; otherwise rely on default injection in `_vibe_summary_result`.
5. **Tests**:
   a. Update unit tests to call summary prompt with the 3-arg signature.
   b. Ensure formatting guidance and timestamps are present in summary prompts.

### 2. Summary Prompt API
- [x] **Removed the temporary compatibility scaffold in `_vibe_summary_result`** – all call-sites now supply the 3-arg signature.
- [ ] Update every *summary* prompt creator to accept `(config, current_memory, presentation_hints)` (most are done; audit remains).
- [ ] Add type annotations & docs for the 3-arg signature.

### 3. Execution Path DRY-up
- [ ] Extract `run_llm()` helper to remove duplicated adapter + metrics boilerplate (see Roadmap 4 in previous version).
- [ ] Wire existing execution modules through the helper.

### 4. Tests & Coverage
- [ ] Add integration test for planner → execution → summary round-trip including `presentation_hints` propagation.

### 5. Documentation
- [ ] Update `STRUCTURE.md` to reflect new helper locations & flow.
- [ ] Update `README` "Extending prompts" section (include `presentation_hints`).

### 6. Cleanup / Housekeeping
- [ ] Remove migration shim for legacy `custom_instructions` access.
- [ ] Delete any obsolete prompt-layout tests.
- [ ] Run Ruff / Mypy, fix warnings.

### 7. Follow-ups identified during typing pass

- [x] **live_display.py** – port-forward summary path refactored to pass through `presentation_hints` and delegate context injection entirely to prompt helpers.

---

## Key Technical Decisions (reference)

These choices guide the implementation; revisit only with strong justification.

• **Schema upgrade** – `LLMPlannerResponse` now includes `presentation_hints: str | None` and still uses `extra = "forbid"` for strictness.

• **Planner prompt templates** – Every `*_plan_prompt` must list the optional `presentation_hints` field in its schema/example block so the language-model knows it can emit it.

• **Context assembly** – `build_context_fragments(cfg, current_memory=?, presentation_hints=?)` is the _single_ source of truth for memory, custom instructions, presentation hints, and timestamp.

• **Summary prompt API** – Final signature is
```python
def summary_prompt(config: Config | None, current_memory: str | None, presentation_hints: str | None = None) -> PromptFragments
```
  – The temporary introspection scaffold in `_vibe_summary_result` will be deleted once all implementations adopt this.

• **Execution pipeline** – `presentation_hints` is captured from the planner and threaded through `_confirm_and_execute_plan → handle_command_output → _vibe_summary_result → summary_prompt`.  Live display helpers are a special case and need refactor (see TODO 7).

• **Custom-instruction migration** – Legacy flat `custom_instructions` key is now `system.custom_instructions`; a shim in `Config.get()` warns and forwards.  The shim will be removed in Cleanup.

• **Tests** – Integration tests must verify round-trip of `presentation_hints`; schema tests must allow (but not require) the new field until prompts are updated.

---

## Done (recent)
- Central `build_context_fragments` helper implemented & unit-tested.
- Planner schema updated with optional `presentation_hints` + schema regeneration.
- Execution pipeline now threads `presentation_hints` through to summary helpers.
- Temporary compatibility scaffold **deleted**; all code now on final API.
- Updated `vibe_autonomous_prompt` to use `build_context_fragments` with `presentation_hints`.
- All summary-prompt test helpers updated; unit tests & `make typecheck` now clean.
- Fixed failing unit tests caused by the scaffold and typing mismatch.
- Migrated majority of *summary* prompt creators to the new three-argument signature and unified context injection via `build_context_fragments`.
- live_display.py updated to propagate `presentation_hints` and rely exclusively on prompt helpers for context injection.
- Updated `tests/subcommands/test_logs_cmd.py` and `tests/test_cli_global_flag_transduction.py` to reflect the
  new `allowed_exit_codes=(0,)` keyword-argument passed to `run_kubectl` by `command_handler`.
- Corrected patch targets in the same tests so they patch `vibectl.command_handler` (or
  `vibectl.subcommands.logs_cmd`) rather than stale module paths.
- Fixed expectations around the empty-output path: `handle_command_output` is now invoked even
  when kubectl returns no data, and tests have been updated accordingly.
- All unit tests now pass cleanly (`pytest -n auto` → 2158 ✓, 0 ✗).

---

## Release strategy
We'll land the remaining work in **small, reviewable PRs** with green CI.
Once Tasks 1 & 2 are complete the branch can merge; follow-up tasks can happen on `main`.
