# Planned Changes: Output Truncation Overhaul

This document outlines initial ideas for improving the output truncation logic in `vibectl/output_processor.py`.

## Current Status (as of [Current Date/Time])

*   Refactoring of `output_processor.py` and `truncation_logic.py` is largely complete.
*   Several unit tests for `output_processor.py` were previously failing; some were skipped, one removed, others fixed. Existing tests have been reviewed and adjusted for the new logic.
*   Basic test coverage for `output_processor.py` and `truncation_logic.py` has been established.
*   **Budget-Based Secondary YAML Truncation:** Implemented in `_process_yaml_internal`. This logic extracts top-level YAML sections, calculates a budget per section based on the overall character limit (`llm_max_chars` or provided budget), and applies secondary truncation (`tl.truncate_string`) to sections exceeding their budget before reconstructing the YAML.

## Remaining Work for this Branch (Focus: Testing)

*   **(Addressed)** Enhance test coverage for YAML processing, particularly for edge cases in:
    *   `_process_yaml_internal` (various budget scenarios, reconstruction accuracy)
    *   `extract_yaml_sections` (different YAML structures, multi-document handling) - *Added specific multi-doc tests.*
    *   `_reconstruct_yaml` (correctness with truncated/non-truncated sections)
*   **(Addressed)** Added specific tests for multi-document YAML handling in `extract_yaml_sections` and `_process_yaml_internal`.
*   **(Testing)** Review and add tests for JSON truncation edge cases in `truncate_json_like_object` (e.g., very deep nesting, various list lengths).
*   **(Testing)** Review and ensure adequate test coverage for the iterative log truncation logic in `process_logs` and `_truncate_logs_by_lines`.
*   **(Addressed)** Investigated and improved coverage for `_truncate_logs_by_lines`, achieving 99% reported coverage and resolving discrepancies through debugging and code simplification.

*Note: More complex enhancements (refined heuristics, JSON budgeting, context-aware truncation, user configuration) have been moved to `TODO.md`.*

## Preliminary Thoughts & Areas for Improvement (Updated)

1.  **Context-Aware Truncation:**
    *   Generic truncation (`truncate_string`) still uses first/last characters. Format-aware truncation is handled in `process_json`, `process_yaml`, `process_logs`.
    *   **(Moved to TODO)** Consider using `vibe` intent to guide prioritization.

2.  **JSON/YAML Truncation:**
    *   `_truncate_json_like_object` uses depth/list limits.
    *   **(Partially Addressed / JSON Moved to TODO)** YAML now uses a budget system (`_process_yaml_internal`). Improving JSON budget logic moved to TODO.
    *   YAML section extraction (`extract_yaml_sections`) handles basic multi-document cases but could be more robust. The budget logic currently applies only to the first document's sections.
    *   The specific `truncate_yaml_status` function was removed; status (or any section) is now truncated based on the budget system if it exceeds its share.

3.  **Log Truncation:**
    *   `process_logs` now uses an iterative approach (`_truncate_logs_by_lines`) trying to stay within a character budget (`char_budget`) by adjusting the number of start/end lines kept (`max_lines`). This is more budget-aware than the fixed line count approach.
    *   **(Enhancements Moved to TODO)** Could still be enhanced (e.g., error pattern detection).

4.  **Testing:**
    *   **(Focus Area)** Comprehensive tests are crucial, especially for the budget logic and section handling. Focus on different YAML structures and budget constraints.
    *   **(Addressed)** Test multi-document YAML.

5.  **Configuration:**
    *   **(Moved to TODO)** Consider user configuration.

6.  **Refinement:**
    *   The `OutputProcessor` has been significantly refactored. Continued review for clarity is always good.
