# Implementation Plan for prompt.py Refactoring

## Analysis Summary

Based on dependency analysis, the `vibectl/prompt.py` file (2133 lines, 75KB) needs to be systematically refactored into modular components.

### Current Import Patterns
- **36 total import locations** across the codebase
- **16 subcommand files** import planning prompts and summary functions
- **17 test files** import various prompt functions
- **2 existing prompt files** (`edit.py`, `apply.py`) import shared utilities
- **2 other vibectl files** import specific functionality

### Key Shared Utilities (High Reuse)
These must go into `vibectl/prompts/shared.py`:
- `create_planning_prompt()` - Used by all subcommands
- `create_summary_prompt()` - Used by all subcommands
- `fragment_current_time()` - Used by edit.py, apply.py, and others
- `fragment_memory_context()` - Used by edit.py and others
- `fragment_json_schema_instruction()` - Used by edit.py, apply.py
- Schema constants: `_SCHEMA_DEFINITION_JSON`, `_EDIT_RESOURCESCOPE_SCHEMA_JSON`

### Import Categories by Function Type

#### 1. Planning Prompts (14 constants)
Each subcommand imports its `PLAN_*_PROMPT` constant:
- `PLAN_GET_PROMPT`, `PLAN_DELETE_PROMPT`, `PLAN_LOGS_PROMPT`, etc.
- These will move to respective subcommand prompt files

#### 2. Summary Functions (16 functions)
Each subcommand imports its summary function:
- `get_resource_prompt`, `delete_resource_prompt`, `logs_prompt`, etc.
- These will move to respective subcommand prompt files

#### 3. Vibe-Specific Functions (3 functions)
Special functionality for vibe operations:
- `plan_vibe_fragments`, `vibe_autonomous_prompt`, `plan_check_fragments`
- These will move to `vibectl/prompts/vibe.py`

#### 4. Memory Functions (2 functions)
Memory-related prompts used by memory subsystem:
- `memory_update_prompt`, `memory_fuzzy_update_prompt`
- Potential circular import risk - needs careful handling

## Detailed File-by-File Migration Plan

### Phase 1: Create Shared Infrastructure

#### A. Create `vibectl/prompts/shared.py`
```python
# Move these from main prompt.py:
- create_planning_prompt()
- create_summary_prompt()
- fragment_current_time()
- fragment_memory_context()
- fragment_json_schema_instruction()
- fragment_concision()
- format_examples()
- format_ml_examples()
- get_formatting_fragments()
```

#### B. Create `vibectl/prompts/schemas.py`
```python
# Move schema constants:
- _SCHEMA_DEFINITION_JSON
- _EDIT_RESOURCESCOPE_SCHEMA_JSON
```

### Phase 2: Create Subcommand-Specific Files

#### C. Create subcommand prompt files:
1. `vibectl/prompts/get.py`
   - `PLAN_GET_PROMPT`
   - `get_resource_prompt()`

2. `vibectl/prompts/delete.py`
   - `PLAN_DELETE_PROMPT`
   - `delete_resource_prompt()`

3. `vibectl/prompts/logs.py`
   - `PLAN_LOGS_PROMPT`
   - `logs_prompt()`

4. `vibectl/prompts/describe.py`
   - `PLAN_DESCRIBE_PROMPT`
   - `describe_resource_prompt()`

5. `vibectl/prompts/events.py`
   - `PLAN_EVENTS_PROMPT`
   - `events_prompt()`

6. `vibectl/prompts/create.py`
   - `PLAN_CREATE_PROMPT`
   - `create_resource_prompt()`

7. `vibectl/prompts/version.py`
   - `PLAN_VERSION_PROMPT`
   - `version_prompt()`

8. `vibectl/prompts/cluster_info.py`
   - `PLAN_CLUSTER_INFO_PROMPT`
   - `cluster_info_prompt()`

9. `vibectl/prompts/scale.py`
   - `PLAN_SCALE_PROMPT`
   - `scale_resource_prompt()`

10. `vibectl/prompts/wait.py`
    - `PLAN_WAIT_PROMPT`
    - `wait_resource_prompt()`

11. `vibectl/prompts/rollout.py`
    - `PLAN_ROLLOUT_PROMPT`
    - `rollout_status_prompt()`
    - `rollout_history_prompt()`
    - `rollout_general_prompt()`

12. `vibectl/prompts/port_forward.py`
    - `PLAN_PORT_FORWARD_PROMPT`
    - `port_forward_prompt()`

13. `vibectl/prompts/diff.py`
    - `PLAN_DIFF_PROMPT`
    - `diff_output_prompt()`

14. `vibectl/prompts/patch.py`
    - `PLAN_PATCH_PROMPT`
    - `patch_resource_prompt()`

### Phase 3: Special Cases

#### D. Create `vibectl/prompts/vibe.py`
```python
# Move vibe-specific functions:
- plan_vibe_fragments()
- vibe_autonomous_prompt()
- plan_check_fragments()
```

