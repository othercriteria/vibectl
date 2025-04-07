# Cursor Rules

This project uses Cursor rules to maintain consistent development practices.
Rules are stored as `.mdc` files in the `.cursor/rules/` directory.

## What Are Cursor Rules?

Cursor rules are a system for enforcing consistent coding standards, project
organization, and development workflows. They provide automated guidance and
checks that help maintain code quality and project standards.

Each rule:
- Defines specific patterns to match in code or development activities
- Provides suggestions, automated fixes, or rejection messages
- Includes clear examples of correct implementation

## Available Rules

### Code Quality

- **ruff-preferred.mdc**: Enforces the use of ruff as the preferred Python code
  quality tool over other options like black, isort, or flake8.

### Testing

- **dry-test-fixtures.mdc**: Enforces DRY principles in test fixtures and
  promotes fixture reuse.
- **no-llm-in-tests.mdc**: Strictly prohibits unmocked LLM calls in test code to
  ensure fast, deterministic tests.
- **slow-tests.mdc**: Monitors and enforces resolution of slow tests to maintain
  fast test suites.
- **test-coverage.mdc**: Enforces high test coverage standards with documented
  exceptions.

### Documentation

- **project-structure.mdc**: Standards for maintaining project structure
  documentation in STRUCTURE.md.
- **rules.mdc**: Standards for organizing Cursor rule files, ensuring they
  follow consistent patterns and are stored in the correct location.

### Build System

- **no-bazel.mdc**: Prohibits Bazel-related code, recommendations, or tooling in
  favor of Nix.
- **python-venv.mdc**: Python project setup standards for virtual environments.

### Workflow

- **autonomous-commits.mdc**: Defines criteria and behavior for autonomous
  commits, enabling automated code changes while maintaining quality standards.

## Adding New Rules

When creating new rule files:

1. Place them in the `.cursor/rules/` directory with a `.mdc` extension
2. Use kebab-case for filenames (e.g., `new-rule.mdc`)
3. Include proper YAML frontmatter with description, globs, and alwaysApply
4. Structure the rule with clear name, description, filters, and actions
5. Provide examples demonstrating correct usage
6. Avoid project-specific references to ensure reusability

Example rule structure:

```md
---
description: Brief description of the rule
globs: ["**/*.py"]
alwaysApply: true
---
# Rule Title

Brief description of the rule.

<rule>
name: rule_name
description: Detailed description of what the rule enforces

filters:
  # Patterns that trigger the rule
  - type: file_pattern
    pattern: "pattern"

actions:
  # Suggestions and rejections
  - type: suggest
    message: |
      Suggestion message with
      multiple lines

examples:
  # Examples of correct usage
  - input: "Example input"
    output: "Expected output"

metadata:
  priority: high
  version: 1.0
</rule>
```

For more details on specific rules, check the corresponding `.mdc` files in the
`.cursor/rules/` directory.
