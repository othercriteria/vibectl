"""
Tests for the core truncation logic in vibectl.truncation_logic.
"""

import pytest

from vibectl import truncation_logic as tl

# Import the type needed for YAML section tests

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
    assert len(truncated) <= max_length  # Should be exactly max_length if truncated
    assert truncated.startswith("This is a ve")
    assert truncated.endswith(" be truncated.")  # Updated end
    assert "..." in truncated
    # assert "...\n" in truncated # Incorrect check removed/commented


def test_truncate_string_short_max_length() -> None:
    """Test truncation when max_length is very small."""
    text = "A very long string"
    # Marker is "..." (len 3)
    # When max_length <= 3, it should just return prefix
    assert tl.truncate_string(text, 3) == "A v"
    assert tl.truncate_string(text, 2) == "A "
    # max_length=4 is <= 5, should return prefix text[:4]
    assert tl.truncate_string(text, 4) == "A ve"
    # max=5 is <= 5, should return prefix text[:5]
    assert tl.truncate_string(text, 5) == "A ver"
    # max=6 is > 5:
    # half=(6-3)//2=1, end=6-1-3=2 -> text[:1]+"..."+text[-2:] = "A...ng"
    expected_6 = "A...ng"
    assert tl.truncate_string(text, 6) == expected_6
    assert len(expected_6) == 1 + 3 + 2  # start + marker + end = 6


def test_truncate_string_exact_limit_calculation() -> None:
    """Test truncation with exact limit calculations."""
    text = "abcdefghijklmnopqrstuvwxyz"
    marker = "..."
    marker_len = len(marker)  # 3

    # max_length = 15: half=(15-3)//2=6, end=15-6-3=6
    expected_15 = "abcdef...uvwxyz"
    assert tl.truncate_string(text, 15) == expected_15
    assert len(expected_15) == 6 + marker_len + 6  # 15

    # max_length = 16: half=(16-3)//2=6, end=16-6-3=7
    expected_16 = "abcdef...tuvwxyz"
    assert tl.truncate_string(text, 16) == expected_16
    assert len(expected_16) == 6 + marker_len + 7  # 16


def test_truncate_string_empty() -> None:
    """Test truncation with empty string."""
    assert tl.truncate_string("", 10) == ""


def test_truncate_string_basic() -> None:
    """Test basic string truncation."""
    text = "abcdefghijklmnopqrstuvwxyz"
    # For max_length=10, remaining=7, start=3, end=4. End should be 'wxyz'.
    assert tl.truncate_string(text, 10) == "abc...wxyz"
    assert len(tl.truncate_string(text, 10)) == 10


def test_truncate_string_short() -> None:
    """Test truncation when string is shorter than max length."""
    text = "short"
    assert tl.truncate_string(text, 10) == "short"


def test_truncate_string_exact() -> None:
    """Test truncation when string is exactly max length."""
    text = "exactlength"
    assert tl.truncate_string(text, 11) == "exactlength"


def test_truncate_string_very_short_limit() -> None:
    """Test truncation with a limit too small for ellipsis."""
    text = "abcdefghijklmnopqrstuvwxyz"
    assert tl.truncate_string(text, 3) == "abc"
    assert tl.truncate_string(text, 5) == "abcde"  # Limit 5 can't fit '...'


def test_truncate_string_odd_limit() -> None:
    """Test truncation with an odd max length."""
    text = "abcdefghijklmnopqrstuvwxyz"
    truncated = tl.truncate_string(text, 11)  # 11 - 3 = 8. 4 start, 4 end.
    assert truncated == "abcd...wxyz"
    assert len(truncated) == 11

    truncated_odd = tl.truncate_string(text, 9)  # 9 - 3 = 6. 3 start, 3 end.
    assert truncated_odd == "abc...xyz"
    assert len(truncated_odd) == 9


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

    # Test specifically the default value in max for dicts (though unlikely
    # to hit directly)
    # This structure ensures find_max_depth is called on values, but those
    # values have depth 0
    data_for_default = {"key": [1, 2]}  # Depth 2
    assert tl.find_max_depth(data_for_default) == 2

    # A dict containing only an empty dict
    data_empty_inner: dict[str, dict] = {"a": {}}
    # Depth comes from 'a' holding a dict
    assert tl.find_max_depth(data_empty_inner) == 1

    # A dict containing only an empty list
    data_empty_inner_list: dict[str, list] = {"a": []}
    # Depth comes from 'a' holding a list
    assert tl.find_max_depth(data_empty_inner_list) == 1


