# Planned Changes for feature/refactor-apply-implementation

## Overview
Refactor the `vibectl apply` implementation to bring it in line with the `vibectl edit` implementation structure for improved consistency, testability, and maintainability.

## Goals
- **Consistency**: Align apply implementation with edit implementation patterns
- **Testability**: Allow for easier and more complete testing by separating execution logic
- **Maintainability**: Extract prompts from monolithic `prompt.py` into dedicated module
- **Learning**: Gain familiarity with prompt refactoring patterns for other subcommands

## Current State Analysis

### `vibectl apply` (Current)
- **Command Handler**: `vibectl/subcommands/apply_cmd.py` - contains both command handling AND execution logic
- **Execution Logic**: Embedded directly in `apply_cmd.py` with `_run_intelligent_apply_workflow()`
- **Prompts**: Located in monolithic `vibectl/prompt.py`
- **Structure**: Monolithic, harder to test individual components

### `vibectl edit` (Target Pattern)
- **Command Handler**: `vibectl/subcommands/edit_cmd.py` - clean separation of concerns
- **Execution Logic**: `vibectl/execution/edit.py` - dedicated module for workflow logic
- **Prompts**: `vibectl/prompts/edit.py` - dedicated prompt module
- **Structure**: Modular, each component easily testable

## Planned Refactoring Steps

### Phase 1: Extract Execution Logic ✅ COMPLETED
- [x] Create `vibectl/execution/apply.py` module
- [x] Move `_run_intelligent_apply_workflow()` and related functions from `apply_cmd.py`
- [x] Update `apply_cmd.py` to use the extracted execution module
- [x] Ensure all existing functionality is preserved
- [x] **CLEANUP**: Remove dead code and unused imports from `apply_cmd.py`
- [x] **CLEANUP**: Achieve 100% test coverage for simplified `apply_cmd.py`

**Phase 1 Summary**: Successfully extracted 875 lines of execution logic to `vibectl/execution/apply.py`, cleaned up 985 lines of dead code from `apply_cmd.py`, and achieved clean separation of concerns. All tests passing with 100% coverage for the command handler.

### Phase 2: Extract Prompts ✅ COMPLETED
- [x] Create `vibectl/prompts/apply.py` module
- [x] Move apply-related prompts from `vibectl/prompt.py`:
  - `plan_apply_filescope_prompt_fragments()`
  - `summarize_apply_manifest_prompt_fragments()`
  - `correct_apply_manifest_prompt_fragments()`
  - `plan_final_apply_command_prompt_fragments()`
  - `apply_output_prompt()`
  - `PLAN_APPLY_PROMPT`
- [x] Update imports in execution and command modules
- [x] Remove apply prompts from main `prompt.py`

**Phase 2 Summary**: Successfully extracted all apply-related prompts to dedicated `vibectl/prompts/apply.py` module. The execution module now imports prompts from the dedicated module, achieving clean separation of concerns consistent with the edit implementation pattern.

**Prompt Enhancement**: Enhanced apply prompts with comprehensive examples to improve Claude 4 compatibility and ensure reliable multi-namespace fan-out behavior. Added detailed examples to both file scoping and command planning prompts that guide the LLM toward creating separate kubectl apply commands for each target namespace. Updated documentation to clearly explain the fan-out behavior with practical examples.

**Critical Bug Fixes**: Resolved critical async-related bugs in the apply workflow:
- Fixed variable scope issue where temp file paths were created before YAML validation, causing "file does not exist" errors
- Fixed namespace contamination in correction prompts that was causing deployment conflicts between target namespaces
- Updated correction and summary prompts to generate namespace-agnostic manifests that work correctly with fan-out deployment pattern
- Ensured temp files are only created when valid YAML is successfully generated and validated

### Phase 3: Testing Improvements ✅ COMPLETED
- [x] Add comprehensive unit tests for `vibectl/execution/apply.py`
- [x] Add unit tests for `vibectl/prompts/apply.py`
- [x] Update existing apply command tests to work with new structure
- [x] Add integration tests for the complete workflow

**Phase 3 Summary**: Successfully improved test coverage across both apply modules. Achieved 100% coverage for `vibectl/prompts/apply.py` with 8 comprehensive test functions covering all prompt generation functions, edge cases, and structure validation. Significantly improved coverage for `vibectl/execution/apply.py` from 22% to 57% by adding 7 comprehensive test functions for `execute_planned_commands()` covering single/multiple commands, YAML manifest handling, error scenarios, and edge cases. Fixed import issues and resolved test coherence problems. All 23 tests now pass reliably.

### Phase 4: Documentation and Cleanup
- [ ] Update `docs/intelligent_apply.md` to reflect new structure if needed
- [ ] Update `STRUCTURE.md` to document new modules
- [ ] Clean up any remaining references or unused imports
- [ ] Ensure consistent naming and patterns with edit implementation

## Success Criteria
- [ ] All existing apply functionality works identically
- [ ] Code structure matches edit implementation patterns
- [ ] Comprehensive test coverage for new modules
- [ ] Clean separation of concerns between command, execution, and prompts
- [ ] No regressions in apply workflow behavior
- [ ] Documentation updated appropriately

## Files to be Modified
- `vibectl/subcommands/apply_cmd.py` - simplify to match edit_cmd.py pattern
- `vibectl/prompt.py` - remove apply-specific prompts
- `vibectl/execution/apply.py` - NEW: extracted execution logic
- `vibectl/prompts/apply.py` - NEW: extracted prompt logic
- Tests for apply functionality
- `STRUCTURE.md` - document new modules

## Reference Implementation
The `vibectl edit` implementation serves as the reference pattern:
- Command handler delegates to execution module
- Execution module contains workflow logic
- Dedicated prompts module for all prompt functions
- Clear separation enables focused unit testing
