# Planned Changes

- Define JSON schema for command-generation LLM output:
  - `commands`: List[str] (kubectl commands to execute)
  - `explanation`: Optional[str] (Textual feedback from LLM)
  - `error`: Optional[str] (Error message, mutually exclusive with commands)
  - `action_type`: Enum["COMMAND", "ERROR", "WAIT", "FEEDBACK"] (Type of response)
  - `wait_duration_seconds`: Optional[int] (Wait time for WAIT action)
- Update LLM prompts in `prompt.py` to request JSON output conforming to the schema.
- Integrate schema usage with `llm` calls in `model_adapter.py` or `command_handler.py` using `--schema`.
- Implement JSON response parsing and handling logic in `command_handler.py` based on `action_type`.
- Add schema validation for received JSON responses.
- Implement fallback mechanism (request JSON in prompt, validate after) for models without native schema support. Add TODO for controlled generation.
- Add tests covering:
  - Schema definition validation
  - Prompt generation with schema requests
  - Response handling for different action types
  - Fallback mechanism behavior