def test_find_max_depth_basic() -> None:
    """Test finding max depth in nested structures."""
    assert tl.find_max_depth(1) == 0
    assert tl.find_max_depth("string") == 0
    assert tl.find_max_depth([]) == 0
    assert tl.find_max_depth({}) == 0
    assert tl.find_max_depth([1, 2, 3]) == 1
    assert tl.find_max_depth({"a": 1, "b": 2}) == 1
    assert tl.find_max_depth({"a": [1, 2]}) == 2
    assert tl.find_max_depth([{"a": 1}]) == 2
    assert tl.find_max_depth({"a": {"b": {"c": 3}}}) == 3
    assert tl.find_max_depth([[[1]]]) == 3


# --- Tests for truncate_json_like_object ---


def test_truncate_json_like_no_truncation_needed() -> None:
    """Test truncation when object is within limits."""
    obj = {"a": 1, "b": [1, 2]}
    assert tl.truncate_json_like_object(obj, max_depth=3, max_list_len=5) == obj


def test_truncate_json_like_max_depth() -> None:
    """Test truncation based on max_depth."""
    obj = {"l1": {"l2": {"l3": {"l4": "value"}}}}
    # Depth 0: Truncates immediately
    assert tl.truncate_json_like_object(obj, max_depth=0) == {
        "... 1 keys truncated ...": ""
    }
    # Depth 1: Keeps l1, truncates its content (l2 dict)
    assert tl.truncate_json_like_object(obj, max_depth=1) == {
        "l1": {"... 1 keys truncated ...": ""}
    }
    # Depth 2: Keeps l1, l2, truncates content of l2 (l3 dict)
    assert tl.truncate_json_like_object(obj, max_depth=2) == {
        "l1": {"l2": {"... 1 keys truncated ...": ""}}
    }
    # Depth 3: Keeps l1, l2, l3, truncates content of l3 (l4 string)
    assert tl.truncate_json_like_object(obj, max_depth=3) == {
        "l1": {"l2": {"l3": {"... 1 keys truncated ...": ""}}}
    }
    # Depth 4: Keeps all levels, truncates the final value 'value'
    # (which is primitive, so kept as is)
    assert tl.truncate_json_like_object(obj, max_depth=4) == {
        "l1": {"l2": {"l3": {"l4": "value"}}}
    }
    # Depth 5 (more than needed): Keeps everything
    assert tl.truncate_json_like_object(obj, max_depth=5) == obj

    # Testing actual truncation requires careful expectation setting
    obj_deep = {"a": {"b": {"c": "d"}}}
    assert tl.truncate_json_like_object(obj_deep, max_depth=1) == {
        "a": {"... 1 keys truncated ...": ""}
    }
    assert tl.truncate_json_like_object(obj_deep, max_depth=2) == {
        "a": {"b": {"... 1 keys truncated ...": ""}}
    }
    assert tl.truncate_json_like_object(obj_deep, max_depth=3) == {
        "a": {"b": {"c": "d"}}
    }

    # Let's try a more complex one
    obj_complex = {"a": 1, "b": {"c": 2, "d": {"e": 3}}}
    # Depth 1: Keeps a, b; truncates c, d contents
    # (primitives, so kept); truncates e content
    assert tl.truncate_json_like_object(obj_complex, max_depth=1) == {
        "a": 1,
        "b": {"... 2 keys truncated ...": ""},
    }
    # Depth 2: Keeps a, b, c, d; truncates e contents (primitive, so kept)
    assert tl.truncate_json_like_object(obj_complex, max_depth=2) == {
        "a": 1,
        "b": {"c": 2, "d": {"... 1 keys truncated ...": ""}},
    }
    # Depth 3: Keeps everything
    assert tl.truncate_json_like_object(obj_complex, max_depth=3) == obj_complex


