# Planned Changes for feature/streaming-llm-responses

**Completed:**
- Modify `LLMModelAdapter` in `vibectl/model_adapter.py` to support streaming responses.
  - Added `stream_execute` method.
  - Updated `LLMMetrics` capture for streaming and non-streaming paths (ongoing verification for token counts).
  - Handled `response.text()` and `response.json()` equivalents for streaming via `SyncLLMResponseAdapter` and `AsyncLLMResponseAdapter`.
- Update `handle_command_output` in `vibectl/command_handler.py` to consume streamed Vibe results.
  - Modified `_process_vibe_output` to handle streamed data.
  - Updated `ConsoleManager` with `start_live_vibe_panel`, `update_live_vibe_panel`, and `stop_live_vibe_panel` for live display in a panel.
  - Ensured final panel output correctly renders Rich markup.

**Next Steps / Outstanding Work:**

1.  **Stabilize Core Functionality:**
    *   Address outstanding linter errors in `vibectl/command_handler.py` (primarily async/await return type mismatches).
    *   Investigate and fix the ~90 existing test failures to ensure no regressions were introduced. This is critical before proceeding with new features.

2.  **Verify Streaming Across Commands:**
    *   Systematically test and verify that streaming output works correctly for all relevant `vibectl` commands (beyond just `vibectl get`).

3.  **Add Configuration for Streaming:**
    *   Implement a `show_streaming` configuration option (e.g., in `vibectl.config` and as a CLI flag).
    *   This option should allow users to suppress the intermediate streamed output, which is important for scripting or when piping output to files.
    *   Modify `_process_vibe_output` to respect this flag. If `show_streaming` is false but `show_vibe` is true, only the final panel should be displayed.

4.  **Enhance Test Coverage:**
    *   Add new tests specifically for the streaming functionality.
        *   Mock streaming responses effectively in these tests.
        *   Verify correct panel behavior (start, update, stop).
        *   Test the new `show_streaming` configuration.

5.  **Refactor and Cleanup (Ongoing):**
    *   Continue to refactor and clean up `model_adapter.py`, `command_handler.py`, and `console.py` as opportunities arise during the above tasks.
    *   Ensure token counting is consistently accurate across all models and response types (streaming/non-streaming).

6.  **Documentation:**
    *   Update `CHANGELOG.md` with all feature changes and significant fixes.
    *   Update `STRUCTURE.md` if any structural changes were made (e.g., new methods in `ConsoleManager` affecting how output is handled).

**Order of Attack for Outstanding Tasks:**
1. Fix Linter Errors (`command_handler.py` type hints).
2. Fix Existing Test Failures.
3. Verify Streaming on Other Commands.
4. Implement `show_streaming` Config.
5. Add New Tests for Streaming & Config.
6. Documentation (Changelog, Structure).