#### E. Handle Memory Functions
**Decision: Keep in main `prompt.py` initially**
- `memory_update_prompt()`
- `memory_fuzzy_update_prompt()`
- Only used by `vibectl/memory.py` and `vibectl/execution/vibe.py`
- Moving might create circular imports - assess after other migrations

#### F. Handle Recovery Function
**Decision: Create `vibectl/prompts/recovery.py`**
- `recovery_prompt()` - Used by recovery mechanisms

### Phase 4: Update Existing Files

#### G. Update `vibectl/prompts/edit.py`
Change imports from:
```python
from vibectl.prompt import (
    fragment_current_time,
    fragment_json_schema_instruction,
    # etc.
)
```
To:
```python
from .shared import (
    fragment_current_time,
    fragment_json_schema_instruction,
    # etc.
)
from .schemas import _EDIT_RESOURCESCOPE_SCHEMA_JSON
```

#### H. Update `vibectl/prompts/apply.py`
Similar import updates to use shared modules.

### Phase 5: Update All Import Dependencies

#### I. Update Subcommand Files (16 files)
Each `vibectl/subcommands/*_cmd.py` file needs updated imports:

**Before:**
```python
from vibectl.prompt import PLAN_GET_PROMPT, get_resource_prompt
```

**After:**
```python
from vibectl.prompts.get import PLAN_GET_PROMPT, get_resource_prompt
```

#### J. Update Test Files (17 files)
Update all test imports to use new locations.

#### K. Update Other Files
- `vibectl/execution/vibe.py` - Update memory function import
- `vibectl/execution/check.py` - Update to use `vibectl.prompts.vibe`

### Phase 6: Create Transition Compatibility

#### L. Update Main `vibectl/prompt.py`
Create compatibility layer with re-exports:
```python
# Backwards compatibility imports
from .prompts.shared import (
    create_planning_prompt,
    create_summary_prompt,
    # etc.
)
from .prompts.get import PLAN_GET_PROMPT, get_resource_prompt
from .prompts.delete import PLAN_DELETE_PROMPT, delete_resource_prompt
# etc. for all subcommands

# Keep memory functions here temporarily
def memory_update_prompt(...): ...
def memory_fuzzy_update_prompt(...): ...
```

This allows incremental migration without breaking existing imports.

## Implementation Order

### Step 1: Shared Infrastructure (Day 1)
1. Create `vibectl/prompts/shared.py`
2. Create `vibectl/prompts/schemas.py`
3. Test that existing edit.py and apply.py can import from new locations

### Step 2: High-Impact Subcommands (Day 2-3)
Start with most frequently used subcommands:
1. `get.py` (most used)
2. `describe.py`
3. `delete.py`
4. `logs.py`

### Step 3: Remaining Subcommands (Day 4-5)
Complete the remaining 10 subcommand files.

### Step 4: Special Cases (Day 6)
1. `vibe.py`
2. `recovery.py`
3. Update existing edit.py and apply.py imports

### Step 5: Update Dependencies (Day 7-8)
1. Update all subcommand file imports
2. Update all test file imports
3. Update other vibectl file imports

### Step 6: Testing & Cleanup (Day 9-10)
1. Full test suite validation
2. Remove compatibility layer from main prompt.py
3. Final cleanup and documentation

## Risk Mitigation

### Circular Import Prevention
- Keep memory functions in main module initially
- Shared utilities in separate module to avoid cycles
- Test imports carefully at each step

### Backwards Compatibility
- Maintain compatibility layer during transition
- Incremental migration allows rollback at any point
- Extensive testing at each phase

### Testing Strategy
- Run test suite after each major phase
- Validate imports resolve correctly
- Performance testing to ensure no regression

## Success Metrics

- All 2133 lines properly distributed across <15 focused files
- Each file <500 lines (target <300 lines)
- All tests passing
- No circular import issues
- Clear separation of concerns by subcommand
- Maintained backwards compatibility during transition

## Directory Structure After Refactoring

```
vibectl/
├── prompt.py (minimal re-exports + memory functions temporarily)
├── prompts/
│   ├── __init__.py
│   ├── shared.py (common utilities)
│   ├── schemas.py (JSON schemas)
│   ├── vibe.py (vibe-specific)
│   ├── recovery.py (recovery prompts)
│   ├── get.py (get command)
│   ├── delete.py (delete command)
│   ├── logs.py (logs command)
│   ├── describe.py (describe command)
│   ├── events.py (events command)
│   ├── create.py (create command)
│   ├── version.py (version command)
│   ├── cluster_info.py (cluster-info command)
│   ├── scale.py (scale command)
│   ├── wait.py (wait command)
│   ├── rollout.py (rollout command)
│   ├── port_forward.py (port-forward command)
│   ├── diff.py (diff command)
│   ├── patch.py (patch command)
│   ├── edit.py (existing, updated imports)
│   └── apply.py (existing, updated imports)
```

This structure provides clear organization, eliminates the 2133-line monolith, and maintains clean separation of concerns while preserving all existing functionality.
