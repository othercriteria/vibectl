# Consistent Prompt-Injection Refactor – High-Level Plan

_Updated after prompt-builder context refactor pass (2025-06-21)._
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

**Recent progress (2025-06-21)**

- ✅ `vibectl/prompts/memory.py` (both `memory_update_prompt` and `memory_fuzzy_update_prompt`) now rely on `build_context_fragments` and have removed manual `fragment_current_time` / `fragment_memory_context` logic.
- ✅ `vibectl/prompts/recovery.py` migrated to use `build_context_fragments` for timestamp and future context injection.

Remaining summary/other prompt modules still need auditing as per steps below.

### ✅ 1.a Memory Update Side-Effect Policy (2025-06-21)

Generic errors during *handle_command_output* now trigger an additional memory update (post-execution error record).  Tests have been updated to assert **two** `update_memory` calls: one for the successful execution record, one for the formatting error.  This ensures future prompts have full context.

No further action needed.

### 2. Summary Prompt API
- [x] **Removed the temporary compatibility scaffold in `_vibe_summary_result`** – all call-sites now supply the 3-arg signature.
- [ ] Update every *summary* prompt creator to accept `(config, current_memory, presentation_hints)` (most are done; audit remains).
- [ ] Add type annotations & docs for the 3-arg signature.

### 3. Execution Path DRY-up – *run_llm helper*

❗ **Goal**: every non-streaming LLM invocation should route through the shared
`vibectl.llm_utils.run_llm()` coroutine so that adapter look-up, metric
aggregation and unit-test monkey-patching are handled uniformly.

**Status**

*Introduced in PR #?? (2025-06-21).*  Core wiring completed:

| Module | Calls replaced |
| ------- | -------------- |
| `command_handler.py` | Recovery suggestions & non-stream summaries |
| `memory.py` | `update_memory` |
| `execution/vibe.py` | `_handle_fuzzy_memory_update` |

**Remaining migration checklist**:

All direct `execute_and_log_metrics` call-sites have been migrated to use
`run_llm`.

Next cleanup tasks:
-1. `execution/vibe.py`
   - ✅ Replaced internal planning call with `run_llm` (response_model forwarded).
   - ✅ Audited helpers (`_handle_fuzzy_memory_update`, confirmation logic) – they already use `run_llm`.
-2. `execution/apply.py`
   - ✅ Migrated 5 direct `execute_and_log_metrics` invocations (replaced with `run_llm`).
-3. `execution/edit.py`
   - ✅ Migrated 3 direct calls (lines ~250, 340, 510).
-4. `execution/check.py`
   - ✅ Single call migrated (replaced with `run_llm`; lines ~75–140).
-5. `subcommands/memory_update_cmd.py`
   - ✅ Migrated single call around line 50.

After each batch:

```bash
pytest -q tests/path_of_interest  # ensure mocks still hook get_model_adapter
ruff check . && mypy .            # keep linters happy
```

Once all call-sites are migrated:

Cleanup tasks remaining:

* Remove redundant `get_model_adapter` imports where no longer required (after test fixtures are updated).
* Deprecate or consolidate any helper wrappers that duplicate `run_llm` functionality.
* Document the preferred `run_llm` call-site convention (always pass `config` & use keyword args), then update code & STRUCTURE.md accordingly.

### 4. Tests & Coverage
- [ ] Add integration test for planner → execution → summary round-trip including
      `run_llm` path.
