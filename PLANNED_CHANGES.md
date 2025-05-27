# Planned Changes for feature/plugin-system

## Overview
Implement a plugin system that allows users to replace default prompts with custom ones, providing extensibility and customization capabilities.

## Core Requirements
- [x] User can replace default prompts with custom prompts ✅
- [x] Configurable via config options ✅
- [x] Plugin management via `vibectl install plugin plugin-foo-v3.json` ✅
- [x] Precedence order support like `["plugin-foo-v3", "plugin-foo-v2", "plugin-bar-v3"]` ✅ (COMPLETED)
- [x] Version compatibility checking for plugins (install time) ✅ **RECENTLY COMPLETED**
- [ ] Version compatibility checking for plugins (runtime validation)
- [x] WARNING level logging for command failures attributable to custom prompts ✅

## Implementation Components

### 1. Plugin Management System ✅ COMPLETED
- [x] Plugin installation command: `vibectl install plugin <plugin-file>` ✅
- [x] Plugin file format (JSON) with metadata and prompt definitions ✅
- [x] Plugin storage location: `~/.config/vibectl/plugins/` ✅
- [x] Plugin listing capabilities: `vibectl plugin list` ✅
- [x] Plugin uninstallation and update capabilities ✅ **IMPLEMENTED**
- [x] Local file installation support (examples/plugins/ as step 0) ✅
- [x] Plugin validation before storing (install-time courtesy check) ✅

### 2. Prompt Store (MVP: File-based) ✅ COMPLETED
- [x] File-based prompt store for MVP ✅
- [x] JSON file storage and management in `~/.config/vibectl/` ✅
- [x] Prompt resolution with fallback chain using flat keys ✅
- [x] Version compatibility validation at install time ✅ **RECENTLY COMPLETED**
- [ ] Version compatibility validation at runtime
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

## ✅ COMPLETED: MVP Implementation + Plugin Precedence + Version Compatibility

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

### ✅ Phase 4: Version Compatibility System (RECENTLY COMPLETED)
1. [x] Implement semantic versioning support with operators (>=, <=, >, <, ==, !=) ✅
2. [x] Add install-time version compatibility checking ✅
3. [x] Create comprehensive version parsing and comparison logic ✅
4. [x] Integrate version validation into plugin installation process ✅
5. [x] Add 19 comprehensive test cases covering all version scenarios ✅

### 🚧 Phase 5: Management & Polish (REMAINING)
1. [x] Add plugin management commands (uninstall, update) ✅ **IMPLEMENTED** - list was already done ✅
2. [ ] Add runtime version compatibility validation
3. [ ] Extend to other prompt-using subcommands (patch working ✅)
4. [ ] Comprehensive testing and documentation
5. [ ] Performance optimization

## ✅ RECENTLY COMPLETED FIXES

### Version Compatibility System ✅ (RECENTLY COMPLETED)
**Status**: INSTALL-TIME CHECKING FULLY IMPLEMENTED
- **Implemented**: `vibectl/version_compat.py` module with comprehensive version handling
- **Implemented**: Semantic versioning support with operators: `>=`, `<=`, `>`, `<`, `==`, `!=`
- **Implemented**: Version parsing for variable-length versions (1.0, 1.0.0, 1.2.3.4)
- **Implemented**: Version normalization for different-length version comparisons
- **Implemented**: Integration with `PluginStore._validate_plugin()` for install-time checks
- **Implemented**: 19 comprehensive test cases covering all functionality
- **Working**: Install-time validation prevents incompatible plugin installation
- **Current Version**: Validates against vibectl 0.8.7

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
4. **Version Compatibility**: Added robust semantic versioning with comprehensive test coverage

## ❓ Outstanding Questions

### Version Compatibility
**Status**: Install-time checking IMPLEMENTED ✅, Runtime validation pending
- [x] Install-time version checking ✅ **RECENTLY COMPLETED**
- [ ] Runtime version validation
- [x] Semantic versioning enforcement ✅ **RECENTLY COMPLETED**

## 🎉 SUCCESS ACHIEVED
- [x] Users can install custom prompt plugins from examples/plugins/ ✅
- [x] Custom prompts are used with proper precedence ✅ (working with explicit precedence)
- [x] Plugin precedence is fully configurable and manageable ✅
- [x] Install-time version compatibility checking prevents incompatible plugins ✅ **NEW**
- [x] Failures are properly attributed and logged ✅
- [x] System degrades gracefully to defaults ✅
- [x] No performance impact on non-plugin users ✅
- [x] Plugin management commands work reliably ✅ (install, list, uninstall, update, precedence management working)

## Next Steps
1. **Add runtime version compatibility validation**
2. **Extend to other subcommands** beyond patch
3. **Add comprehensive testing**

## Note on Implementation Status
The plugin system is now highly functional with both precedence management and install-time version compatibility checking. The original undefined behavior (where precedence depended on filesystem order) has been replaced with explicit configuration-based precedence that users can control via CLI commands. Version compatibility ensures only compatible plugins can be installed, preventing runtime errors from version mismatches.
