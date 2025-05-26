# Planned Changes for feature/refactor-prompt-py

## Overview
Systematically refactor the large `vibectl/prompt.py` file (2134 lines) into separate subcommand-specific files, building on the existing pattern established with `edit.py` and `apply.py`.

## Current State Analysis
- **Main file**: `vibectl/prompt.py` (2134 lines) - contains prompts for all subcommands plus shared utilities
- **Existing separated files**: `vibectl/prompts/edit.py`, `vibectl/prompts/apply.py` (but still import heavily from main `prompt.py`)
- **Extensive cross-dependencies**: All subcommand files (`*_cmd.py`) and test files import from `vibectl.prompt`

## Key Import Categories to Refactor
1. **Planning prompts**: `PLAN_GET_PROMPT`, `PLAN_DELETE_PROMPT`, `PLAN_LOGS_PROMPT`, etc.
2. **Summary prompts**: `get_resource_prompt`, `delete_resource_prompt`, `logs_prompt`, etc.
3. **Shared utilities**: `fragment_current_time`, `fragment_memory_context`, `create_planning_prompt`, `create_summary_prompt`
4. **Schema definitions**: `_SCHEMA_DEFINITION_JSON`, `_EDIT_RESOURCESCOPE_SCHEMA_JSON`
5. **Vibe-specific**: `plan_vibe_fragments`, `vibe_autonomous_prompt`, `plan_check_fragments`
6. **Memory functions**: `memory_update_prompt`, `memory_fuzzy_update_prompt`

## Files That Need Import Updates
- All subcommand files (`*_cmd.py`)
- Test files
- `vibectl/execution/vibe.py`
- `vibectl/memory.py`
- Existing separated prompt files (`edit.py`, `apply.py`)

## Architecture Decisions to Make
1. **Shared utilities location**: `vibectl/prompt.py` vs `vibectl/prompts/shared.py`
2. **Vibe-specific logic**: `vibectl/prompts/vibe.py` vs shared file
3. **Schema definitions**: Separate file or embedded in relevant prompt files
4. **Memory functions**: Keep in main or move to `vibectl/prompts/memory.py`

## Planned Implementation Steps

### Phase 1: Analysis and Setup
- [ ] Complete dependency analysis of all imports
- [ ] Create detailed mapping of what goes where
- [ ] Design new module structure
- [ ] Plan import migration strategy

### Phase 2: Create New Module Structure
- [ ] Create `vibectl/prompts/shared.py` for common utilities
- [ ] Create subcommand-specific prompt files (get, delete, logs, etc.)
- [ ] Create `vibectl/prompts/vibe.py` for vibe-specific functionality
- [ ] Create `vibectl/prompts/memory.py` for memory-related prompts

### Phase 3: Migrate Content Systematically
- [ ] Move shared utilities to `shared.py`
- [ ] Move subcommand-specific prompts to respective files
- [ ] Move vibe functionality to `vibe.py`
- [ ] Move memory functionality to `memory.py`
- [ ] Update existing `edit.py` and `apply.py` to use new shared modules

### Phase 4: Update Import Dependencies
- [ ] Update all `*_cmd.py` files to import from new locations
- [ ] Update test files
- [ ] Update `vibectl/execution/vibe.py`
- [ ] Update `vibectl/memory.py`
- [ ] Create compatibility layer if needed for transition

### Phase 5: Testing and Validation
- [ ] Run full test suite
- [ ] Verify all imports resolve correctly
- [ ] Check for any missing functionality
- [ ] Performance validation
- [ ] Clean up main `prompt.py` to minimal shared exports

### Phase 6: Documentation and Cleanup
- [ ] Update STRUCTURE.md to reflect new organization
- [ ] Add docstrings to new modules
- [ ] Remove old imports and unused code
- [ ] Final test run and validation

## Risk Mitigation
- Keep original `prompt.py` as fallback during transition
- Use feature branch to allow easy rollback
- Test each phase thoroughly before proceeding
- Maintain backwards compatibility during migration
- Use systematic approach to avoid missing dependencies

## Success Criteria
- All functionality preserved
- Imports clearly organized by subcommand
- Shared utilities properly factored
- Test suite passes completely
- Code is more maintainable and navigable
- File sizes are reasonable (<500 lines per file)
