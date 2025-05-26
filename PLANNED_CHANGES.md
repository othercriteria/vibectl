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

### Phase 1: Extract Execution Logic
- [ ] Create `vibectl/execution/apply.py` module
- [ ] Move `_run_intelligent_apply_workflow()` and related functions from `apply_cmd.py`
- [ ] Update `apply_cmd.py` to use the extracted execution module
- [ ] Ensure all existing functionality is preserved

### Phase 2: Extract Prompts
- [ ] Create `vibectl/prompts/apply.py` module
- [ ] Move apply-related prompts from `vibectl/prompt.py`:
  - `plan_apply_filescope_prompt_fragments()`
  - `summarize_apply_manifest_prompt_fragments()`
  - `correct_apply_manifest_prompt_fragments()`
  - `plan_final_apply_command_prompt_fragments()`
  - `apply_output_prompt()`
  - `PLAN_APPLY_PROMPT`
- [ ] Update imports in execution and command modules
- [ ] Remove apply prompts from main `prompt.py`

### Phase 3: Testing Improvements
- [ ] Add comprehensive unit tests for `vibectl/execution/apply.py`
- [ ] Add unit tests for `vibectl/prompts/apply.py`
- [ ] Update existing apply command tests to work with new structure
- [ ] Add integration tests for the complete workflow

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
