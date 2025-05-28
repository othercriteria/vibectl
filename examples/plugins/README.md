# Vibectl Plugin Examples

This directory contains example plugin files that demonstrate how to customize vibectl's prompts.

## Plugin File Format

Each plugin is a JSON file with the following structure:

```json
{
  "plugin_metadata": {
    "name": "plugin-name",
    "version": "1.0.0",
    "description": "Description of what this plugin does",
    "author": "Plugin Author",
    "compatible_vibectl_versions": ">=0.8.0,<1.0.0",
    "created_at": "2024-01-15T10:00:00Z"
  },
  "prompt_mappings": {
    "prompt_key": {
      "description": "What this prompt customization does",
      "focus_points": [
        "What to focus on in output",
        "Other important aspects"
      ],
      "example_format": [
        "Example output line 1",
        "Example output line 2"
      ]
    }
  }
}
```

## Available Prompt Keys

Currently supported prompt keys for customization:

- `patch_plan`: Planning prompts for `kubectl patch` commands (generates the kubectl command)
- `patch_resource_summary`: Summary output for `kubectl patch` commands
- `check_plan`: Planning prompts for `vibectl check` commands (evaluates predicates against cluster state)
- `events_plan`: Planning prompts for `kubectl events` commands (generates the kubectl command)
- `events_resource_summary`: Summary output for `kubectl events` commands
- `get_plan`: Planning prompts for `kubectl get` commands (generates the kubectl command)
- `get_resource_summary`: Summary output for `kubectl get` commands
- `logs_plan`: Planning prompts for `kubectl logs` commands (generates the kubectl command)
- `logs_resource_summary`: Summary output for `kubectl logs` commands
- `port_forward_plan`: Planning prompts for `kubectl port-forward` commands (generates the kubectl command)
- `port_forward_resource_summary`: Summary output for `kubectl port-forward` commands
- `vibe_plan`: Planning prompts for `vibectl vibe` autonomous commands (generates the next action)
- `vibe_resource_summary`: Summary output for `vibectl vibe` autonomous command results
- `memory_update`: Custom memory update behavior for both explicit `vibectl memory update` commands and internal memory operations

## Example Plugins

### enhanced-patch-summary-v1.json
Provides enhanced, detailed summaries for patch operations including:
- Detailed resource state tracking
- Before/after change information
- Timing and strategy details
- Related resource impact

### minimal-patch-summary-v1.json
Provides minimal, concise summaries for patch operations focusing on:
- Essential status information only
- Simple success/failure indicators
- Critical errors only

### minimal-events-summary-v1.json
Provides minimal, focused summaries for kubectl events output focusing on:
- Critical errors and warnings only
- Recent activity (last 5-10 minutes)
- Resource names with issues
- Simple status indicators with emojis

### annotating-patch-v1.json
Demonstrates both planning and summarizing customization with operation tracking:
- Adds encoded annotations to patch commands using Caesar cipher (shift +2)
- Decodes annotations in summaries to show operation context
- Shows how a single plugin can customize both planning and summarizing
- Uses simple cipher: PATCH→RCEEJ, SCALE→UECNG, UPDATE→WRIKCG, LABEL→NCDJN

### security-focused-check-v1.json
Demonstrates check command customization with security and compliance focus:
- Enhanced task description emphasizing security best practices
- Specialized examples for RBAC, network policies, secrets, and privileged access
- Security-focused context instructions and analysis approach
- Detailed explanations highlighting security implications and violations

### smart-port-selection-v1.json
Demonstrates intelligent port selection for port-forward commands:
- Suggests alternative local ports to avoid conflicts with common services
- Provides smart port mappings (e.g., 8000 instead of 8080, 5433 instead of 5432)
- Includes helpful tips for resolving port conflicts
- Focuses on developer-friendly port selections for common databases and web services
- Covers Redis, PostgreSQL, MongoDB, web servers, and Node.js applications

### memory-update-counter-v1.json
Demonstrates custom memory update behavior with usage tracking:
- Adds a running counter of memory update operations
- Automatically initializes counter to 1 for first memory update
- Increments counter on each subsequent memory update
- Affects both explicit `vibectl memory update` commands and internal memory operations
- Shows how plugins can customize core system behavior globally

### clumsy-vibe-v1.json
Demonstrates a well-intentioned but clumsy vibe planner:
- Overcomplilcates simple requests with excessive flags and options
- Gets confused about ambiguous requests and overthinks decisions
- Shows planning-only customization (no summary override)
- Examples include overly broad searches and unnecessary complexity
- Educational example of how plugins can change planning behavior

### devious-organizer-vibe-v1.json
Demonstrates both planning and summary customization with organizational focus:
- Secretly adds organizational labels to resources during operations
- Summarizes results while highlighting organizational opportunities
- Planning adds tracking labels like "last-scaled-by" and "created-by"
- Summary suggests missing labels and organizational improvements
- Shows how a single plugin can customize both planning and summarizing

### terse-minimalist-vibe-v1.json
Demonstrates ultra-concise, code-golf style responses:
- Planning uses minimal commands with terse explanations
- Summary uses emojis and one-line status reports
- Examples show minimal viable responses without fluff
- Demonstrates extreme brevity while maintaining functionality
- Planning and summary both override for consistent minimal style

### paranoid-security-vibe-v1.json
Demonstrates security-focused planning and summarizing:
- Planning always considers security implications before acting
- Requires security justification for risky operations
- Summary highlights security contexts, privileged containers, and risks
- Examples show security-first decision making and risk assessment
- Educational for security-conscious Kubernetes operations

### verbose-explainer-vibe-v1.json
Demonstrates summary-only customization with educational focus:
- Provides extremely detailed explanations of command results
- Breaks down Kubernetes concepts and resource relationships
- Includes troubleshooting tips and learning opportunities
- Shows how summary plugins can be educational tools
- Only overrides summary prompt, uses default planning behavior

## Installation (Future)

Once the plugin system is implemented, you'll be able to install these plugins with:

```bash
# Install a plugin
vibectl install plugin examples/plugins/enhanced-patch-summary-v1.json

# List installed plugins
vibectl plugins list

# Set plugin precedence
vibectl config set plugins.precedence "enhanced-patch-summary-v1,minimal-patch-summary-v1"
```

## Development Notes

- Plugin keys use flat naming (e.g., `patch_resource_summary`) rather than hierarchical
- Version compatibility follows semantic versioning
- All plugins should include comprehensive metadata
- Example formats should use rich.Console() markup syntax
- A single plugin can customize multiple prompt types (planning and summarizing)
