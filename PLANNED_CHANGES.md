# Planned Changes for `vibectl vibe` Feature

## Overview

The `vibectl vibe` command will be enhanced to provide autonomous Kubernetes
operations guided by LLM memory and planning. The command will move from its
current state (displaying an intro message) to executing planned actions based on
memory context.

## Key Changes

1. Move intro message functionality to bare `vibectl` command
2. Implement memory-guided planning for `vibectl vibe`
   - Use memory context to understand current state
   - Generate and execute appropriate kubectl commands
   - Update memory with results
   - Plan next steps
3. Support no-argument mode for `vibectl vibe`
   - Function with no user-provided request string
   - Use memory, custom instructions, and K8s knowledge to guide actions
   - Execute initial discovery commands (cluster-info, current-context) when no context exists

## Implementation Plan

1. Refactor Command Structure
   - Move intro message to `vibectl` base command
   - Update `vibectl vibe` to use planning framework
   - Support execution without arguments

2. Memory Integration
   - Enhance memory prompt to track planned actions
   - Update memory after each action with results
   - Use memory to guide next steps

3. Command Execution
   - Implement confirmation flow similar to `vibectl delete vibe`
   - Execute kubectl commands based on plan
   - Handle and report results
   - Implement proper fallback commands for no-context scenarios

4. Testing
   - Add unit tests for planning logic
   - Add integration tests for memory updates
   - Test confirmation flow
   - Test no-argument mode with empty memory

## Example Flow

```text
Memory: "We are working in `foo` namespace. We have created deployment `bar`.
We need to create a service for `bar`."

Command: vibectl vibe "keep working on the bar system"

Action: Create service/bar-service
Confirmation: [Y/n]

Updated Memory: "We are working in the `foo` namespace. We have created
deployment `bar` with service `service/bar-service`. We don't know if it is
alive yet."
```

## No-Argument Example Flow

```text
Memory: <empty>

Command: vibectl vibe

Planning: Need to understand the cluster context first
Action: kubectl cluster-info
Confirmation: [Y/n]

Updated Memory: "We are working with a Kubernetes cluster running version 1.25.4
with control plane at https://cluster.example.com. Next, we should understand
what namespaces and workloads are available."
```

## Success Criteria

1. Bare `vibectl` shows intro message
2. `vibectl vibe` executes planned actions based on memory
3. Memory updates reflect completed actions and next steps
4. User confirmation required for kubectl operations
5. Clear feedback on action results
6. Test coverage for new functionality
7. `vibectl vibe` works correctly without arguments
8. System uses discovery commands when no prior context exists
