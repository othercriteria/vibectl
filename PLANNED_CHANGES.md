# Planned Changes for vibectl auto Feature

## New Subcommands

- `vibectl auto`: Implement a new subcommand that reifies the looping `vibectl vibe --yes` pattern currently used in examples
- `vibectl semiauto`: Create a subcommand that acts as sugar for `vibectl auto` but with the `--yes` behavior negated

## Enhanced Confirmation Dialog

Add new choices to the confirmation dialog:
- `yes [A]nd`: Equivalent to `[Y]es` but also allows for a fuzzy memory update within the loop
- `no [B]ut`: Equivalent to `[N]o` but allows for a fuzzy memory update within the loop
- `[E]xit`: Available only in `semiauto` mode to exit the loop more cleanly than Ctrl+C

## Example Updates

- Update the `chaos-monkey` example to use the new `vibectl auto` subcommand
- Leave the `ctf` demo in its current state as it's considered stable and finished

## Implementation Plan

1. Create new command structure for `auto` and `semiauto` subcommands
2. Implement the looping behavior with proper memory handling
3. Enhance the confirmation dialog with new options
4. Update relevant examples to use the new functionality
5. Add documentation and update tests
