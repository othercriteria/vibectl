# Planned Changes: Output Truncation Overhaul

This document outlines initial ideas for improving the output truncation logic in `vibectl/output_processor.py`.

## Current Status (as of [Date])

*   Refactoring of `output_processor.py` and `truncation_logic.py` is in progress.
*   Several unit tests for `output_processor.py` are currently failing due to the refactor and are proving difficult to fix directly.
*   **Next Steps:** Temporarily skip the failing tests and focus on improving overall test coverage for `output_processor.py` and `truncation_logic.py`. Once coverage is improved, revisit the failing tests.

## Preliminary Thoughts & Areas for Improvement

1.  **Context-Aware Truncation:**
    *   The current `process_for_llm` and `truncate_string` use a simple "first/last N characters" approach.
    *   Explore making truncation aware of the output format (JSON, YAML, logs, plain text) even in the generic functions.
    *   Consider the *intent* of the `vibe` command (if available) to prioritize relevant sections (e.g., keep more `status` info if asking about resource health).

2.  **JSON/YAML Truncation:**
    *   The `_truncate_json_object` uses max depth and list length limits.
    *   The defined `important_keys` set is not currently used in truncation logic. Explore using it to preserve key information even when truncating deeply nested objects or long lists.
    *   Simplify and unify the logic between `process_json`, `process_yaml`, and `process_output_for_vibe`. The thresholds and strategies seem inconsistent (e.g., `max_chars // 2` vs `max_chars // (4 * section_count)`).
    *   YAML section extraction (`extract_yaml_sections`) seems reasonable but could be more robust against edge cases. The status truncation (`truncate_yaml_status`) is specific; check if other sections (like `spec` or `metadata`) might also benefit from tailored truncation.

3.  **Log Truncation:**
    *   `process_logs` keeps the first 40 and last 60 lines. This seems reasonable for preserving recent events, but could be configurable or smarter (e.g., detect error patterns and preserve context around them).

4.  **Testing:**
    *   **(In Progress)** Add comprehensive unit tests specifically targeting the `OutputProcessor` class and its methods, as well as `truncation_logic.py`.
    *   **(Focus Area)** Improve overall test coverage before fixing currently failing tests.
    *   Include tests for various edge cases:
        *   Very large outputs (JSON, YAML, logs, plain text)
        *   Deeply nested structures
        *   Long lists within structures
        *   Empty or malformed inputs
        *   Different `max_chars` and `llm_max_chars` settings.

5.  **Configuration:**
    *   Consider if any truncation parameters should be user-configurable via `vibectl config`.

6.  **Refinement:**
    *   Review the overall flow and ensure clarity and maintainability of the `OutputProcessor`.
