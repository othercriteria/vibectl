"""
Tests for the core truncation logic in vibectl.truncation_logic.
"""

import pytest
from vibectl import truncation_logic as tl

# --- Tests for truncate_string ---

def test_truncate_string_no_truncation() -> None:
    """Test that strings shorter than or equal to max_length are not truncated."""
    text = "Hello, world!"
    assert tl.truncate_string(text, 20) == text
    assert tl.truncate_string(text, len(text)) == text

def test_truncate_string_truncation() -> None:
    """Test basic string truncation."""
    text = "This is a very long string that needs to be truncated."
    max_length = 30
    truncated = tl.truncate_string(text, max_length)
    assert len(truncated) <= max_length + 1 # Allow for potential newline char in marker
    assert truncated.startswith("This is a ve")
    assert truncated.endswith(" truncated.")
    assert "...\n" in truncated

def test_truncate_string_short_max_length() -> None:
    """Test truncation when max_length is very small."""
    text = "A very long string"
    assert tl.truncate_string(text, 5) == "A ver" # Simple prefix
    assert tl.truncate_string(text, 4) == "A ve"
    assert tl.truncate_string(text, 6) == "...\ng"

def test_truncate_string_exact_limit_calculation() -> None:
    """Test truncation with exact limit calculations."""
    text = "abcdefghijklmnopqrstuvwxyz"
    # max_length = 15, half_length = (15 - 5) // 2 = 5
    expected = "abcde...\nvwxyz"
    assert tl.truncate_string(text, 15) == expected
    assert len(expected) == 14

    # max_length = 16, half_length = (16 - 5) // 2 = 5
    # end_length = 16 - 5 - 5 = 6
    expected_odd = "abcde...\nuvwxyz" # End part gets one extra char (6 chars)
    assert tl.truncate_string(text, 16) == expected_odd
    assert len(expected_odd) == 15

def test_truncate_string_empty() -> None:
    """Test truncation with empty string."""
    assert tl.truncate_string("", 10) == ""

# --- Tests for find_max_depth ---

def test_find_max_depth_simple() -> None:
    """Test finding depth of simple structures."""
    assert tl.find_max_depth(123) == 0
    assert tl.find_max_depth("abc") == 0
    assert tl.find_max_depth([]) == 0
    assert tl.find_max_depth({}) == 0
    assert tl.find_max_depth([1, 2, 3]) == 1
    assert tl.find_max_depth({"a": 1, "b": 2}) == 1

def test_find_max_depth_nested() -> None:
    """Test finding depth of nested structures."""
    assert tl.find_max_depth([1, [2, 3], 4]) == 2
    assert tl.find_max_depth({"a": 1, "b": {"c": 2}}) == 2
    assert tl.find_max_depth({"a": [1, 2], "b": 3}) == 2
    assert tl.find_max_depth([{"a": 1}, {"b": [2, 3]}]) == 3
    assert tl.find_max_depth({"x": {"y": {"z": [1, {"w": 2}]}}}) == 5

def test_find_max_depth_empty_nested() -> None:
    """Test finding depth with empty nested structures."""
    assert tl.find_max_depth([[]]) == 1
    assert tl.find_max_depth([{}]) == 1
    assert tl.find_max_depth({"a": []}) == 1
    assert tl.find_max_depth({"a": {}}) == 1
    assert tl.find_max_depth({"a": {"b": []}}) == 2
    assert tl.find_max_depth([1, {"b": []}, 3]) == 2

