"""
Core logic for truncating various output types (text, logs, JSON, YAML).
"""

import json
import textwrap
from typing import Any

import yaml


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
        return text[:max_length]  # Cannot fit ellipsis reasonably

    # Always use '...' as the ellipsis
    ellipsis = "..."
    ellipsis_len = len(ellipsis)
    remaining = max_length - ellipsis_len
    half_length = remaining // 2
    end_length = remaining - half_length
    if half_length < 0: half_length = 0
    if end_length < 0: end_length = 0

    start = text[:half_length]
    end = text[-end_length:] if end_length > 0 else ""
    result = f"{start}{ellipsis}{end}"
    assert len(result) == max_length, f"Expected length {max_length}, got {len(result)}"
    return result


def find_max_depth(obj: Any, current_depth: int = 0) -> int:
    """Find the maximum depth of a nested data structure."""
    if isinstance(obj, dict):
        if not obj:  # empty dict
            return current_depth
        return max(
            (find_max_depth(value, current_depth + 1) for value in obj.values()),
            default=current_depth # Handle case where dict has no values (shouldn't happen but safe)
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


def truncate_json_like_object(obj: Any, max_depth: int = 3, max_list_len: int = 10) -> Any:
    """Recursively truncate a JSON-like object (dict/list) to a maximum depth/list length.

    Args:
        obj: The dict or list to truncate.
        max_depth: The maximum nesting depth to preserve.
        max_list_len: The maximum number of items to keep in lists (split between start/end).

    Returns:
        A truncated version of the object.
    """
    if not isinstance(obj, dict | list) or max_depth <= 0:
        # Base case: not a dict/list or depth limit reached
        return obj

    if isinstance(obj, dict):
        # Truncate dictionary values recursively
        return {
            k: truncate_json_like_object(v, max_depth - 1, max_list_len)
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        # Truncate list items recursively, handling long lists
        if len(obj) <= max_list_len:
            # List is short enough, truncate items individually
            return [truncate_json_like_object(item, max_depth - 1, max_list_len) for item in obj]
        else:
            # List is too long, keep first and last few items
            if max_list_len < 2: # Need at least 2 to show start/end
                return [{f"... {len(obj)} items truncated ...": ""}]

            half_list_len = max_list_len // 2
            first_items = [
                truncate_json_like_object(item, max_depth - 1, max_list_len)
                for item in obj[:half_list_len]
            ]
            # Ensure we handle odd lengths correctly for the last items slice
            last_items_count = max_list_len - half_list_len
            last_items = [
                truncate_json_like_object(item, max_depth - 1, max_list_len)
                for item in obj[-last_items_count:]
            ]
            # Use a dictionary for the truncation marker instead of a string
            marker = {f"... {len(obj) - max_list_len} more items ...": ""}
            return [*first_items, marker, *last_items] 