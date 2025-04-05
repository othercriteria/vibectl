# Console Management Refactoring

## Changes Made

1. Created a dedicated `console.py` module with a `ConsoleManager` class to handle all console output functionality
   - Added typed methods for different types of output (errors, warnings, notes, etc.)
   - Consolidated duplicate formatting code into reusable methods
   - Improved error handling with dedicated error methods

2. Added helper methods for common tasks:
   - `print_vibe` for displaying vibe check summaries
   - `print_config_table` for displaying configuration details
   - `process_output_for_vibe` to handle token limit processing for LLM inputs

3. Refactored CLI code in `cli.py`:
   - Created a `configure_output_flags` helper to handle common flag configuration logic
   - Updated command handlers to use the ConsoleManager methods
   - Fixed error display in command output
   - Reduced code duplication across command implementations

## Benefits

- **Improved code organization**: Console-related code is now in a single module
- **Reduced duplication**: Common output handling patterns are now in reusable methods
- **Better error messages**: More consistent error handling and formatting
- **Easier maintenance**: Changes to console output only need to be made in one place
- **Type safety**: Added proper type annotations to all methods

## Future Improvements

- Extract common command handling patterns into a shared method
- Create a dedicated output processing module for handling token limits and LLM input preparation
- Add unit tests for the ConsoleManager class
- Potentially add color themes or output styling configuration
