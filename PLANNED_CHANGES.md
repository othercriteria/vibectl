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

### 5. TODOs / Follow-ups

- [ ] **Deprecate `get_adapter=` hook in `run_llm`**
  - Now that every call-site passes an explicit `Config` instance, the helper can
    look up its own adapter consistently.
  - Plan: introduce an internal cache in `llm_utils` for adapter instances per
    config and migrate callers, then remove the kwarg.
- [ ] **Decide on `execute_kwargs` future**
  - Currently used only for `response_model=`; still valuable as an escape hatch for
    low-frequency parameters (e.g., `temperature`, `max_tokens`).
  - Option A: keep as flexible `**kwargs` (status quo).  Option B: promote the few
    stable parameters (starting with `response_model`) to explicit keywords for
    stronger type safety, then lint for stray extras.
  - Evaluate once additional adapter options become necessary.
