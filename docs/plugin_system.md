# Vibectl Plugin System

The vibectl plugin system allows users to customize and extend vibectl's behavior by replacing default prompts with custom ones. This provides powerful extensibility for teams, specific use cases, or workflow preferences.

## Overview

The plugin system enables users to:
- Install custom prompt plugins from JSON files
- Configure plugin precedence and fallback chains
- Override specific prompts for different commands
- Maintain version compatibility across vibectl updates
- Use plugins for enhanced security, documentation, or workflow customization

## Core Concepts

### Plugin Files
Plugins are JSON files containing:
- **Metadata**: Name, version, description, author, compatibility information
- **Prompt Mappings**: Custom prompts keyed by specific prompt identifiers

### Plugin Store
- File-based storage in `~/.config/vibectl/plugins/`
- Automatic validation during installation
- Version compatibility checking at install time and runtime

### Prompt Override System
- Flat key-based prompt resolution (e.g., `"patch_plan"`, `"apply_resource_summary"`)
- Configurable precedence order with fallback chains
- Graceful degradation to defaults on errors

## Installation and Management

### Installing Plugins

Install from local files (e.g., examples):
```bash
vibectl install plugin examples/plugins/enhanced-patch-summary-v1.json
```

Install with specific precedence:
```bash
vibectl install plugin examples/plugins/paranoid-security-vibe-v1.json --precedence first
vibectl install plugin examples/plugins/minimal-patch-summary-v1.json --precedence last
```

### Managing Plugins

List installed plugins:
```bash
vibectl plugin list
```

Uninstall plugins:
```bash
vibectl plugin uninstall paranoid-security-vibe
```

Update plugins:
```bash
vibectl plugin update paranoid-security-vibe examples/plugins/paranoid-security-vibe-v2.json
```

### Plugin Precedence

View current precedence order:
```bash
vibectl plugin precedence list
```

Set explicit precedence order:
```bash
vibectl plugin precedence set plugin-name-1 plugin-name-2 plugin-name-3
```

Add plugin to precedence list:
```bash
vibectl plugin precedence add new-plugin --position 2
```

Remove plugin from precedence:
```bash
vibectl plugin precedence remove old-plugin
```

## Plugin File Format

### Basic Structure

