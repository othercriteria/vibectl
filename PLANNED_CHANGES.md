# Consistent Prompt-Injection Refactor – High-Level Plan

_Updated after memory adapter & test harness cleanup (2025-06-21)._
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

**Migration status** — ✅ **Complete**

All former `execute_and_log_metrics` call-sites now route through `run_llm` and
CI is green. The helper's `get_adapter=` escape-hatch has been excised from its
signature, so callers can no longer pass it explicitly.  Tests continue to
monkey-patch `vibectl.model_adapter.get_model_adapter`, which `run_llm` now
imports lazily, preserving full mockability.

Remaining niceties (resolved):

* **Document the preferred `run_llm` call pattern in STRUCTURE.md** — ✅ **Done**
  *The docstring in `vibectl.llm_utils.run_llm` now contains a canonical usage
  snippet, and we consider that sufficient for now. A dedicated STRUCTURE.md
  excerpt can be added later if the pattern evolves.*

* **Re-evaluate the `execute_kwargs` escape-hatch** — ⏸️ **Deferred**
  *Current consensus: leave the passthrough in place until new adapter options
  emerge. We'll revisit when concrete requirements appear.*

### 4. Tests & Coverage (Deferred)
🔜 *Integration test for planner → execution → summary round-trip including
  `run_llm` path.*  We'll implement this once our test harness supports
  deterministic LLM stubbing or a suitable mocking framework is ready.

### 5. TODOs / Follow-ups

* **Deprecate `get_adapter=` hook in `run_llm`** — ✅ **Done** (2025-06-21)
  * Parameter removed; helper now always resolves the adapter internally.
  * Tests rely solely on patching `vibectl.model_adapter.get_model_adapter`.

---

## ✅ Plan completion status

All critical tasks for the **Consistent Prompt-Injection Refactor** have been
completed. Deferred items are documented above and will be tackled in future
iterations.