def test_find_max_depth_dict_with_no_iterable_values() -> None:
    """Test find_max_depth with a dict whose values don't increase depth."""
    # Although obj.values() wouldn't be empty, the recursive calls might result
    # in max being called on potentially empty generators if values are non-iterable.
    # The 'default' kwarg handles this.
    data = {"a": None, "b": 1, "c": "str"}
    # The depth comes from the dict itself, not its non-dict/list values.
    assert tl.find_max_depth(data) == 1

    # Test edge case: dict with values that yield depth 0
    data_depth_zero = {"a": 1, "b": 2}
    assert tl.find_max_depth(data_depth_zero) == 1

    # Test specifically the default value in max for dicts (though unlikely to hit directly)
    # This structure ensures find_max_depth is called on values, but those values have depth 0
    data_for_default = {"key": [1, 2]} # Depth 2
    assert tl.find_max_depth(data_for_default) == 2
    data_inner_dict = {"key": {"subkey": 1}} # Depth 2
    assert tl.find_max_depth(data_inner_dict) == 2

    # A dict containing only an empty dict
    data_empty_inner = {"a": {}}
    assert tl.find_max_depth(data_empty_inner) == 1 # Depth comes from 'a' holding a dict

    # A dict containing only an empty list
    data_empty_inner_list = {"a": []}
    assert tl.find_max_depth(data_empty_inner_list) == 1 # Depth comes from 'a' holding a list

# --- Tests for truncate_json_like_object ---

def test_truncate_json_like_no_truncation_needed() -> None:
    """Test truncation when object is within limits."""
    obj = {"a": 1, "b": [1, 2]}
    assert tl.truncate_json_like_object(obj, max_depth=3, max_list_len=5) == obj

def test_truncate_json_like_max_depth() -> None:
    """Test truncation based on max_depth."""
    obj = {"l1": {"l2": {"l3": {"l4": "value"}}}}
    truncated = tl.truncate_json_like_object(obj, max_depth=2)
    # Depth 1: l1 exists
    # Depth 2: l2 exists
    # Depth 3: l3 should be truncated (replaced by its value)
    expected = {"l1": {"l2": {"l3": {"l4": "value"}}}} # Base case returns obj
    assert tl.truncate_json_like_object(obj, max_depth=0) == obj # Depth 0, returns original
    assert tl.truncate_json_like_object(obj, max_depth=1) == {'l1': {'l2': {'l3': {'l4': 'value'}}}} # Depth 1, returns l1 obj
    assert tl.truncate_json_like_object(obj, max_depth=2) == {'l1': {'l2': {'l3': {'l4': 'value'}}}} # Depth 2, returns l2 obj
    # Testing actual truncation requires careful expectation setting
    obj_deep = {"a": {"b": {"c": "d"}}}
    assert tl.truncate_json_like_object(obj_deep, max_depth=1) == {"a": {"b": {"c": "d"}}} # Keeps 'a', truncates content of b
    assert tl.truncate_json_like_object(obj_deep, max_depth=2) == {"a": {"b": {"c": "d"}}} # Keeps 'a' and 'b', truncates content of c

    # Let's try a more complex one
    obj_complex = {"a": 1, "b": {"c": 2, "d": {"e": 3}}}
    assert tl.truncate_json_like_object(obj_complex, max_depth=1) == {"a": 1, "b": {"c": 2, "d": {"e": 3}}} # Keeps a, b; truncates c, d contents
    assert tl.truncate_json_like_object(obj_complex, max_depth=2) == {"a": 1, "b": {"c": 2, "d": {"e": 3}}} # Keeps a, b, c, d; truncates e contents

def test_truncate_json_like_max_list_len() -> None:
    """Test truncation based on max_list_len."""
    long_list = list(range(20))
    max_len = 10
    truncated = tl.truncate_json_like_object(long_list, max_depth=5, max_list_len=max_len)
    assert isinstance(truncated, list)
    assert len(truncated) == max_len + 1 # Original items + 1 marker
    half_len = max_len // 2
    last_items_count = max_len - half_len
    assert truncated[:half_len] == long_list[:half_len] # Check first items
    assert truncated[-last_items_count:] == long_list[-last_items_count:] # Check last items
    marker = truncated[half_len]
    assert isinstance(marker, dict)
    assert list(marker.keys())[0] == f"... {len(long_list) - max_len} more items ..."

