#!/bin/bash
# Helper script for the commit-message rule to format and execute a git commit.

# Arguments:
# $1: type
# $2: concise description
# $3: detailed description (can be multi-line, "None" if not provided)
# $4: breaking changes (can be multi-line, "None" if not provided)
# $5: related issues/tickets (can be multi-line, "None" if not provided)

COMMIT_TYPE="$1"
CONCISE_DESCRIPTION="$2"
DETAILED_DESCRIPTION="$3"
BREAKING_CHANGES="$4"
RELATED_ISSUES="$5"

echo "Verifying changes for commit (format-and-commit.sh)..."
CHANGED_FILES=$(git diff --cached --name-only)

if [ -z "$CHANGED_FILES" ]; then
  echo "Error: No files staged for commit. Use git add to stage changes." >&2
  exit 1
fi

echo "Files to be committed:" >&2
echo "$CHANGED_FILES" >&2
echo "" >&2
echo "Summary of changes:" >&2
git diff --cached --stat >&2
echo "" >&2

# Function to process multi-line message parts into -m arguments
create_m_args() {
  local input_str="$1"
  local current_args=""

  # Skip if empty or literally "None"
  if [[ -z "$input_str" || "$input_str" == "None" ]]; then
    echo ""
    return
  fi

  # Use a temporary file for line-by-line processing to handle newlines correctly
  local tmpfile_args
  tmpfile_args=$(mktemp)
  # Use printf to preserve newlines from the input string when writing to tmpfile
  printf "%s" "$input_str" > "$tmpfile_args"

  while IFS= read -r line; do
    # Escape double quotes within the line for the -m argument
    line_escaped=$(echo "$line" | sed 's/\"/\\\"/g')
    current_args="$current_args -m \"$line_escaped\""
  done < "$tmpfile_args"

  rm "$tmpfile_args"
  echo "$current_args"
}

CONCISE_ARG="-m \"$COMMIT_TYPE: $CONCISE_DESCRIPTION\""
DESCRIPTION_ARGS=$(create_m_args "$DETAILED_DESCRIPTION")

BREAKING_HEADER=""
BREAKING_ARGS=""
if [[ -n "$BREAKING_CHANGES" && "$BREAKING_CHANGES" != "None" ]]; then
  BREAKING_HEADER="-m \"\" -m \"Breaking Changes:\""
  BREAKING_ARGS=$(create_m_args "$BREAKING_CHANGES")
fi

ISSUES_HEADER=""
ISSUES_ARGS=""
if [[ -n "$RELATED_ISSUES" && "$RELATED_ISSUES" != "None" ]]; then
  ISSUES_HEADER="-m \"\" -m \"Related Issues:\""
  ISSUES_ARGS=$(create_m_args "$RELATED_ISSUES")
fi

# Construct the final git commit command with all arguments
# Ensure that args are correctly expanded and quoted using eval
echo "Executing: git commit $CONCISE_ARG $DESCRIPTION_ARGS $BREAKING_HEADER $BREAKING_ARGS $ISSUES_HEADER $ISSUES_ARGS" >&2
eval git commit "$CONCISE_ARG" "$DESCRIPTION_ARGS" "$BREAKING_HEADER" "$BREAKING_ARGS" "$ISSUES_HEADER" "$ISSUES_ARGS"
