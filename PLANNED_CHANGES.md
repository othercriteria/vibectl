# Planned Changes for feature/improve-llm-metrics

## Overview
Improve LLM metrics recording and reporting for better consistency, completeness, and configurability.

## Goals
- Adjust `show_metrics` configuration to separately control:
  - Sub-metrics: Individual LLM call metrics
  - Total metrics: Final command completion metrics (successful or failed)
- Ensure every LLM call is correctly and consistently instrumented
- DRY up boilerplate around LLM calls
- Fix any obvious bugs around LLM calls discovered during this work

## Configuration Options Under Consideration
- Extend `show_metrics` to accept enumerated values instead of just boolean
- Create new separate configuration options for sub-metrics vs total metrics
- Maintain backward compatibility with existing boolean `show_metrics` behavior

## Areas to Investigate
1. Current LLM call patterns and instrumentation
2. Existing metrics collection and reporting mechanisms
3. Configuration system for metrics display
4. Boilerplate code that can be consolidated
5. Edge cases and error conditions in LLM metrics

## Implementation Tasks
- [ ] Audit current LLM call sites for consistent instrumentation
- [ ] Design improved configuration schema for metrics display
- [ ] Create utility functions/decorators to reduce LLM call boilerplate
- [ ] Update metrics collection and reporting logic
- [ ] Add comprehensive tests for metrics functionality
- [ ] Update documentation for new metrics configuration
- [ ] Ensure backward compatibility with existing configurations

## Testing Strategy
- Unit tests for metrics collection functions
- Integration tests for end-to-end metrics reporting
- Test different configuration combinations
- Verify LLM call instrumentation across all command types
- Test error conditions and edge cases
