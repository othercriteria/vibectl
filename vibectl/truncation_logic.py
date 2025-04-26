"""
Core logic for truncating various output types (text, logs, JSON, YAML).
"""

from typing import Any

# Import YamlSections type


def truncate_string(text: str, max_length: int) -> str:
    """Truncate a string to a maximum length, preserving start and end.

    Args:
        text: The string to truncate
        max_length: Maximum length of the result

    Returns:
        Truncated string that keeps content from beginning and end
    """
    if len(text) <= max_length:
        return text

    if max_length <= 5:
        # If max_length is 5, ellipsis (...) is 3, leaving 2 chars.
        # Cannot split 2 chars for start/end reasonably, so just return start.
        # Handle max_length 0, 1, 2, 3, 4, 5 consistently.
        return text[:max_length]

    # Use '...' as the ellipsis
    ellipsis = "..."
    ellipsis_len = len(ellipsis)
    # Calculate remaining chars available *after* ellipsis
    remaining = max_length - ellipsis_len
    # Split remaining chars for start and end portions
    # Integer division gives floor, favouring start if odd
    half_length = remaining // 2
    # Calculate end length based on start length
    end_length = remaining - half_length

    # Ensure lengths are non-negative (shouldn't happen if max_length > 5)
    start_length = max(0, half_length)
    end_length = max(0, end_length)

    start = text[:start_length]
    end = text[-end_length:] if end_length > 0 else ""
    result = f"{start}{ellipsis}{end}"

    # Assert final length is exactly max_length
    assert len(result) == max_length, (
        f"Expected length {max_length}, got {len(result)} "
        f"(start:{start_length}, end:{end_length})"
    )
    return result


def find_max_depth(obj: Any, current_depth: int = 0) -> int:
    """Find the maximum depth of a nested data structure."""
    if isinstance(obj, dict):
        if not obj:  # empty dict
            return current_depth
        return max(
            (find_max_depth(value, current_depth + 1) for value in obj.values()),
            default=current_depth,  # Handle dicts with no iterable values
        )
    elif isinstance(obj, list):
        if not obj:  # empty list
            return current_depth
        return max(
            (find_max_depth(item, current_depth + 1) for item in obj),
            default=current_depth,
        )
    else:
        return current_depth


def truncate_json_like_object(
    obj: Any, max_depth: int = 3, max_list_len: int = 10
) -> Any:
    """Recursively truncate a JSON-like object (dict/list) to a maximum
    depth/list length.

    Args:
        obj: The dict or list to truncate.
        max_depth: The maximum nesting depth to preserve.
        max_list_len: The maximum number of items to keep in lists
                      (split between start/end).

    Returns:
        A truncated version of the object.
    """

    # Define internal helper function to track current depth
    def _truncate_recursive(item: Any, current_depth: int) -> Any:
        if current_depth >= max_depth:
            # Depth limit reached
            if isinstance(item, dict):
                return {f"... {len(item)} keys truncated ...": ""} if item else {}
            elif isinstance(item, list):
                return [{f"... {len(item)} items truncated ...": ""}] if item else []
            else:
                return item  # Return primitive types as is

        if isinstance(item, dict):
            # Truncate dictionary values recursively
            if not item:
                return {}
            return {
                k: _truncate_recursive(v, current_depth + 1) for k, v in item.items()
            }
        elif isinstance(item, list):
            # Truncate list items recursively, handling long lists
            if not item:
                return []
            if len(item) <= max_list_len:
                # List is short enough, truncate items individually
                return [_truncate_recursive(i, current_depth + 1) for i in item]
            else:
                # List is too long, keep first and last few items
                if max_list_len < 2:  # Need at least 2 to show start/end
                    return [{f"... {len(item)} items truncated ...": ""}]

                half_list_len = max_list_len // 2
                first_items = [
                    _truncate_recursive(i, current_depth + 1)
                    for i in item[:half_list_len]
                ]
                # Ensure we handle odd lengths correctly for the last items slice
                last_items_count = max_list_len - half_list_len
                last_items = [
                    _truncate_recursive(i, current_depth + 1)
                    for i in item[-last_items_count:]
                ]
                # Use a dictionary for the truncation marker instead of a string
                marker = {f"... {len(item) - max_list_len} more items ...": ""}
                return [*first_items, marker, *last_items]
        else:
            # Base case: item is not a dict or list
            return item

    # Start the recursion with initial depth 0
    return _truncate_recursive(obj, 0)


def _truncate_logs_by_lines(
    log_text: str,
    max_lines: int,
    end_ratio: float = 0.6,
) -> str:
    """Truncate log text by keeping start/end lines based purely on ratio.

    Args:
        log_text: The log text to truncate.
        max_lines: The total maximum number of lines to keep.
        end_ratio: The proportion of max_lines to keep from the end (0.0 to 1.0).

    Returns:
        The log text truncated by lines.
    """
    lines = log_text.splitlines()
    num_lines = len(lines)

    if num_lines <= max_lines:
        return log_text  # No line truncation needed

    if max_lines <= 0:
        return "[... Log truncated entirely ...]"

    # Calculate ideal end/start counts based purely on ratio
    # Use round() for potentially more balanced distribution on small numbers
    # Ensure end_lines_count is non-negative
    end_lines_count = max(0, round(max_lines * end_ratio))
    # start_lines_count is now guaranteed non-negative if max_lines is non-negative
    start_lines_count = max_lines - end_lines_count

    # Ensure counts are non-negative and handle cases where max_lines is very small
    if max_lines == 1:
        start_lines_count = 0
        end_lines_count = 1
    elif max_lines == 2:
        # Ensure start and end get at least 1 if possible
        start_lines_count = 1
        end_lines_count = 1

    # Ensure counts do not exceed num_lines (redundant due to initial check, but safe)
    start_lines_count = min(start_lines_count, num_lines)
    end_lines_count = min(end_lines_count, num_lines)

    first_chunk_lines = lines[:start_lines_count]
    # Slice end lines carefully
    end_slice_start = num_lines - end_lines_count  # Correct index calculation
    last_chunk_lines = lines[end_slice_start:] if end_lines_count > 0 else []

    lines_truncated_count = num_lines - len(first_chunk_lines) - len(last_chunk_lines)

    marker = f"[... {lines_truncated_count} lines truncated ...]"

    # Combine parts
    result_parts = []
    if first_chunk_lines:
        result_parts.append("\n".join(first_chunk_lines))
    result_parts.append(marker)
    if last_chunk_lines:
        result_parts.append("\n".join(last_chunk_lines))

    return "\n".join(result_parts)


def _calculate_yaml_overhead(num_sections: int) -> int:
    """Estimate overhead for keys, colons, newlines, indentation in
    reconstructed YAML."""
    # Use double newline for better separation between top-level keys/docs
    # Estimate overhead for keys, colons, newlines, indentation in reconstructed YAML.
    # Rough estimate: key + colon + space + newline + potential indent (2)
    # + inter-section newline
    # Let's estimate ~ 5 chars overhead per key line, plus 2 newlines between sections.
    if num_sections <= 0:
        return 0
    return (num_sections * 5) + (num_sections - 1) * 2
