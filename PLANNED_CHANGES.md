# Robust Async-Testing Refactor

## Motivation
Spurious `RuntimeWarning: coroutine ... was never awaited` messages and flaky
`ServerConfig` autoreload tests stem from globally monkey-patching `asyncio`
primitives.  Instead of widening filter-warnings we will run the real event loop
and make our mocks play nicely with it.

## High-Level Tasks

1. **New shared async-test helpers**
   - `fast_sleep` fixture → replaces `asyncio.sleep` with an _awaitable_ noop
     implementation that never blocks longer than a single tick.
   - `background_tasks` fixture → list for tests to append any
     `asyncio.create_task(...)`; automatic cancellation/await in a session
     finaliser.

2. **Remove global `mock_asyncio_for_wait` patches**
   - Delete the duplicate fixtures from `tests/conftest.py` _and_
     `tests/subcommands/test_wait_cmd.py`.
   - Convert existing sync stubs to `AsyncMock` or lightweight async wrappers as
     needed.

3. **Refactor `tests/subcommands/test_wait_cmd.py`**
   - Stop patching `asyncio` directly.
   - Ensure every mocked helper is `AsyncMock` and awaited by production code.
   - Append any long-lived tasks to `background_tasks`.

4. **Stabilise `ServerConfig` autoreload tests**
   - Replace `time.sleep(...)` calls with `await asyncio.sleep(...)` inside
     `pytest.mark.asyncio` tests _or_ use `loop.run_in_executor` to wait on the
     `threading.Event`.
   - Increase poll interval to `0.05` but rely on deterministic async sleeps.

5. **Trim warning filters**
   - Remove broad filters from `pyproject.toml` and `tests/conftest.py` once the
     event-loop is clean.
   - Keep only project-specific suppressions (e.g. `DeprecationWarning` for
     third-party libs) if any remain.

6. **CI / Coverage**
   - Run full test suite with `pytest -n auto --no-cov` to validate the parallel
     path.
   - Verify warnings summary is empty; address any remaining noise explicitly.

## Non-Goals (for this PR)
- Changing production `vibectl` async behaviour.
- Improving coverage or performance beyond eliminating warnings/flakes.

## Acceptance Criteria
- `make test` passes under xdist without *any* `RuntimeWarning: ...was never
  awaited` messages.
- `tests/server/test_config_reload.py` passes deterministically (no sleeps or
  flakiness).
- No broad warning filters remain in repository configuration.

---

*(This plan will be executed in a new feature branch/worktree as per project
workflow.  Only the `scripts/run_parallel_tests.sh` zsh-compatibility change and
minor formatting in `docs/llm-proxy-server.md` are retained from the prior
exploration.)*