```json
{
  "plugin_metadata": {
    "name": "plugin-name",
    "version": "1.0.0",
    "description": "Description of what this plugin does",
    "author": "Plugin Author",
    "compatible_vibectl_versions": ">=0.9.0,<1.0.0",
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

### Version Compatibility

Version constraints support semantic versioning operators:
- `>=0.9.0` - Greater than or equal
- `<1.0.0` - Less than
- `==0.9.5` - Exact version
- `!=0.9.3` - Not equal
- `>0.8.0,<=0.9.10` - Range with multiple constraints

## Available Prompt Keys

### Currently Supported Commands

| Command | Planning Key | Summary Key | Description |
|---------|-------------|-------------|-------------|
| **patch** | `patch_plan` | `patch_resource_summary` | Resource patching operations |
| **apply** | `apply_plan` | `apply_resource_summary` | Basic apply operations |
| **apply** | `apply_filescope` | `apply_manifest_summary` | Intelligent apply workflow |
| **apply** | `apply_manifest_correction` | `apply_final_planning` | Advanced apply operations |

### Prompt Key Patterns

- **Planning prompts**: `{command}_plan` (e.g., `"patch_plan"`, `"apply_plan"`)
- **Summary prompts**: `{command}_resource_summary` (e.g., `"patch_resource_summary"`)
- **Specialized prompts**: Command-specific keys for advanced workflows

## Example Use Cases

### Security-Focused Analysis
```bash
vibectl install plugin examples/plugins/paranoid-security-vibe-v1.json
vibectl vibe "look around"
# Gets security-focused analysis highlighting vulnerabilities
```

### Minimal Output Style
```bash
vibectl install plugin examples/plugins/minimal-patch-summary-v1.json
vibectl patch deployment/nginx --image nginx:1.21
# Gets concise, minimal output summaries
```

### Enhanced Documentation
```bash
vibectl install plugin examples/plugins/verbose-explainer-vibe-v1.json
vibectl get vibe pods
# Gets detailed explanations and learning opportunities
```

## Error Handling and Fallbacks

### Graceful Degradation
- Plugin errors automatically fall back to default prompts
- WARNING level logging for failed custom prompts
- Version incompatibility prevents plugin usage without breaking functionality

### Attribution and Debugging
- Clear attribution when custom prompts are used
- Detailed error logging for plugin-related issues
- Environment variable `VIBECTL_TRACEBACK=1` for detailed error traces

### Version Validation
- Install-time compatibility checking prevents incompatible plugins
- Runtime validation ensures continued compatibility
- Automatic fallback when plugins become incompatible

## Creating Custom Plugins

### Plugin Development Guidelines

1. **Start with examples**: Use `examples/plugins/` as templates
2. **Test thoroughly**: Verify behavior with target commands
3. **Document clearly**: Include helpful descriptions and focus points
4. **Version appropriately**: Use semantic versioning for compatibility
5. **Handle edge cases**: Consider error scenarios and fallbacks

### Example Plugin Development

```json
{
  "plugin_metadata": {
    "name": "team-standards-v1",
    "version": "1.0.0",
    "description": "Enforces team standards for Kubernetes operations",
    "author": "DevOps Team",
    "compatible_vibectl_versions": ">=0.9.0",
    "created_at": "2024-03-01T10:00:00Z"
  },
  "prompt_mappings": {
    "patch_plan": {
      "description": "Adds team approval requirements for patches",
      "focus_points": [
        "Require approval for production changes",
        "Include team notification steps",
        "Add change tracking labels"
      ],
      "example_format": [
        "# Team Standards Patch Plan",
        "kubectl patch ... # (pending team approval)",
        "# Change ID: PATCH-2024-001"
      ]
    }
  }
}
```

## Integration with vibectl Commands

### Plugin-Enabled Commands

Currently, these commands support plugin customization:
- `vibectl patch` - Both planning and summary customization
- `vibectl apply` - Comprehensive workflow customization (6 prompt types)

### Command Integration Pattern

1. Commands use `@with_plugin_override()` decorators on prompt functions
2. Plugin keys follow established naming conventions
3. Fallback to default prompts when plugins fail or are unavailable
4. Error attribution helps identify plugin-related issues

### Future Command Integration

The plugin system is designed to expand to all vibectl commands. The established patterns make it straightforward to add plugin support to additional commands as they're enhanced.

## Configuration Integration

### Config System Integration
- Plugin precedence stored in vibectl config system
- Integration with existing `vibectl config` commands
- Respects user preferences and system defaults

### Performance Considerations
- Zero overhead for non-plugin users
- Efficient plugin resolution with caching
- Minimal impact on command execution time

## Advanced Usage

### Multiple Plugin Coordination
```bash
# Install complementary plugins
vibectl install plugin team-security-v1.json --precedence first
vibectl install plugin documentation-enhanced-v1.json --precedence last

# View effective precedence
vibectl plugin precedence list
```

### Workflow-Specific Plugins
```bash
# Development workflow
vibectl install plugin dev-friendly-v1.json

# Production workflow
vibectl install plugin production-safe-v1.json --precedence first
```

### Plugin Development Workflow
```bash
# Test plugin locally
vibectl install plugin ./my-plugin-draft.json

# Iterate and update
vibectl plugin update my-plugin-draft ./my-plugin-v2.json

# Deploy to team
cp my-plugin-v2.json /shared/vibectl-plugins/
```

## Future Development

The plugin system provides a foundation for:
- Additional command integrations
- Enhanced plugin discovery and sharing
- Plugin validation and testing frameworks
- Community plugin repositories
- Advanced plugin features (conditional logic, templating, etc.)

The current implementation focuses on prompt replacement as the primary customization mechanism, with room for expansion into other plugin types as the system evolves.