def test_truncate_json_like_max_list_len_odd() -> None:
    """Test truncation with odd max_list_len."""
    long_list = list(range(21))
    max_len = 9
    truncated = tl.truncate_json_like_object(long_list, max_depth=5, max_list_len=max_len)
    assert len(truncated) == max_len + 1
    half_len = max_len // 2 # 4
    last_items_count = max_len - half_len # 5
    assert truncated[:half_len] == long_list[:half_len]
    assert truncated[-last_items_count:] == long_list[-last_items_count:]
    marker = truncated[half_len]
    assert list(marker.keys())[0] == f"... {len(long_list) - max_len} more items ..."


def test_truncate_json_like_max_list_len_small() -> None:
    """Test truncation when max_list_len is very small."""
    long_list = list(range(10))
    truncated_1 = tl.truncate_json_like_object(long_list, max_list_len=1)
    assert len(truncated_1) == 1
    assert isinstance(truncated_1[0], dict)
    assert list(truncated_1[0].keys())[0] == "... 10 items truncated ..."

    truncated_0 = tl.truncate_json_like_object(long_list, max_list_len=0)
    assert len(truncated_0) == 1
    assert isinstance(truncated_0[0], dict)
    assert list(truncated_0[0].keys())[0] == "... 10 items truncated ..."

def test_truncate_json_like_nested_list_depth() -> None:
    """Test truncation of nested lists combined with depth limit."""
    obj = {"a": [1, [2, [3, [4, 5]]]]}
    # Depth 1: Keep 'a'
    # Depth 2: Keep outer list [1, [...]]
    # Depth 3: Keep inner list [2, [...]]
    # Depth 4: Keep inner list [3, [...]] - this should be truncated value
    truncated = tl.truncate_json_like_object(obj, max_depth=3)
    expected = {"a": [1, [2, [3, [4, 5]]]]} # Depth 3 should keep list [3, [...]] but truncate its content
    assert truncated == expected

    truncated_depth_2 = tl.truncate_json_like_object(obj, max_depth=2)
    expected_depth_2 = {"a": [1, [2, [3, [4, 5]]]]} # Depth 2 keeps outer list, truncates content of [2, [...]]
    assert truncated_depth_2 == expected_depth_2


def test_truncate_json_like_mixed() -> None:
    """Test truncation with mixed depth and list length limits."""
    obj = {
        "deep_dict": {"l1": {"l2": {"l3": "value"}}},
        "long_list": list(range(30)),
        "nested_list": [1, 2, [3, 4, list(range(15))]],
    }
    truncated = tl.truncate_json_like_object(obj, max_depth=2, max_list_len=8)

    # Check deep_dict truncation (depth=2)
    assert "deep_dict" in truncated
    assert "l1" in truncated["deep_dict"]
    assert "l2" in truncated["deep_dict"]["l1"]
    # Content of l2 should be truncated
    assert truncated["deep_dict"]["l1"]["l2"] == {"l3": "value"}

    # Check long_list truncation (len=8)
    assert "long_list" in truncated
    assert len(truncated["long_list"]) == 8 + 1 # 8 items + marker
    assert truncated["long_list"][:4] == [0, 1, 2, 3]
    assert truncated["long_list"][-4:] == [26, 27, 28, 29]
    assert "... 22 more items ..." in truncated["long_list"][4]

    # Check nested_list truncation (depth=2 applies first)
    assert "nested_list" in truncated
    # Depth 1 keeps the outer list
    # Depth 2 keeps items 1, 2 and the inner list [3, 4, [...]]
    # Depth 2 means content of inner list [3, 4, [...]] is truncated
    assert truncated["nested_list"][0] == 1
    assert truncated["nested_list"][1] == 2
    inner_list_trunc = truncated["nested_list"][2]
    assert inner_list_trunc == [3, 4, list(range(15))] # Content truncated by depth

def test_truncate_non_dict_list() -> None:
    """Test that non-dict/list objects are returned as is."""
    assert tl.truncate_json_like_object(123) == 123
    assert tl.truncate_json_like_object("string") == "string"
    assert tl.truncate_json_like_object(None) is None 