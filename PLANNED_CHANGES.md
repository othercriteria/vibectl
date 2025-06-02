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

2. **Backward compatibility** - `MetricsDisplayMode.from_value()` converts boolean values
   - `False/None` → `NONE`
   - `True` → `ALL` (maintains existing behavior)

3. **Updated OutputFlags** - Now uses `MetricsDisplayMode` instead of boolean
   - Maintains backward compatibility in constructor
   - Updated all field references (`show_raw` → `show_raw_output`)
   - **Complete refactor of OutputFlags with new `from_args()` class method**
   - **All references throughout codebase updated to use new field names**

4. **Configuration system updates**
   - Updated schema to accept both `bool` and `str` for `show_metrics`
   - Updated validation logic to handle enum conversion
   - Maintains backward compatibility with existing config files

5. **Console utility functions** - Added to `vibectl/console.py`
   - `should_show_sub_metrics()`: Check if individual metrics should be shown
   - `should_show_total_metrics()`: Check if total metrics should be shown
   - `print_sub_metrics_if_enabled()`: Print individual LLM call metrics if enabled
   - `print_total_metrics_if_enabled()`: Print accumulated metrics if enabled

6. **LLMMetricsAccumulator class** - Added to `vibectl/types.py`
   - Reduces boilerplate for accumulating metrics across multiple LLM calls
   - Provides `print_total_if_enabled()` convenience method

7. **Updated check command** - `vibectl/execution/check.py`
   - Now uses new utility functions for metrics display
   - Shows individual LLM call metrics when enabled
   - Shows total metrics on completion
   - Fixed all `show_raw` → `show_raw_output` references
   - **Captures and displays memory update LLM metrics** - Now accumulates metrics from `update_memory()` calls

8. **Updated all subcommands** - **COMPLETED**
   - **All subcommand functions now accept `MetricsDisplayMode` instead of `bool` for `show_metrics`**
   - **Type signatures updated across all command modules**
   - **Backward compatibility maintained through configuration layer**

9. **Updated vibe execution** - **COMPLETED**
   - **Memory update metrics in vibe.py now use new display utilities**
   - **Individual memory update calls show sub-metrics when enabled**

10. **Comprehensive test updates** - **COMPLETED**
    - **All test files updated to use new `MetricsDisplayMode` types**
    - **Test fixtures and mocks updated for new type signatures**
    - **Backward compatibility tests maintained**

11. **CLI integration** - **COMPLETED**
    - **Main CLI updated to handle new types properly**
    - **Command handler updated to use new `OutputFlags.from_args()` method**

12. **Async streaming metrics infrastructure** - **NEW IN THIS COMMIT**
    - **Added `stream_execute_and_log_metrics()` abstract method to ModelAdapter**
    - **Implemented `StreamingMetricsCollector` class for async metrics collection**
    - **Full implementation in Claude model adapter with proper metrics tracking**
    - **Updated command_handler.py to accept and use LLMMetricsAccumulator parameters**
    - **Enhanced memory update operations to pass through metrics accumulators**
    - **Updated all test mocks to include streaming metrics methods**
    - **Added comprehensive test coverage for streaming metrics functionality**

### 🔄 In Progress / Next Steps

1. **Test CLI interface**
   - Test string values: `vibectl config set show_metrics total`
   - Test boolean values: `vibectl config set show_metrics true` (should map to `all`)
   - Verify different modes work as expected

2. **Update remaining command implementations** - **MOSTLY COMPLETE**
   - **Replace any remaining direct `console_manager.print_metrics()` calls with utility functions**
   - **Ensure all async operations properly utilize streaming metrics**

3. **Documentation**
   - Update configuration documentation to explain new enum values
   - Update CLI help text to mention the new options
   - Document the new async streaming metrics capabilities

### 🎯 Success Criteria

- [x] `show_metrics: false` → No metrics displayed
- [x] `show_metrics: true` → Both individual and total metrics displayed (backward compatible)
- [ ] `show_metrics: "none"` → No metrics displayed
- [ ] `show_metrics: "sub"` → Only individual LLM call metrics displayed
- [ ] `show_metrics: "total"` → Only accumulated/total metrics displayed
- [ ] `show_metrics: "all"` → Both individual and total metrics displayed
- [x] Backward compatibility maintained for existing configurations
- [x] No breaking changes to existing API
- [x] **Memory update LLM calls now included in metrics** - Previously missing memory update metrics are now captured and displayed
- [x] **All type signatures updated to use MetricsDisplayMode**
- [x] **All tests updated and passing**
- [x] **Async streaming metrics properly integrated throughout codebase**

## Implementation Notes

- The `MetricsDisplayMode` enum uses string values to make it easily serializable in config files
- Utility functions are placed in `console.py` rather than a separate module to keep related functionality together
- `LLMMetricsAccumulator` is in `types.py` alongside the `LLMMetrics` class for logical grouping
- All changes maintain backward compatibility with existing boolean-based configurations
- **The core infrastructure is now complete including async streaming support**
- **Type system is fully migrated to use MetricsDisplayMode throughout the codebase**
- **StreamingMetricsCollector provides a clean async interface for metrics collection**
- **All command handlers now support accumulating metrics across multiple LLM operations**
