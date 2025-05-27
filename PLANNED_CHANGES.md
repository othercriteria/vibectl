# Planned Changes for feature/plugin-system

## Overview
Implement a plugin system that allows users to replace default prompts with custom ones, providing extensibility and customization capabilities.

## Core Requirements
- [x] User can replace default prompts with custom prompts ✅
- [x] Configurable via config options ✅
- [x] Plugin management via `vibectl install plugin plugin-foo-v3.json` ✅
- [x] Precedence order support like `["plugin-foo-v3", "plugin-foo-v2", "plugin-bar-v3"]` ✅ (COMPLETED)
- [ ] Version compatibility checking for plugins (install time + runtime)
- [x] WARNING level logging for command failures attributable to custom prompts ✅

## Implementation Components

### 1. Plugin Management System ✅ COMPLETED
- [x] Plugin installation command: `vibectl install plugin <plugin-file>` ✅
- [x] Plugin file format (JSON) with metadata and prompt definitions ✅
- [x] Plugin storage location: `~/.config/vibectl/plugins/` ✅
- [x] Plugin listing capabilities: `vibectl plugin list` ✅
- [ ] Plugin uninstallation and update capabilities
- [x] Local file installation support (examples/plugins/ as step 0) ✅
- [x] Plugin validation before storing (install-time courtesy check) ✅

### 2. Prompt Store (MVP: File-based) ✅ COMPLETED
- [x] File-based prompt store for MVP ✅
- [x] JSON file storage and management in `~/.config/vibectl/` ✅
- [x] Prompt resolution with fallback chain using flat keys ✅
- [ ] Version compatibility validation at runtime + install time
- [x] Flat prompt key mapping (e.g., `"patch_resource_summary"`) ✅

### 3. Configuration Integration ✅ COMPLETED
- [x] Plugin precedence configuration system ✅ (COMPLETED)
- [x] Integration with existing vibectl config system ✅
- [x] Runtime prompt replacement mechanism ✅
- [x] Plugin precedence CLI commands (`vibectl plugin precedence list/set/add/remove`) ✅

### 4. Error Handling and Logging ✅ COMPLETED
- [x] Attribution tracking for custom prompt usage ✅
- [x] WARNING level logging for custom prompt failures ✅
- [x] Graceful fallback to default prompts on errors ✅

## ✅ COMPLETED: MVP Implementation + Plugin Precedence

### ✅ Phase 1: Core Infrastructure & Examples
1. [x] Create `examples/plugins/` directory with sample plugin files ✅
2. [x] Design JSON plugin file format specification ✅
3. [x] Implement file-based prompt storage in `~/.config/vibectl/plugins/` ✅
4. [x] Create basic plugin installation command with validation ✅
5. [x] Add configuration support for plugin precedence ✅

### ✅ Phase 2: Prompt Integration
1. [x] Define flat prompt key mapping strategy (e.g., `"patch_resource_summary"`) ✅
2. [x] Start with `patch_resource_prompt` as proof of concept ✅
3. [x] Implement prompt resolution and replacement mechanism ✅
4. [x] Add error attribution and logging ✅
5. [x] Test with sample plugin from examples/ ✅

### ✅ Phase 3: Plugin Precedence System (COMPLETED)
1. [x] Add plugin precedence management commands ✅
2. [x] Implement explicit precedence configuration ✅
3. [x] Fix config system list handling bug ✅
4. [x] Fix asyncclick import compatibility issue ✅
5. [x] Complete plugin precedence CLI interface ✅

### 🚧 Phase 4: Management & Polish (REMAINING)
1. [ ] Add plugin management commands (uninstall, update) - list is done ✅
2. [ ] Extend to other prompt-using subcommands (patch working ✅)
3. [ ] Comprehensive testing and documentation
4. [ ] Performance optimization

## ✅ RECENTLY COMPLETED FIXES

### Plugin Precedence Configuration System ✅ (COMPLETED)
**Status**: FULLY IMPLEMENTED AND WORKING
- **Fixed**: Config system list handling bug where list values were stored as individual characters
- **Fixed**: AsyncClick import compatibility issue in plugin_cmd.py
- **Implemented**: Complete CLI interface for precedence management:
  - `vibectl plugin precedence list` - show current precedence order
  - `vibectl plugin precedence set plugin1 plugin2 ...` - set precedence order
  - `vibectl plugin precedence add plugin [--position N]` - add plugin to precedence
  - `vibectl plugin precedence remove plugin` - remove plugin from precedence
- **Working**: Explicit precedence configuration via `plugin_precedence` config key
- **Working**: Ordered resolution respects configured precedence

### Technical Fixes Applied
1. **Config System List Handling**: Fixed `Config.set()` method to properly handle list types without converting them to string representations first
2. **AsyncClick Compatibility**: Updated plugin_cmd.py to use `import asyncclick as click` to match the main CLI pattern
3. **Type Conversion**: Added `_convert_to_list()` method to properly parse list values from strings when needed

## ❓ Outstanding Questions

### Version Compatibility
**Status**: Not yet implemented
- Install-time version checking
- Runtime version validation
- Semantic versioning enforcement

## 🎉 SUCCESS ACHIEVED
- [x] Users can install custom prompt plugins from examples/plugins/ ✅
- [x] Custom prompts are used with proper precedence ✅ (working with explicit precedence)
- [x] Plugin precedence is fully configurable and manageable ✅
- [x] Failures are properly attributed and logged ✅
- [x] System degrades gracefully to defaults ✅
- [x] No performance impact on non-plugin users ✅
- [x] Plugin management commands work reliably ✅ (list, precedence management working)

## Next Steps
1. **Add version compatibility checking**
2. **Complete plugin management** (uninstall, update commands)
3. **Extend to other subcommands** beyond patch
4. **Add comprehensive testing**

## Note on Implementation Status
The plugin precedence system is now fully functional. The original undefined behavior (where precedence depended on filesystem order) has been replaced with explicit configuration-based precedence that users can control via the CLI commands.