def test_truncate_json_like_max_list_len() -> None:
    """Test truncation based on max_list_len."""
    long_list = list(range(20))
    max_len = 10
    truncated = tl.truncate_json_like_object(
        long_list, max_depth=5, max_list_len=max_len
    )
    assert isinstance(truncated, list)
    assert len(truncated) == max_len + 1  # Original items + 1 marker
    half_len = max_len // 2
    last_items_count = max_len - half_len
    assert truncated[:half_len] == long_list[:half_len]  # Check first items
    assert (
        truncated[-last_items_count:] == long_list[-last_items_count:]
    )  # Check last items
    marker = truncated[half_len]
    assert isinstance(marker, dict)
    assert next(iter(marker.keys())) == f"... {len(long_list) - max_len} more items ..."


def test_truncate_json_like_max_list_len_odd() -> None:
    """Test truncation with odd max_list_len."""
    long_list = list(range(21))
    max_len = 9
    truncated = tl.truncate_json_like_object(
        long_list, max_depth=5, max_list_len=max_len
    )
    assert len(truncated) == max_len + 1
    half_len = max_len // 2  # 4
    last_items_count = max_len - half_len  # 5
    assert truncated[:half_len] == long_list[:half_len]
    assert truncated[-last_items_count:] == long_list[-last_items_count:]
    marker = truncated[half_len]
    assert next(iter(marker.keys())) == f"... {len(long_list) - max_len} more items ..."


def test_truncate_json_like_max_list_len_small() -> None:
    """Test truncation when max_list_len is very small."""
    long_list = list(range(10))
    truncated_1 = tl.truncate_json_like_object(long_list, max_list_len=1)
    assert len(truncated_1) == 1
    assert isinstance(truncated_1[0], dict)
    assert next(iter(truncated_1[0].keys())) == "... 10 items truncated ..."

    truncated_0 = tl.truncate_json_like_object(long_list, max_list_len=0)
    assert len(truncated_0) == 1
    assert isinstance(truncated_0[0], dict)
    assert next(iter(truncated_0[0].keys())) == "... 10 items truncated ..."


def test_truncate_json_like_nested_list_depth() -> None:
    """Test truncation of nested lists combined with depth limit."""
    obj = {"a": [1, [2, [3, [4, 5]]]]}
    # Depth 0: Truncates 'a' content
    assert tl.truncate_json_like_object(obj, max_depth=0) == {
        "... 1 keys truncated ...": ""
    }
    # Depth 1: Keeps 'a', truncates list content
    assert tl.truncate_json_like_object(obj, max_depth=1) == {
        "a": [{"... 2 items truncated ...": ""}]
    }
    # Depth 2: Keeps 'a', outer list [1, marker], truncates inner list content
    assert tl.truncate_json_like_object(obj, max_depth=2) == {
        "a": [1, [{"... 2 items truncated ...": ""}]]
    }
    # Depth 3: Keeps 'a', outer list, inner list [2, marker],
    # truncates next list content
    assert tl.truncate_json_like_object(obj, max_depth=3) == {
        "a": [1, [2, [{"... 2 items truncated ...": ""}]]]
    }
    # Depth 4: Keeps 'a', outer list, inner list, next list [3, marker],
    # truncates final list content
    assert tl.truncate_json_like_object(obj, max_depth=4) == {
        "a": [1, [2, [3, [{"... 2 items truncated ...": ""}]]]]
    }
    # Depth 5: Keeps everything
    assert tl.truncate_json_like_object(obj, max_depth=5) == obj


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
    # Content of l1 (l2 dict) should be truncated at depth 2
    assert truncated["deep_dict"]["l1"] == {"... 1 keys truncated ...": ""}

    # Check long_list truncation (len=8)
    assert "long_list" in truncated
    assert len(truncated["long_list"]) == 8 + 1  # 8 items + marker
    assert truncated["long_list"][:4] == [0, 1, 2, 3]
    assert truncated["long_list"][-4:] == [26, 27, 28, 29]
    assert "... 22 more items ..." in truncated["long_list"][4]

    # Check nested_list truncation (depth=2 applies first)
    assert "nested_list" in truncated
    # Depth 1 keeps the outer list [1, 2, inner_list]
    # Depth 2 truncates items within the outer list
    # Item 1 and 2 are primitives, kept as is.
    # Item inner_list [3, 4, [...]] is truncated at depth 2
    assert truncated["nested_list"][0] == 1
    assert truncated["nested_list"][1] == 2
    inner_list_trunc = truncated["nested_list"][2]
    assert inner_list_trunc == [
        {"... 3 items truncated ...": ""}
    ]  # Inner list truncated


