# Planned Changes for vibectl LLM Metrics Improvements

## Overview
Improve LLM metrics handling and configurability by separating individual metrics reporting from rolled-up/total metrics reporting.

## Progress Status

### ✅ Completed
1. **New MetricsDisplayMode enum** - Added to `vibectl/types.py`
   - `NONE`: Show no metrics
   - `TOTAL`: Show only total/accumulated metrics
   - `SUB`: Show only individual sub-metrics
   - `ALL`: Show both sub-metrics and totals

2. **Updated OutputFlags** - Now uses `MetricsDisplayMode` instead of boolean
   - Updated all field references (`show_raw` → `show_raw_output`)
   - **Complete refactor of OutputFlags with new `from_args()` class method**
   - **All references throughout codebase updated to use new field names**

3. **Configuration system updates**
   - Updated schema to accept `str` for `show_metrics`
   - Updated validation logic to handle enum conversion

4. **Console utility functions** - Added to `vibectl/console.py`
   - `should_show_sub_metrics()`: Check if individual metrics should be shown
   - `should_show_total_metrics()`: Check if total metrics should be shown
   - `print_sub_metrics_if_enabled()`: Print individual LLM call metrics if enabled
   - `print_total_metrics_if_enabled()`: Print accumulated metrics if enabled

5. **LLMMetricsAccumulator class** - Added to `vibectl/types.py`
   - Reduces boilerplate for accumulating metrics across multiple LLM calls
   - Provides `print_total_if_enabled()` convenience method

6. **Updated check command** - `vibectl/execution/check.py`
   - Now uses new utility functions for metrics display
   - Shows individual LLM call metrics when enabled
   - Shows total metrics on completion
   - Fixed all `show_raw` → `show_raw_output` references
   - **Captures and displays memory update LLM metrics** - Now accumulates metrics from `update_memory()` calls

7. **Updated all subcommands** - **COMPLETED**
   - **All subcommand functions now accept `MetricsDisplayMode` instead of `bool` for `show_metrics`**
   - **Type signatures updated across all command modules**
   - **Backward compatibility maintained through configuration layer**

8. **Updated vibe execution** - **COMPLETED**
   - **Memory update metrics in vibe.py now use new display utilities**
   - **Individual memory update calls show sub-metrics when enabled**

9. **Comprehensive test updates** - **COMPLETED**
    - **All test files updated to use new `MetricsDisplayMode` types**
    - **Test fixtures and mocks updated for new type signatures**
    - **Backward compatibility tests maintained**

10. **CLI integration** - **COMPLETED**
    - **Main CLI updated to handle new types properly**
    - **Command handler updated to use new `OutputFlags.from_args()` method**

11. **Async streaming metrics infrastructure** - **COMPLETED**
    - **Added `stream_execute_and_log_metrics()` abstract method to ModelAdapter**
    - **Implemented `StreamingMetricsCollector` class for async metrics collection**
    - **Full implementation in Claude model adapter with proper metrics tracking**
    - **Updated command_handler.py to accept and use LLMMetricsAccumulator parameters**
    - **Enhanced memory update operations to pass through metrics accumulators**
    - **Updated all test mocks to include streaming metrics methods**
    - **Added comprehensive test coverage for streaming metrics functionality**

12. **Apply command integration** - **COMPLETED**
    - **Full integration of LLMMetricsAccumulator in vibectl/execution/apply.py**
    - **All LLM operations now properly accumulate metrics (file scoping, summarization, correction, final planning)**
    - **Memory update operations include metrics in accumulator**
    - **Command execution output processing includes metrics accumulation**
    - **Total metrics displayed at end of apply workflow**
    - **Comprehensive test updates for apply functionality with new metrics types**
    - **All 976 tests passing with new infrastructure**

### 🔄 In Progress / Next Steps

**NONE** - All planned work has been completed.

### 🎯 Success Criteria

- [x] `show_metrics: "none"` → No metrics displayed
- [x] `show_metrics: "sub"` → Only individual LLM call metrics displayed
- [x] `show_metrics: "total"` → Only accumulated/total metrics displayed
- [x] `show_metrics: "all"` → Both individual and total metrics displayed
- [x] **Memory update LLM calls now included in metrics** - Previously missing memory update metrics are now captured and displayed
- [x] **All type signatures updated to use MetricsDisplayMode**
- [x] **All tests updated and passing (976/976)**
- [x] **Async streaming metrics properly integrated throughout codebase**
- [x] **Apply command fully integrated with new metrics infrastructure**

## Implementation Notes

- The `MetricsDisplayMode` enum uses string values to make it easily serializable in config files
- Utility functions are placed in `console.py` rather than a separate module to keep related functionality together
- `LLMMetricsAccumulator` is in `types.py` alongside the `LLMMetrics` class for logical grouping
- All changes maintain backward compatibility with existing boolean-based configurations
- **The core infrastructure is now complete including async streaming support**
- **Type system is fully migrated to use MetricsDisplayMode throughout the codebase**
- **StreamingMetricsCollector provides a clean async interface for metrics collection**
- **All command handlers now support accumulating metrics across multiple LLM operations**
- **Apply command serves as a comprehensive example of the new metrics infrastructure in action**

## Implementation Complete

This feature is now **FULLY IMPLEMENTED**. The LLM metrics improvements provide:

1. **Flexible display modes** - Users can choose which metrics to see
2. **Comprehensive coverage** - All LLM operations are properly tracked
3. **Accumulated metrics** - Total metrics across multiple LLM calls in complex workflows
4. **Memory inclusion** - Memory update operations are included in metrics
5. **Async streaming support** - Proper metrics collection for streaming LLM operations
6. **Test coverage** - 100% test coverage maintained with 976/976 tests passing

The vibectl apply command demonstrates the full power of the new infrastructure, accumulating metrics across file scoping, manifest summarization, error correction, final planning, and memory updates, then displaying totals at the end of the workflow.
