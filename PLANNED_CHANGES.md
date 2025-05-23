# Planned Changes for feature/intelligent-edit

## Overview
Implement `vibectl edit` command with intelligent editing capabilities, similar to the existing `vibectl apply` with `intelligent_apply.md` functionality.

## Core Components

### 1. Configuration Support
- Add `intelligent_edit` config option to `vibectl/config.py`
- Gate intelligent editing behavior behind this config flag
- Default behavior when disabled: standard kubectl edit functionality

### 2. Basic Edit Command
- Create `vibectl/subcommands/edit_cmd.py` with `run_edit_command()` function
- Add edit command to `vibectl/cli.py` following existing patterns
- Support standard kubectl edit arguments and options
- Handle both standard usage and "vibe" mode

### 3. Standard Mode Behavior
- Without `intelligent_edit` config: Pass through to kubectl edit directly
- With "vibe" but `intelligent_edit` disabled: Basic vibe processing without intelligent workflow

### 4. Intelligent Edit Workflow (when enabled)
- **Step 1**: Fetch the target resource using kubectl get
- **Step 2**: Summarize resource into natural language (targeting ~1 screen of text)
- **Step 3**: Invoke editor with natural language summary (using `click.edit()` pattern from `instructions_set`)
- **Step 4**: Detect changes between original and edited summaries
- **Step 5**: Use LLM to analyze edits and generate appropriate patch
- **Step 6**: Apply the generated patch to the resource
- **Step 7**: Summarize the result to user

### 5. Custom Execution Logic
- Create execution module similar to `vibectl/execution/check.py`
- Handle resource fetching, summarization, editing workflow, and patch generation
- Integrate with existing LLM interfaces and patch command logic

### 6. Editor Integration
- Use `click.edit()` for text editing (as seen in `instructions_set`)
- Handle cases where editor is cancelled or returns no changes
- Provide clear instructions in the editable text

### 7. Testing
- Unit tests for basic edit command functionality
- Mock tests for intelligent editing workflow
- Integration tests for patch generation and application

## Technical Details

### Files to Create/Modify
- `vibectl/config.py` - Add `intelligent_edit` config option
- `vibectl/cli.py` - Add edit command definition
- `vibectl/subcommands/edit_cmd.py` - Main command implementation
- `vibectl/execution/edit.py` - Custom execution logic for intelligent workflow
- `tests/subcommands/test_edit_cmd.py` - Comprehensive tests

### Dependencies
- Reuse existing patch command logic for resource modification
- Leverage existing LLM interface for summarization and patch generation
- Integrate with existing error handling and output formatting

### Error Handling
- Handle editor cancellation gracefully
- Validate generated patches before application
- Provide clear error messages for invalid edits or failed patches
- Support dry-run mode for testing patches

## Examples of Expected Usage

```bash
# Standard kubectl edit behavior
vibectl edit deployment/nginx

# Vibe mode with intelligent editing (when config enabled)
vibectl edit deployment nginx vibe "scale to 3 replicas and add memory limits"

# Standard vibe mode (intelligent_edit disabled)
vibectl edit vibe "update the nginx deployment with more replicas"
```

## Implementation Notes
- Build on proven patterns from `vibectl patch` and `vibectl apply`
- Ensure backward compatibility with standard kubectl edit usage
- Provide clear documentation and examples
- Consider adding `--dry-run` flag for testing intelligent edits
