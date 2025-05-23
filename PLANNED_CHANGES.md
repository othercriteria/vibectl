# Planned Changes for feature/intelligent-edit

## Overview
Implement `vibectl edit` command with intelligent editing capabilities, similar to the existing `vibectl apply` with `intelligent_apply.md` functionality.

## Implementation Status

### ✅ Completed Components

### 1. Configuration Support
- ✅ Added `intelligent_edit` config option to `vibectl/config.py` (defaults to `True`)
- ✅ Integrated config flag to gate intelligent editing behavior
- ✅ Default behavior when disabled: standard kubectl edit functionality

### 2. Basic Edit Command
- ✅ Created `vibectl/subcommands/edit_cmd.py` with `run_edit_command()` function
- ✅ Added edit command to `vibectl/cli.py` following existing patterns
- ✅ Support for standard kubectl edit arguments and options
- ✅ Handle both standard usage and "vibe" mode

### 3. Edit-Specific Prompts
- ✅ Created `vibectl/prompts/edit.py` with edit-specific prompts
- ✅ Implemented `PLAN_EDIT_PROMPT` for planning edit operations
- ✅ Implemented `edit_resource_prompt()` for summarizing edit results
- ✅ Updated imports in edit_cmd.py to use new prompts

### 4. Standard Mode Behavior
- ✅ Without `intelligent_edit` config: Pass through to kubectl edit directly
- ✅ With "vibe" but `intelligent_edit` disabled: Basic vibe processing without intelligent workflow

### 5. Documentation
- ✅ Updated STRUCTURE.md to document new prompts/ directory
- ✅ Updated STRUCTURE.md to include edit command in command systems
- ✅ Updated CLI help with examples for traditional and vibe modes

## 🚧 Pending Components

### 6. Intelligent Edit Workflow (when enabled)
- ⏳ **Step 1**: Fetch the target resource using kubectl get
- ⏳ **Step 2**: Summarize resource into natural language (targeting ~1 screen of text)
- ⏳ **Step 3**: Invoke editor with natural language summary (using `click.edit()` pattern from `instructions_set`)
- ⏳ **Step 4**: Detect changes between original and edited summaries
- ⏳ **Step 5**: Use LLM to analyze edits and generate appropriate patch
- ⏳ **Step 6**: Apply the generated patch to the resource
- ⏳ **Step 7**: Summarize the result to user

### 7. Custom Execution Logic
- ⏳ Create execution module similar to `vibectl/execution/check.py`
- ⏳ Handle resource fetching, summarization, editing workflow, and patch generation
- ⏳ Integrate with existing LLM interfaces and patch command logic

### 8. Editor Integration
- ⏳ Use `click.edit()` for text editing (as seen in `instructions_set`)
- ⏳ Handle cases where editor is cancelled or returns no changes
- ⏳ Provide clear instructions in the editable text

### 9. Testing
- ⏳ Unit tests for basic edit command functionality
- ⏳ Mock tests for intelligent editing workflow
- ⏳ Integration tests for patch generation and application

## Technical Details

### Files Created/Modified
- ✅ `vibectl/config.py` - Added `intelligent_edit` config option
- ✅ `vibectl/cli.py` - Added edit command definition
- ✅ `vibectl/subcommands/edit_cmd.py` - Main command implementation
- ✅ `vibectl/prompts/edit.py` - Edit-specific prompts
- ✅ `vibectl/prompts/__init__.py` - Prompts package initialization
- ⏳ `vibectl/execution/edit.py` - Custom execution logic for intelligent workflow
- ⏳ `tests/subcommands/test_edit_cmd.py` - Comprehensive tests

### Dependencies
- ✅ Reuse existing patch command logic for resource modification
- ✅ Leverage existing LLM interface for summarization and patch generation
- ✅ Integrate with existing error handling and output formatting

### Error Handling
- ⏳ Handle editor cancellation gracefully
- ⏳ Validate generated patches before application
- ⏳ Provide clear error messages for invalid edits or failed patches
- ⏳ Support dry-run mode for testing patches

## Examples of Current Usage

```bash
# Standard kubectl edit behavior (working)
vibectl edit deployment/nginx

# Edit with specific editor (working)
vibectl edit service api-server --editor=vim

# Vibe mode - currently uses basic vibe workflow
vibectl edit vibe "nginx deployment liveness and readiness config"
vibectl edit vibe "add resource limits to the frontend deployment"
vibectl edit vibe "configure ingress for the api service"
```

## Next Steps
1. Implement intelligent edit workflow execution logic
2. Create resource fetching and summarization functionality
3. Implement editor integration with natural language summaries
4. Add patch generation from edited summaries
5. Create comprehensive tests for all functionality
6. Add `--dry-run` flag support

## Implementation Notes
- ✅ Built on proven patterns from `vibectl patch` and `vibectl apply`
- ✅ Ensured backward compatibility with standard kubectl edit usage
- ✅ Organized prompts in separate module to keep main prompt.py manageable
- ✅ Clear documentation and examples provided
- ⏳ Consider adding `--dry-run` flag for testing intelligent edits
