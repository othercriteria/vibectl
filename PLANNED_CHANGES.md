# Planned Changes for feature/plugin-system

## Overview
Implement a plugin system that allows users to replace default prompts with custom ones, providing extensibility and customization capabilities.

## Core Requirements
- [x] User can replace default prompts with custom prompts ✅
- [x] Configurable via config options ✅
- [x] Plugin management via `vibectl install plugin plugin-foo-v3.json` ✅
- [x] Precedence order support like `["plugin-foo-v3", "plugin-foo-v2", "plugin-bar-v3"]` ✅ (COMPLETED)
- [x] Version compatibility checking for plugins (install time) ✅ **RECENTLY COMPLETED**
- [x] Version compatibility checking for plugins (runtime validation) ✅ **RECENTLY COMPLETED**
- [x] WARNING level logging for command failures attributable to custom prompts ✅

## ✅ SUCCESS: Patch Command Plugin Integration

### Implementation Pattern Established
Successfully converted `vibectl patch` to use the plugin system with the following pattern:

1. **Legacy Constant Removal**: Removed `PLAN_PATCH_PROMPT` constant from `vibectl/prompts/patch.py`
2. **Plugin Override Decorators**: Both prompt functions use `@with_plugin_override()`:
   - `patch_plan_prompt()` with key `"patch_plan"`
   - `patch_resource_prompt()` with key `"patch_resource_summary"`
3. **Command Integration**: `vibectl/subcommands/patch_cmd.py` uses functions directly:
   - `plan_prompt_func=patch_plan_prompt` for vibe requests
   - `summary_prompt_func=patch_resource_prompt` for both standard and vibe

### Plugin Keys Established
- **Planning prompts**: `"{command}_plan"` (e.g., `"patch_plan"`)
- **Summary prompts**: `"{command}_resource_summary"` (e.g., `"patch_resource_summary"`)

### Test Updates Required
- Remove legacy constant imports
- Update test assertions to compare function results instead of constants
- All 935 tests passing ✅

## ✅ SUCCESS: Apply Command Plugin Integration (COMPLETED)

### BREAKTHROUGH: Comprehensive Plugin System Implementation
Successfully converted `vibectl apply` to use the plugin system with **ALL 6 prompt override capabilities**:

1. **Complete Plugin Override Integration**: All apply prompt functions now use plugin decorators:
   - `apply_plan_prompt()` with key `"apply_plan"` - main planning (like patch)
   - `apply_output_prompt()` with key `"apply_resource_summary"` - output summarization (like patch)
   - `plan_apply_filescope_prompt_fragments()` with key `"apply_filescope"` - file scoping analysis
   - `summarize_apply_manifest_prompt_fragments()` with key `"apply_manifest_summary"` - manifest summarization
   - `correct_apply_manifest_prompt_fragments()` with key `"apply_manifest_correction"` - manifest correction/generation
   - `plan_final_apply_command_prompt_fragments()` with key `"apply_final_planning"` - final command planning

2. **Legacy Constant Removal**: Removed `PLAN_APPLY_PROMPT` constant, converted to function pattern

3. **Intelligent Apply Workflow Support**: Full plugin system integration for complex multi-stage apply workflow

### Apply Plugin Keys Established (6 Total)
- **Standard prompts** (like patch):
  - `"apply_plan"` - main planning prompt
  - `"apply_resource_summary"` - output summarization
- **Intelligent workflow prompts** (NEW - advanced capabilities):
  - `"apply_filescope"` - file scoping analysis
  - `"apply_manifest_summary"` - manifest summarization
  - `"apply_manifest_correction"` - manifest correction/generation
  - `"apply_final_planning"` - final command planning

### Comprehensive Demo Plugin Created
- **File**: `examples/plugins/apply-comprehensive-demo-v1.json`
- **Coverage**: Demonstrates all 6 plugin override capabilities
- **Features**: Enhanced safety, server-side apply, validation, dependency awareness, security hardening
- **Advanced Capabilities**: Progressive rollout strategies, intelligent orchestration, best practices enforcement

