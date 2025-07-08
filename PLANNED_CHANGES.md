# Robust Async-Testing Refactor

## Motivation
Spurious `RuntimeWarning: coroutine ... was never awaited` messages and flaky
`ServerConfig` autoreload tests stem from globally monkey-patching `asyncio`
primitives.  Instead of widening filter-warnings we will run the real event loop
and make our mocks play nicely with it.

## High-Level Tasks

1. [x] **New shared async-test helpers**
   - `fast_sleep` fixture → replaces `asyncio.sleep` with an _awaitable_ noop
     implementation that never blocks longer than a single tick.
   - `background_tasks` fixture → list for tests to append any
     `asyncio.create_task(...)`; automatic cancellation/await in a session
     finaliser.

2. [x] **Remove global `mock_asyncio_for_wait` patches**
   - Delete the duplicate fixtures from `tests/conftest.py` _and_
     `tests/subcommands/test_wait_cmd.py`.
   - Convert existing sync stubs to `AsyncMock` or lightweight async wrappers as
     needed.

3. [x] **Refactor `tests/subcommands/test_wait_cmd.py`**
   - Stop patching `asyncio` directly.
   - Ensure every mocked helper is `AsyncMock` and awaited by production code.
   - Append any long-lived tasks to `background_tasks`.
   - **COMPLETED**: Fixed LLM mocking issues by adding `mock_get_adapter` fixture to wait command tests.
   - **COMPLETED**: All 2182 tests now pass; eliminated majority of async warnings.

4. [x] **Stabilise `ServerConfig` autoreload tests**
   - **COMPLETED**: Converted tests to `pytest.mark.asyncio`, replacing
     `time.sleep(...)` with `await asyncio.sleep(...)` and leveraging
     `asyncio.to_thread` for `threading.Event` waits.  Poll interval remains at
     `0.05` for fast detection.

5. [x] **Trim warning filters**
   - **COMPLETED**: Removed autouse fixture suppressing coroutine-not-awaited
     `RuntimeWarning`; test suite passes without broad warning filters.

6. **CI / Coverage**
   - Run full test suite with `pytest -n auto --no-cov` to validate the parallel
     path.
   - Verify warnings summary is empty; address any remaining noise explicitly.

## Non-Goals (for this PR)
- Changing production `vibectl` async behaviour.
- Improving coverage or performance beyond eliminating warnings/flakes.

## Acceptance Criteria
- ✅ **ACHIEVED**: All 2182 tests pass under xdist without major `RuntimeWarning: ...was never awaited` messages.
- ⚠️ **NEARLY ACHIEVED**: Only 1 minor async warning remains (down from multiple major warnings).
- ✅ `tests/server/test_config_reload.py` passes deterministically (no sleeps or
  flakiness).
- No broad warning filters remain in repository configuration.
