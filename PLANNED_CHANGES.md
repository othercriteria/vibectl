# Planned Changes: Basic Logging Features for vibectl

## Goals
- Add basic logging to vibectl to improve observability and debugging.
- Ensure logs are structured and configurable (level, output).
- Integrate logging with existing CLI commands and error handling.

## Tasks
- [ ] Decide on logging library (likely Python standard logging)
- [ ] Add logger initialization to main entry point
- [ ] Add logging to key operations (start, stop, errors, etc.)
- [ ] Make log level configurable via CLI flag or environment variable
- [ ] Add tests to verify logging output and error reporting
- [ ] Update documentation to describe logging usage
- [ ] Implement a custom logging.Handler that forwards WARNING and ERROR logs to console_manager for user visibility
- [ ] Ensure normal operation only shows user-facing messages; verbose/debug mode can surface more logs
- [ ] Do not duplicate messages between logger and console_manager unless in debug/verbose mode
- [ ] Allow user to control log verbosity (config/env/CLI flag)

## Considerations
- Keep logging and console_manager separate for clean architecture
- Use a logging handler to bridge logs to user output when appropriate
- Only surface logs to users when relevant (warnings/errors, or if verbose/debug enabled)
- Keep logging simple and non-intrusive for users
- Avoid logging sensitive data
- Ensure logging does not break existing CLI output
- Plan for future extensibility (e.g., file logging, JSON logs)

## Logging Test Pattern (2024-05-xx)

When testing logging output in command handler or other modules:
- Use the `mock_command_handler_logger` fixture (from conftest.py) to patch and assert on log output.
- This ensures fast, reliable, and consistent logging assertions.
- For new modules, add a similar fixture to conftest.py and use it in tests.

Example usage:
```python
# In your test function signature:
def test_something(..., mock_command_handler_logger: Mock):
    ...
    # After running code
    assert any("expected log message" in str(call) for call in mock_command_handler_logger.info.call_args_list)
```
