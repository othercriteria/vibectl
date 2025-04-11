# Planned Changes: Improved LLM Model Selection and Key Management

This branch aims to improve how `vibectl` manages model selection and API key handling, focusing on immediate pain points while setting the stage for future enhancements. The goal is to provide a more maintainable solution without overengineering.

## Background

Currently, `vibectl` relies on the `llm` package for model access, which has several limitations in production contexts:

1. Key management is isolated within the `llm` package, leading to conflicts with other tools
2. The NixOS module requires complex wrapper scripts to handle key isolation
3. Slow performance when accessing keys through the `llm` CLI
4. No direct support for vibectl-specific key configuration

## Focused Changes (10 commits max)

### 1. Enhanced Configuration Isolation

- Create a dedicated vibectl-specific key configuration section
  - Allow environment variable overrides (`VIBECTL_ANTHROPIC_API_KEY`)
  - Support key file paths (`VIBECTL_ANTHROPIC_API_KEY_FILE`)
  - Keep backward compatibility with existing config
- Add lightweight key validation on startup

### 2. Adapter Pattern for Model Interaction

- Create a simple model adapter interface around `llm` package
  - Abstract model selection and prompt handling
  - Allow future replacement without changing command handlers
- Make adapter compatible with MCP concepts for future migration

### 3. Performance Improvements

- Cache model instances for common operations
- Optimize key loading to avoid slow CLI calls
- Implement direct key file reading when possible

### 4. Better Error Handling

- Add clear error messages for key configuration issues
- Implement simple fallback logic for model selection
- Provide helpful configuration suggestions in error messages

### 5. Module Integration

- Update NixOS module to use new configuration options
- Remove the complex wrapper script in favor of direct configuration
- Add secure key management best practices to documentation

## Implementation Plan

1. Create model adapter interface aligned with MCP concepts
2. Implement dedicated key configuration system
3. Enhance error handling for key and model selection
4. Optimize performance for key operations
5. Update NixOS module to use new system
6. Add tests for new components
7. Document the new key management approach

## Technical Considerations

- Maintain backward compatibility
- Keep code changes minimal and focused
- Use abstractions that align with MCP paradigms
- Follow existing type safety practices
- Limit scope to most valuable improvements

## MCP Compatibility Notes

The [Model Context Protocol](https://github.com/modelcontextprotocol/python-sdk) provides a robust framework for model interaction. While full MCP implementation is out of scope for this work, our adapter pattern will:

1. Use compatible interface concepts (tools, resources, prompts)
2. Structure key management in a way that would support future MCP adoption
3. Keep model interaction isolated behind interfaces that could be replaced