### Technical Achievements
1. **Complex Prompt Function Support**: Successfully handled varied prompt signatures and schema dependencies
2. **Intelligent Workflow Integration**: Plugin system works seamlessly with sophisticated multi-stage apply operations
3. **Production-Ready Enhancements**: Demo plugin shows advanced features like security hardening, dependency ordering, progressive rollouts
4. **Linter Error Resolution**: Fixed trailing comma issue in `command_construction_guidelines_frag`

### Apply Command: Most Advanced Plugin Integration
The apply command now represents the **most sophisticated plugin integration** in vibectl, with 6 different customizable prompt stages compared to patch's 2. This establishes a powerful foundation for complex workflow customization.

## 🎯 Next Target: Auto Command (Alphabetical Order)

### Remaining Commands for Plugin Integration
After successfully completing patch (2 prompts) and apply (6 prompts), continue alphabetically:
- **NEXT: Auto Command** - analyze prompt structure and convert to plugin system
- **Subsequent Commands**: check, cluster_info, create, delete, describe, diff, edit, events, get, logs, memory_update, port_forward, rollout, scale, version, vibe, wait

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
- [x] Version compatibility validation at runtime ✅ **RECENTLY COMPLETED**
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

## ✅ COMPLETED: MVP Implementation + Plugin Precedence + Version Compatibility + First Command Integration

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

### ✅ Phase 5: First Command Integration (PATCH - COMPLETED)
1. [x] Convert patch command to use plugin-enabled prompts ✅
2. [x] Remove legacy constants and update tests ✅
3. [x] Establish standard plugin key naming conventions ✅
4. [x] Validate end-to-end functionality with custom plugins ✅
5. [x] Document implementation pattern for other commands ✅

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

### Version Compatibility ✅ COMPLETED
**Status**: BOTH install-time and runtime checking FULLY IMPLEMENTED ✅
- [x] Install-time version checking ✅ **RECENTLY COMPLETED**
- [x] Runtime version validation ✅ **RECENTLY COMPLETED**
- [x] Semantic versioning enforcement ✅ **RECENTLY COMPLETED**

### Design Enhancements in plugins.py
1. **Runtime Version Compatibility**: Added `_is_plugin_compatible_at_runtime()` method in `PromptResolver` class
2. **Flexible PromptMapping**: Enhanced `PromptMapping` class with dictionary-style access and type detection
3. **Graceful Fallbacks**: Plugin resolution gracefully handles incompatible plugins and falls back to defaults
4. **Plugin Precedence**: Full precedence-based resolution with configurable order

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
1. **Systematic Command Rollout (Alphabetical Order)**:
   - **NEXT: Auto Command** - Analyze prompt structure and convert to plugin system
   - **Subsequent Commands**: check, cluster_info, create, delete, describe, diff, edit, events, get, logs, memory_update, port_forward, rollout, scale, version, vibe, wait

2. **Enhanced Plugin Examples** - create comprehensive plugin examples for each command type as they're converted

3. **Performance Optimization** - minimize overhead for non-plugin users (already achieved for non-plugin scenarios)

## Note on Implementation Status
The plugin system is now highly functional with comprehensive features:
- **Plugin Management**: Full installation, listing, uninstallation, and precedence management
- **Version Compatibility**: Both install-time and runtime validation with semantic versioning
- **Command Integration**: Two commands fully converted (patch with 2 prompts, apply with 6 prompts)
- **Error Handling**: Graceful fallbacks, proper attribution, and warning-level logging
- **Performance**: Zero overhead for non-plugin users, efficient plugin resolution
- **Configuration**: Explicit precedence management replacing filesystem-order dependency

**Major Achievement**: The apply command integration demonstrates the plugin system can handle complex, multi-stage workflows with specialized prompt signatures and schema dependencies. This establishes a robust foundation for converting all remaining vibectl commands.

**Next Priority**: Continue alphabetical rollout starting with the auto command to systematically enable plugin customization across all vibectl functionality.
