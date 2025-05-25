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
- ✅ **Step 1**: Fetch the target resource using kubectl get
- ✅ **Step 2**: Summarize resource into natural language (targeting ~1 screen of text)
- ✅ **Step 3**: Invoke editor with natural language summary (using `click.edit()` pattern from `instructions_set`)
- ✅ **Step 4**: Detect changes between original and edited summaries
- ✅ **Step 5**: Use LLM to analyze edits and generate appropriate patch
- ✅ **Step 6**: Apply the generated patch to the resource
- ✅ **Step 7**: Summarize the result to user

### 7. Custom Execution Logic
- ✅ Create execution module similar to `vibectl/execution/check.py`
- ✅ Handle resource fetching, summarization, editing workflow, and patch generation
- ✅ Integrate with existing LLM interfaces and patch command logic
- ✅ **FIXED**: Model name configuration issue - now properly uses `output_flags.model_name` instead of defaulting to `gpt-4`

### 8. Editor Integration
- ✅ Use `
