# Planned Changes for Apply and Diff Subcommands

## Kubectl Apply Subcommand
- Implement basic `vibectl apply -f <filename>` functionality.
- Handle YAML/JSON file inputs.
- Integrate with `vibe` for planning, summarization, and input fixing.
- LLM-powered 'fix' mode for invalid/incomplete input files (configurable).
  - Fixes can range from typo correction to generating manifests from descriptions.
  - Operates on a per-file basis.
- Add tests for common use cases.

## Shared Functionality
- Develop common utilities for file handling and resource parsing.
- Ensure consistent error handling and reporting.
