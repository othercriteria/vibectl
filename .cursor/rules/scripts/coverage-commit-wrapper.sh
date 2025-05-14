#!/bin/bash
# Helper script for the test-coverage rule.
# Performs coverage checks and then executes git commit with passthrough arguments.

# Check coverage before committing
if [[ "$(git diff --cached --name-only)" =~ \\.py$ ]]; then
  echo "Checking test coverage (via coverage-commit-wrapper.sh)..."

  # Run coverage check using pytest-cov
  if ! python -m pytest --cov; then
    echo "Error: Test coverage check failed (ran from coverage-commit-wrapper.sh)." >&2
    echo "Please ensure coverage meets requirements or document exceptions." >&2
    exit 1
  fi
  echo "PASSED: Pytest coverage check."

  # Verify all coverage exclusions are documented
  UNDOCUMENTED=$(grep -r "pragma: no cover" --include="*.py" . | grep -v " - ")
  if [ -n "$UNDOCUMENTED" ]; then
    echo "Error: Undocumented coverage exclusions found (ran from coverage-commit-wrapper.sh):" >&2
    echo "$UNDOCUMENTED" >&2
    echo "Add explanation: # pragma: no cover - [reason for exclusion]" >&2
    exit 1
  fi
  echo "PASSED: Undocumented 'pragma: no cover' check."
else
  echo "No Python files in commit, skipping coverage check (via coverage-commit-wrapper.sh)."
fi

# Continue with regular commit if checks pass, passing through all arguments
# received by this script to git commit.
echo "Proceeding with commit (via coverage-commit-wrapper.sh)..." >&2
git commit "$@"
