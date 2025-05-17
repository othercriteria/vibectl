#!/bin/bash
# Helper script for the autonomous-commits rule to perform pre-commit checks.
# Exits with 0 if all checks pass, 1 otherwise.

echo "Running autonomous commit checks..."

# Check for untracked .mdc files in .cursor/rules
UNTRACKED_RULES=$(git ls-files --others --exclude-standard .cursor/rules/*.mdc)
if [ -n "$UNTRACKED_RULES" ]; then
  echo "Error: Found untracked rule files. Please add them to git first:" >&2
  echo "$UNTRACKED_RULES" >&2
  exit 1
fi
echo "PASSED: No untracked .mdc files in .cursor/rules."

# Check if STRUCTURE.md needs updating
CHANGED_FILES=$(git diff --cached --name-only)
NEEDS_STRUCTURE_UPDATE=false
if echo "$CHANGED_FILES" | grep -qE '^(\.cursor/rules/.*\.mdc|.*\.py|pyproject\.toml|Makefile|flake\.nix)$'; then
  NEEDS_STRUCTURE_UPDATE=true
fi

if [ "$NEEDS_STRUCTURE_UPDATE" = true ] && ! echo "$CHANGED_FILES" | grep -q '^STRUCTURE\.md$'; then
  echo "Error: Structural changes detected but STRUCTURE.md not updated." >&2
  echo "Affected files requiring STRUCTURE.md update:" >&2
  echo "$CHANGED_FILES" | grep -E '^(\.cursor/rules/.*\.mdc|.*\.py|pyproject\.toml|Makefile|flake\.nix)$' >&2
  exit 1
fi
echo "PASSED: STRUCTURE.md check."

# Check if feature changes need CHANGELOG.md updates
# This is a warning, not an error, so it doesn't exit 1.
FEATURE_CHANGES=false
if echo "$CHANGED_FILES" | grep -qvE '^(CHANGELOG\.md|bump_version\.py|pyproject\.toml)$' && echo "$CHANGED_FILES" | grep -qE '\.(py|js|ts|jsx|tsx|css|html|md)$'; then
  FEATURE_CHANGES=true
fi

if [ "$FEATURE_CHANGES" = true ]; then
  if ! echo "$CHANGED_FILES" | grep -q '^CHANGELOG\.md$'; then
    echo "Warning: Feature changes detected but CHANGELOG.md not updated." >&2
    echo "Consider adding your changes to the Unreleased section of CHANGELOG.md" >&2
    echo "See the changelog rule for details." >&2
  fi
fi
echo "INFO: CHANGELOG.md check (warning only)."

# Check for Python files and run coverage test if needed
# This assumes that if pytest-cov is installed, coverage checks are desired here.
# Note: Standard pre-commit hooks might also run pytest.
if echo "$CHANGED_FILES" | grep -qE '\.py$'; then
  if command -v pytest &> /dev/null && python -c "import pytest_cov" &> /dev/null; then
    echo "Checking test coverage via autonomous-commit-checks.sh..."
    if ! python -m pytest --cov; then
      echo "Error: Test coverage check failed (ran from autonomous-commit-checks.sh)." >&2
      echo "Please ensure coverage meets requirements or document exceptions." >&2
      exit 1
    fi
    echo "PASSED: Pytest coverage check."

    UNDOCUMENTED=$(find . -name "*.py" -not -path "./.venv/*" -print0 | xargs -0 grep -H "pragma: no cover" | grep -v " - ")
    if [ -n "$UNDOCUMENTED" ]; then
      echo "Error: Undocumented coverage exclusions found (ran from autonomous-commit-checks.sh):" >&2
      echo "$UNDOCUMENTED" >&2
      echo "Add explanation: # pragma: no cover - [reason for exclusion]" >&2
      exit 1
    fi
    echo "PASSED: Undocumented 'pragma: no cover' check."
  else
    echo "Warning: pytest-cov not found. Skipping coverage check from autonomous-commit-checks.sh." >&2
    echo "Install with: pip install pytest-cov" >&2
  fi
fi
echo "INFO: Python coverage checks (if applicable) completed."

echo "All autonomous commit script checks completed successfully."
exit 0
