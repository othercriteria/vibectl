# Planned Changes for feature/plugin-system

## Overview
Implement a plugin system that allows users to replace default prompts with custom ones, providing extensibility and customization capabilities.

## Core Requirements
- [ ] User can replace default prompts with custom prompts
- [ ] Configurable via config options
- [ ] Plugin management via `vibectl install plugin plugin-foo-v3.json`
- [ ] Precedence order support like `["plugin-foo-v3", "plugin-foo-v2", "plugin-bar-v3"]`
- [ ] Version compatibility checking for plugins (install time + runtime)
- [ ] WARNING level logging for command failures attributable to custom prompts

## Implementation Components

### 1. Plugin Management System
- [ ] Plugin installation command: `vibectl install plugin <plugin-file>`
- [ ] Plugin file format (JSON) with metadata and prompt definitions
- [ ] Plugin storage location: `~/.config/vibectl/plugins/`
- [ ] Plugin uninstallation, listing, and update capabilities (good to do early)
- [ ] Local file installation support (examples/plugins/ as step 0)
- [ ] Plugin validation before storing (install-time courtesy check)

### 2. Prompt Store (MVP: File-based)
- [ ] File-based prompt store for MVP (punt on SQLite database for now)
- [ ] JSON file storage and management in `~/.config/vibectl/`
- [ ] Prompt resolution with fallback chain using flat keys
- [ ] Version compatibility validation at runtime + install time
- [ ] Flat prompt key mapping (e.g., `"edit_result_summary"` not hierarchical)

### 3. Configuration Integration
- [ ] Plugin precedence configuration (separate from existing config.yaml)
- [ ] Integration with existing vibectl config system
- [ ] Runtime prompt replacement mechanism

### 4. Error Handling and Logging
- [ ] Attribution tracking for custom prompt usage
- [ ] WARNING level logging for custom prompt failures
- [ ] Graceful fallback to default prompts on errors

## MVP Implementation Plan

### Phase 1: Core Infrastructure & Examples
1. Create `examples/plugins/` directory with sample plugin files
2. Design JSON plugin file format specification
3. Implement file-based prompt storage in `~/.config/vibectl/plugins/`
4. Create basic plugin installation command with validation
5. Add configuration support for plugin precedence

### Phase 2: Prompt Integration
1. Define flat prompt key mapping strategy (e.g., `"edit_result_summary"`)
2. Start with `patch_resource_prompt` as proof of concept
3. Implement prompt resolution and replacement mechanism
4. Add error attribution and logging
5. Test with sample plugin from examples/

### Phase 3: Management & Polish
1. Add plugin management commands (list, uninstall, update)
2. Extend to other prompt-using subcommands
3. Comprehensive testing and documentation
4. Performance optimization

## Technical Decisions Made

### Plugin Storage & Configuration
- **Storage location**: `~/.config/vibectl/plugins/` (separate from config.yaml)
- **MVP approach**: File-based storage, no SQLite database initially
- **Configuration**: Separate plugins config, not in existing config.yaml

### Plugin File Format
- **Format**: JSON with plugin metadata and prompt mappings
- **Prompt keys**: Flat structure (e.g., `"edit_result_summary"`) not hierarchical
- **Version compatibility**: Semantic versioning with install + runtime checks

### Installation & Management
- **Install support**: Local files first, examples/plugins/ as step 0
- **Validation**: Install-time validation before storing (courtesy check)
- **Management commands**: List/uninstall/update good to implement early

### Error Attribution
- **Strategy**: Track which prompts came from plugins vs defaults
- **Logging**: WARNING level for failures when custom prompts active
- **Fallback**: Graceful degradation to default prompts

## Technical Decisions to Validate
- Specific JSON schema structure for plugin files
- Exact prompt key naming convention
- Plugin precedence resolution algorithm
- Error attribution implementation strategy

## Success Criteria
- Users can install custom prompt plugins from examples/plugins/
- Custom prompts are used with proper precedence
- Failures are properly attributed and logged
- System degrades gracefully to defaults
- No performance impact on non-plugin users
- Plugin management commands work reliably
