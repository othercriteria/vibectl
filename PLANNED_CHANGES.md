# Planned Changes: Basic Logging Features for vibectl

## Goals
- Add basic logging to vibectl to improve observability and debugging.
- Ensure logs are structured and configurable (level, output).
- Integrate logging with existing CLI commands and error handling.

## Tasks
- [x] Decide on logging library (Python standard logging)
- [x] Add logger initialization to main entry point (`init_logging` in logutil.py, called from cli.py)
- [x] Make log level configurable via CLI flag or environment variable (supports config and VIBECTL_LOG_LEVEL)
- [x] Implement a custom logging.Handler that forwards WARNING and ERROR logs to console_manager for user visibility
- [x] Add tests to verify logging output and error reporting (see test_logging.py, test_standard_command.py)
- [x] Ensure normal operation only shows user-facing messages; verbose/debug mode can surface more logs (future extension planned)
- [x] Do not duplicate messages between logger and console_manager unless in debug/verbose mode (handler logic prevents duplication)
- [x] Allow user to control log verbosity (config/env/CLI flag)
- [ ] Add logging to key operations (start, stop, errors, etc.) in all subcommands
- [ ] Update documentation to describe logging usage (README, CLI help)

### Subcommand Migration Progress
- [x] Moved and updated: `just` (subcommands/just_cmd.py)
- [x] Moved and updated: `wait` (subcommands/wait_cmd.py)
- [x] Moved and updated: `get` (subcommands/get_cmd.py)
- [ ] Remaining: migrate and update logging for other subcommands (list here as you go)

## Next Steps / Foundational Changes
- [ ] Add global CLI `--log-level` and `--verbose` flags to control logging level and verbosity for all commands
- [ ] Ensure all error and exception paths consistently use logging (not just console_manager)
- [ ] Consider if any additional shared logging utilities or patterns are needed before migrating more subcommands (e.g., context-aware log formatting, per-command loggers, etc.)
- [ ] Plan for future extensibility (file logging, JSON logs, etc.) but keep current implementation simple

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