def test_truncate_non_dict_list() -> None:
    """Test that non-dict/list objects are returned as is."""
    assert tl.truncate_json_like_object(123) == 123
    assert tl.truncate_json_like_object("string") == "string"
    assert tl.truncate_json_like_object(None) is None


def test_truncate_json_like_object_basic() -> None:
    """Test basic truncation of JSON-like objects."""
    data = {"a": 1, "b": [1, 2, 3, 4, 5], "c": {"d": {"e": "too deep"}}}
    # Truncate depth 2, list len 3
    truncated = tl.truncate_json_like_object(data, max_depth=2, max_list_len=3)
    expected: dict = {
        "a": 1,
        # List truncated: keep first 1, marker, last 2 (3 total)
        "b": [1, {"... 2 more items ...": ""}, 4, 5],
        # Depth 2 reached at 'd', its content (dict {'e':...}) is truncated
        "c": {"d": {"... 1 keys truncated ...": ""}},
    }
    assert truncated == expected


def test_truncate_json_like_object_no_truncation() -> None:
    """Test object truncation when no limits are exceeded."""
    data = {"a": [1, 2], "b": {"c": 3}}
    truncated = tl.truncate_json_like_object(data, max_depth=5, max_list_len=5)
    assert truncated == data


def test_truncate_json_like_object_depth_limit() -> None:
    """Test object truncation purely by depth limit."""
    data = {"a": {"b": {"c": {"d": 4}}}}
    # Depth 2 means content of 'b' (dict {'c':...}) is truncated
    truncated = tl.truncate_json_like_object(data, max_depth=2)
    expected: dict = {"a": {"b": {"... 1 keys truncated ...": ""}}}
    assert truncated == expected


def test_truncate_json_like_object_list_limit() -> None:
    """Test object truncation purely by list length limit."""
    data = list(range(20))
    truncated = tl.truncate_json_like_object(data, max_depth=5, max_list_len=5)
    # keep first 2, marker, last 3
    expected = [0, 1, {"... 15 more items ...": ""}, 17, 18, 19]
    assert truncated == expected


def test_truncate_json_like_object_list_limit_small() -> None:
    """Test object truncation with max_list_len < 2."""
    data = list(range(20))
    truncated_1 = tl.truncate_json_like_object(data, max_depth=5, max_list_len=1)
    expected_1 = [{f"... {len(data)} items truncated ...": ""}]
    assert truncated_1 == expected_1

    truncated_0 = tl.truncate_json_like_object(data, max_depth=5, max_list_len=0)
    expected_0 = [{f"... {len(data)} items truncated ...": ""}]
    assert truncated_0 == expected_0


def test_truncate_json_like_empty_nested() -> None:
    """Test truncation of empty nested structures."""
    # Depth 1: Should truncate the empty dict/list inside
    assert tl.truncate_json_like_object({"a": {}}, max_depth=1) == {"a": {}}
    assert tl.truncate_json_like_object({"a": []}, max_depth=1) == {"a": []}
    # Depth 0: Should truncate the outer dict
    assert tl.truncate_json_like_object({"a": {}}, max_depth=0) == {
        "... 1 keys truncated ...": ""
    }
    assert tl.truncate_json_like_object({"a": []}, max_depth=0) == {
        "... 1 keys truncated ...": ""
    }


def test_truncate_json_like_recursion_empty() -> None:
    """Test truncation recursion handles empty dict/list correctly."""
    # Test case where recursion encounters an empty dict
    data_dict: dict = {"a": {"b": {}}}
    truncated_dict = tl.truncate_json_like_object(data_dict, max_depth=3)
    assert truncated_dict == {"a": {"b": {}}}  # Hits line 98

    # Test case where recursion encounters an empty list
    data_list: dict = {"a": [1, []]}
    truncated_list = tl.truncate_json_like_object(data_list, max_depth=3)
    assert truncated_list == {"a": [1, []]}  # Hits line 106


# --- Tests for _truncate_logs_by_lines --- #


