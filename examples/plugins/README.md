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
