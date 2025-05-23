# Planned Changes for feature/vibectl-patch

## Overview
Implement `vibectl patch` command to provide intelligent Kubernetes resource patching with LLM assistance.

## Core Functionality

### Basic Patch Operations
- Support strategic merge patch (default), JSON merge patch, and JSON patch types
- Handle both inline patches (`-p`) and patch files (`--patch-file`)
- Support resource identification via file (`-f`) or type/name
- Implement all standard kubectl patch options (dry-run, field-manager, etc.)

### Intelligent Patch Features ("vibe" mode)
- **Natural Language Patch Descriptions**: Allow users to describe patches in natural language
  - Example: `vibectl patch vibe "scale nginx deployment to 5 replicas"`
  - Example: `vibectl patch vibe "update container image to nginx:1.21 in my-app deployment"`
- **Context-Aware Patching**: Use current resource state to generate appropriate patches
- **Patch Validation**: Validate patches before application using dry-run
- **Patch Generation**: Generate patches from natural language descriptions

### Architecture
- Create `vibectl/subcommands/patch.py` following existing patterns
- Reuse validation and LLM interaction patterns from `apply.py`
- Implement patch-specific prompts and schemas
- Add comprehensive test coverage

## Implementation Plan

1. **Basic CLI Structure** (Step 1)
   - Add patch command to CLI
   - Implement argument parsing for all kubectl patch options
   - Create basic kubectl pass-through functionality

2. **Intelligent Patch Logic** (Step 2)
   - Add "vibe" subcommand for natural language patches
   - Implement LLM prompt for patch generation
   - Add resource state fetching for context

3. **Validation and Safety** (Step 3)
   - Implement patch validation using dry-run
   - Add confirmation prompts for dangerous operations
   - Ensure proper error handling

4. **Testing and Documentation** (Step 4)
   - Add comprehensive unit tests
   - Add integration tests for patch scenarios
   - Update documentation

## Shared Components with Apply
- LLM interaction patterns
- Resource validation utilities
- Error handling and logging
- Memory integration for context

## Future Enhancements
- Batch patching with natural language
- Patch history and rollback
- Advanced patch conflict resolution
