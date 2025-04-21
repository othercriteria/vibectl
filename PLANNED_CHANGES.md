# Planned Changes for vibectl auto Feature

## New Subcommands

- `vibectl auto`: Implement a new subcommand that reifies the looping `vibectl vibe --yes` pattern currently used in examples
- `vibectl semiauto`: Create a subcommand that acts as sugar for `vibectl auto` but with the `--yes` behavior negated

## Configuration Options and Flags

- Add `--limit <n>` flag to `auto` and `semiauto` to limit the number of iterations
- Add `show_memory` config option (default: false) to control displaying memory before each iteration
- Add `show_iterations` config option (default: false) to display iteration count and limit information

## Enhanced Confirmation Dialog

Add new choices to the confirmation dialog:
- `yes [A]nd`: Equivalent to `[Y]es` but also allows for a fuzzy memory update within the loop
- `no [B]ut`: Equivalent to `[N]o` but allows for a fuzzy memory update within the loop
- `[E]xit`: Available only in `semiauto` mode to exit the loop more cleanly than Ctrl+C
- `[M]emory`: View current memory content and show the confirmation dialog again

## Example Updates

- Update the `chaos-monkey` example to use the new `vibectl auto` subcommand:
  - Remove the existing while loop, as `auto` handles looping
  - Set appropriate config options (show_memory, show_iterations)
  - Use the `--limit` flag for initial exploration before adding playbook
- Leave the `ctf` demo in its current state as it's considered stable and finished

## Implementation Plan

1. Create new command structure for `auto` and `semiauto` subcommands
2. Implement the looping behavior with proper memory handling
3. Add the iteration limit option and tracking
4. Implement show_memory and show_iterations configuration options
5. Enhance the confirmation dialog with new options
6. Update chaos-monkey example to use the new functionality
7. Add documentation and update tests