@pytest.mark.parametrize(
    "log_text, max_lines, expected_lines_count, expected_substrings",
    [
        # Basic truncation (more end lines: 10 lines, ratio 0.6 -> end=6, start=4)
        (
            "\n".join([f"Line {i}" for i in range(20)]),
            10,
            10,  # 4 start + 6 end lines
            ["Line 0", "Line 3", "[... 10 lines truncated ...]", "Line 14", "Line 19"],
        ),
        # No truncation needed
        (
            "\n".join([f"Line {i}" for i in range(5)]),
            10,
            5,
            ["Line 0", "Line 4"],
        ),
        # Truncation with fewer lines than previous default minimums
        # (ratio still applies)
        # 100 lines, max_lines=8, ratio 0.6 -> end=round(4.8)=5, start=8-5=3
        (
            "\n".join([f"Line {i}" for i in range(100)]),
            8,
            8,
            ["Line 0", "Line 2", "[... 92 lines truncated ...]", "Line 95", "Line 99"],
        ),
        # Edge case: max_lines = 0
        (
            "\n".join([f"Line {i}" for i in range(10)]),
            0,
            0,  # 0 content lines expected
            ["[... Log truncated entirely ...]"],
        ),
        # Edge case: max_lines = 1 (ratio 0.6 -> end=0, start=1)
        (
            "\n".join([f"Line {i}" for i in range(10)]),
            1,
            1,
            # Expect last line based on updated logic favoring end
            ["Line 9", "[... 9 lines truncated ...]"],
        ),
        # Edge case: max_lines >= num_lines
        (
            "\n".join([f"Line {i}" for i in range(10)]),
            15,
            10,
            ["Line 0", "Line 9"],  # Should return original text
        ),
        # Empty input
        ("", 10, 0, [""]),
        # Single line input
        ("Line 0", 10, 1, ["Line 0"]),
        # Input with exactly max_lines
        (
            "\n".join([f"Line {i}" for i in range(10)]),
            10,
            10,
            ["Line 0", "Line 9"],  # Should return original text
        ),
    ],
)
def test_truncate_logs_by_lines(
    log_text: str,
    max_lines: int,
    expected_lines_count: int,
    expected_substrings: list[str],
) -> None:
    """Test _truncate_logs_by_lines with various inputs."""
    truncated = tl._truncate_logs_by_lines(log_text, max_lines)
    truncated_lines = truncated.splitlines()

    # Check number of lines (handle empty case where splitlines might give [''])
    actual_lines_count = len(truncated_lines) if truncated else 0
    if log_text and not truncated:  # Handle max_lines=0 case properly
        assert expected_lines_count == 1  # Marker line
    elif not log_text:
        assert actual_lines_count == 0
    elif max_lines >= len(log_text.splitlines()):
        assert actual_lines_count == len(log_text.splitlines())
    else:
        # Account for marker line if truncation occurred
        num_original_lines = len(log_text.splitlines())
        lines_truncated_count = num_original_lines - expected_lines_count
        expected_actual_lines = expected_lines_count + (
            1 if lines_truncated_count > 0 else 0
        )

        # Check if the actual number of lines matches the expected count
        # including the marker
        assert (
            actual_lines_count == expected_actual_lines
        ), f"Expected {expected_actual_lines} lines, got {actual_lines_count}"

    # Check for expected content / markers
    for sub in expected_substrings:
        assert sub in truncated

    # Check it doesn't contain lines that should be truncated (simple check)
    if max_lines < len(log_text.splitlines()) and max_lines > 0:
        # Pick a line expected to be truncated
        num_original_lines = len(log_text.splitlines())
        end_lines = int(max_lines * 0.6)
        start_lines = max_lines - end_lines

        mid_line_index = num_original_lines // 2
        mid_line = f"Line {mid_line_index}"

        # Ensure this middle line is NOT present unless it's part of start/end
        # kept lines
        if mid_line_index >= start_lines and mid_line_index < (
            num_original_lines - end_lines
        ):
            assert mid_line not in truncated


def test_truncate_logs_by_lines_basic() -> None:
    """Test basic truncation of logs by lines."""
    lines = [f"Line {i}" for i in range(20)]
    log_text = "\n".join(lines)
    # Keep 10 lines, default 60% end ratio -> 4 start, 6 end
    truncated = tl._truncate_logs_by_lines(log_text, max_lines=10)
    expected_start = "\n".join(lines[:4])
    expected_end = "\n".join(lines[-6:])
    lines_truncated_count = 20 - 4 - 6
    expected_marker = f"[... {lines_truncated_count} lines truncated ...]"
    expected = f"{expected_start}\n{expected_marker}\n{expected_end}"
    assert truncated == expected


def test_truncate_logs_by_lines_no_truncation() -> None:
    """Test log truncation when max_lines is not exceeded."""
    lines = [f"Line {i}" for i in range(10)]
    log_text = "\n".join(lines)
    truncated = tl._truncate_logs_by_lines(log_text, max_lines=15)
    assert truncated == log_text

    truncated_exact = tl._truncate_logs_by_lines(log_text, max_lines=10)
    assert truncated_exact == log_text


def test_truncate_logs_by_lines_zero_limit() -> None:
    """Test log truncation with max_lines=0."""
    lines = [f"Line {i}" for i in range(10)]
    log_text = "\n".join(lines)
    truncated = tl._truncate_logs_by_lines(log_text, max_lines=0)
    assert truncated == "[... Log truncated entirely ...]"


def test_truncate_logs_by_lines_edge_counts() -> None:
    """Test log truncation edge cases for start/end counts."""
    lines: list[str] = [f"Line {i}" for i in range(10)]
    log_text: str = "\n".join(lines)

    # Case 1: Keep 1 line (should be the last one due to updated logic)
    truncated_1: str = tl._truncate_logs_by_lines(log_text, max_lines=1)
    expected_1_end: list[str] = [lines[-1]]
    expected_1_marker: str = "[... 9 lines truncated ...]"
    expected_1: str = f"{expected_1_marker}\n{expected_1_end[0]}"  # Only marker and end
    assert truncated_1 == expected_1

    # Case 2: Keep 2 lines (1 start, 1 end - logic forces this for max_lines=2)
    truncated_2: str = tl._truncate_logs_by_lines(log_text, max_lines=2)
    expected_2_start: list[str] = [lines[0]]
    expected_2_end: list[str] = [
        lines[-1]
    ]  # end_ratio=0.6 -> end_lines = 1, start_lines = 1
    expected_2_marker: str = "[... 8 lines truncated ...]"
    expected_2: str = f"{expected_2_start[0]}\n{expected_2_marker}\n{expected_2_end[0]}"
    assert truncated_2 == expected_2

    # Case 3: Keep 9 lines (4 start, 5 end)
    truncated_9: str = tl._truncate_logs_by_lines(log_text, max_lines=9)
    expected_9_start_str: str = "\n".join(lines[:4])
    expected_9_end_str: str = "\n".join(lines[-5:])
    expected_9_marker: str = "[... 1 lines truncated ...]"
    # Simplified f-string:
    expected_9: str = (
        f"{expected_9_start_str}\n{expected_9_marker}\n{expected_9_end_str}"
    )
    assert truncated_9 == expected_9


def test_truncate_logs_by_lines_max_1() -> None:
    """Test _truncate_logs_by_lines specifically with max_lines=1."""
    log_text = "Line 1\nLine 2\nLine 3\nLine 4"
    # With max_lines=1, it should keep only the last line (end_ratio >= 0.5)
    expected_result = "[... 3 lines truncated ...]\nLine 4"
    assert tl._truncate_logs_by_lines(log_text, 1) == expected_result

    # Test with only one line input
    assert tl._truncate_logs_by_lines("Single line", 1) == "Single line"


def test_calculate_yaml_overhead() -> None:
    """Test the YAML overhead calculation."""
    assert tl._calculate_yaml_overhead(0) == 0
    assert tl._calculate_yaml_overhead(1) == 5  # 1*5 + (1-1)*2
    assert tl._calculate_yaml_overhead(2) == 12  # 2*5 + (2-1)*2
    assert tl._calculate_yaml_overhead(5) == 33  # 5*5 + (5-1)*2


def test_calculate_yaml_overhead_explicit() -> None:
    """Explicitly test edge cases for _calculate_yaml_overhead."""
    assert tl._calculate_yaml_overhead(0) == 0
    assert tl._calculate_yaml_overhead(1) == 5


# --- TestTruncateYamlSectionsBudgeted class removed ---
