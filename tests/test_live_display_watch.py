"""Tests for live_display_watch.py helper functions."""

import pytest
from rich.table import Table
from rich.text import Text
from pathlib import Path
import collections
import re
from unittest.mock import MagicMock
from pytest_mock import MockerFixture
from typing import Any

from vibectl.live_display_watch import (
    _create_watch_summary_table,
    WatchDisplayState,
    WatchKeypressAction,
    process_keypress,
    _perform_save_to_file,
)

# Test cases for _create_watch_summary_table
# Parameters: (command_str, final_status, elapsed_time, lines_streamed, error_message, operation_had_error, expected_rows, expected_message_row)
test_data = [
    # 1. Basic success case
    (
        "get pods my-pod",
        "Completed",
        10.55,
        150,
        None,
        False,
        4,  # CORRECTED: Command, Status, Duration, Lines (No Message)
        None,
    ),
    # 2. Completed with warnings (error_message present, operation_had_error=False, status includes 'warning')
    (
        "get pods --watch",
        "Completed with warnings",
        25.1,
        300,
        "Connection timed out",
        False,
        5,  # CORRECTED: Command, Status, Duration, Lines, Message
        ("Message", Text("Connection timed out", style="yellow")),
    ),
    # 3. Operation had error (error_message present, operation_had_error=True)
    (
        "get pods non-existent",
        "Error (kubectl rc=1)",
        5.2,
        10,
        "pods 'non-existent' not found",
        True,
        5,  # CORRECTED: Command, Status, Duration, Lines, Message
        ("Message", Text("pods 'non-existent' not found", style="red")),
    ),
    # 4. Cancelled by user (error_message can be None or present, operation_had_error=False, status includes 'cancel')
    (
        "get events --watch",
        "Cancelled by user",
        120.0,
        5000,
        "Operation cancelled by user.",  # Example cancel message
        False,
        5,  # CORRECTED: Command, Status, Duration, Lines, Message
        ("Message", Text("Operation cancelled by user.", style="yellow")),
    ),
    # 5. Cancelled by user (error_message is None)
    (
        "logs my-pod -f",
        "Cancelled by user",
        60.3,
        1000,
        None,  # No specific error message
        False,
        4,  # CORRECTED: Command, Status, Duration, Lines (No Message) - error_message is None
        None,
    ),
    # 6. Operation had error, but no error_message provided (edge case)
    (
        "get pods",
        "Error (Internal)",
        2.1,
        5,
        None,
        True,  # Still an error state
        4,  # CORRECTED: Command, Status, Duration, Lines (No Message) - error_message is None
        None,
    ),
]


@pytest.mark.parametrize(
    "command_str, final_status, elapsed_time, lines_streamed, error_message, operation_had_error, expected_rows, expected_message_content",
    test_data,
)
def test_create_watch_summary_table(
    command_str: str,
    final_status: str,
    elapsed_time: float,
    lines_streamed: int,
    error_message: str | None,
    operation_had_error: bool,
    expected_rows: int,
    expected_message_content: tuple[str, Text] | None,
) -> None:
    """Verify _create_watch_summary_table generates the correct table structure and content."""
    table = _create_watch_summary_table(
        command_str=command_str,
        final_status=final_status,
        elapsed_time=elapsed_time,
        lines_streamed=lines_streamed,
        error_message=error_message,
        operation_had_error=operation_had_error,
    )

    assert isinstance(table, Table)
    assert table.title == "Watch Session Summary"
    assert len(table.columns) == 2
    assert table.columns[0].header == "Parameter"
    assert table.columns[1].header == "Value"
    assert len(table.rows) == expected_rows

    # Verify standard rows
    # Accessing cell content via columns._cells seems fragile.
    # Let's try rendering or inspecting row data if possible.
    # Rich Table rows store renderables directly. We can check their 'plain' content.
    assert table.row_count == expected_rows

    # Get row data by iterating (more robust than index guessing if columns change)
    row_data = {}
    for row_idx in range(table.row_count):
        param = table.columns[0]._cells[row_idx]  # Get renderable for param column
        value = table.columns[1]._cells[row_idx]  # Get renderable for value column
        # Use plain text content for comparison
        row_data[str(param)] = value  # Use str(param) as key

    # Assertions checking row_data values
    assert str(row_data["Command"]) == f"`kubectl {command_str}`"
    assert str(row_data["Status"]) == final_status
    assert str(row_data["Duration"]) == f"{elapsed_time:.2f} seconds"
    assert str(row_data["Lines Streamed"]) == str(lines_streamed)

    # Verify message row if expected
    if expected_message_content:
        assert "Message" in row_data
        expected_param, expected_text_obj = expected_message_content
        actual_text_obj = row_data["Message"]
        assert isinstance(actual_text_obj, Text)
        assert actual_text_obj.plain == expected_text_obj.plain
        assert actual_text_obj.style == expected_text_obj.style
    else:
        assert "Message" not in row_data


# --- Tests for process_keypress ---

# Test cases for process_keypress
# Parameters: (input_char, initial_state, expected_new_state, expected_action)
keypress_test_data = [
    # 1. Exit key ('e' or 'E')
    ("e", WatchDisplayState(), WatchDisplayState(), WatchKeypressAction.EXIT),
    (
        "E",
        WatchDisplayState(is_paused=True),
        WatchDisplayState(is_paused=True),
        WatchKeypressAction.EXIT,
    ),
    # 2. Toggle Wrap ('w' or 'W')
    (
        "w",
        WatchDisplayState(wrap_text=True),
        WatchDisplayState(wrap_text=False),
        WatchKeypressAction.TOGGLE_WRAP,
    ),
    (
        "W",
        WatchDisplayState(wrap_text=False, is_paused=True),
        WatchDisplayState(wrap_text=True, is_paused=True),
        WatchKeypressAction.TOGGLE_WRAP,
    ),
    # 3. Toggle Pause ('p' or 'P')
    (
        "p",
        WatchDisplayState(is_paused=False),
        WatchDisplayState(is_paused=True),
        WatchKeypressAction.TOGGLE_PAUSE,
    ),
    (
        "P",
        WatchDisplayState(is_paused=True, wrap_text=False),
        WatchDisplayState(is_paused=False, wrap_text=False),
        WatchKeypressAction.TOGGLE_PAUSE,
    ),
    # 4. Save key ('s' or 'S') - State should not change
    ("s", WatchDisplayState(), WatchDisplayState(), WatchKeypressAction.PROMPT_SAVE),
    (
        "S",
        WatchDisplayState(is_paused=True),
        WatchDisplayState(is_paused=True),
        WatchKeypressAction.PROMPT_SAVE,
    ),
    # 5. Filter key ('f' or 'F') - State should not change
    ("f", WatchDisplayState(), WatchDisplayState(), WatchKeypressAction.PROMPT_FILTER),
    (
        "F",
        WatchDisplayState(filter_regex_str="test"),
        WatchDisplayState(filter_regex_str="test"),
        WatchKeypressAction.PROMPT_FILTER,
    ),
    # 6. Invalid key - State should not change, action is NO_ACTION
    ("x", WatchDisplayState(), WatchDisplayState(), WatchKeypressAction.NO_ACTION),
    (
        "?",
        WatchDisplayState(wrap_text=False),
        WatchDisplayState(wrap_text=False),
        WatchKeypressAction.NO_ACTION,
    ),
]


@pytest.mark.parametrize(
    "input_char, initial_state, expected_new_state, expected_action", keypress_test_data
)
def test_process_keypress(
    input_char: str,
    initial_state: WatchDisplayState,
    expected_new_state: WatchDisplayState,
    expected_action: WatchKeypressAction,
) -> None:
    """Verify process_keypress returns the correct new state and action."""

    new_state, action = process_keypress(input_char, initial_state)

    assert action == expected_action
    # Compare dataclass instances directly
    assert new_state == expected_new_state


# --- Tests for _perform_save_to_file ---


# Mock Path object for testing write operations
@pytest.fixture
def mock_path(mocker: MockerFixture) -> Any:
    mock = mocker.MagicMock(spec=Path)
    # Configure the mock for chained calls like Path(...) / filename
    mock.__truediv__.return_value = mock
    return mock


# Mock time.strftime used for default filename generation
@pytest.fixture
def mock_strftime(mocker: MockerFixture) -> Any:
    return mocker.patch("time.strftime", return_value="20240101_120000")


# Test cases for _perform_save_to_file
# Parameters: (save_dir_mock, filename_suggestion, user_filename, all_lines, filter_re_str, expected_save_path_name, expected_lines_written)
save_test_data = [
    # 1. Basic save, no filter, default filename
    (
        Path("/tmp/savedir"),  # Mocked save_dir value for path construction
        "vibectl_watch_pods_20240101_120000.log",  # filename_suggestion
        None,  # user_provided_filename
        collections.deque(["line1", "line2", "line3"]),  # all_lines
        None,  # filter_re_str
        "vibectl_watch_pods_20240101_120000.log",  # expected_save_path_name
        "line1\nline2\nline3",  # expected_lines_written
    ),
    # 2. Basic save, no filter, user filename
    (
        Path("/data"),
        "suggestion.log",
        "user_file.txt",  # user_provided_filename
        collections.deque(["apple", "banana"]),
        None,  # filter_re_str
        "user_file.txt",  # expected_save_path_name
        "apple\nbanana",  # expected_lines_written
    ),
    # 3. Save with filter, default filename
    (
        Path("."),  # Current directory
        "vibectl_watch_svc_20240101_120000.log",
        None,
        collections.deque(["INFO: ok", "WARN: skip", "DEBUG: ok", "INFO: proceed"]),
        "INFO",  # filter_re_str (will be compiled)
        "vibectl_watch_svc_20240101_120000.log",
        "INFO: ok\nINFO: proceed",  # expected_lines_written (only INFO lines)
    ),
    # 4. Save with filter, user filename
    (
        Path("/logs"),
        "suggestion.log",
        "filtered.log",
        collections.deque(["line a", "line b", "no match", "line c"]),
        r"^line \w$",  # CORRECTED: Single backslash for word character
        "filtered.log",
        "line a\nline b\nline c",  # expected_lines_written
    ),
    # 5. Empty input lines, no filter
    (
        Path("/tmp"),
        "empty_default.log",
        None,
        collections.deque([]),
        None,
        "empty_default.log",
        "",  # expected_lines_written (empty string)
    ),
    # 6. Empty input lines, with filter
    (
        Path("/tmp"),
        "empty_filter.log",
        None,
        collections.deque([]),
        "data",
        "empty_filter.log",
        "",  # expected_lines_written (empty string)
    ),
    # 7. Filter results in empty output
    (
        Path("/tmp"),
        "filter_empty.log",
        None,
        collections.deque(["abc", "def", "ghi"]),
        "xyz",  # filter_re_str (no match)
        "filter_empty.log",
        "",  # expected_lines_written (empty string)
    ),
]


@pytest.mark.parametrize(
    "save_dir_base, filename_suggestion, user_filename, all_lines, filter_re_str, expected_save_path_name, expected_lines_written",
    save_test_data,
)
def test_perform_save_to_file(
    mock_path: MagicMock,  # Use the mocked Path fixture
    mock_strftime: MagicMock,  # Ensure time is mocked for suggestion consistency
    mocker: MockerFixture,  # Pytest mocker fixture
    save_dir_base: Path,  # Base path used in test data
    filename_suggestion: str,
    user_filename: str | None,
    all_lines: collections.deque[str],
    filter_re_str: str | None,
    expected_save_path_name: str,
    expected_lines_written: str,
) -> None:
    """Verify _perform_save_to_file writes correct filtered content to expected path."""

    # Configure the mock_path fixture to represent the specific save_dir for this test case
    # This ensures that `save_dir / filename` resolves correctly using the mock
    mock_save_dir = mocker.MagicMock(spec=Path)
    mock_save_dir.configure_mock(
        **{"__str__": lambda self: str(save_dir_base)}
    )  # So logs look right
    final_mock_path = mocker.MagicMock(spec=Path)
    mock_save_dir.__truediv__.return_value = (
        final_mock_path  # save_dir / filename returns final path
    )

    # Compile filter if provided
    filter_re = re.compile(filter_re_str) if filter_re_str else None

    # Call the function under test
    try:
        returned_path = _perform_save_to_file(
            save_dir=mock_save_dir,  # Pass the configured mock directory
            filename_suggestion=filename_suggestion,
            user_provided_filename=user_filename,
            all_lines=all_lines,
            filter_re=filter_re,
        )
    except Exception as e:
        pytest.fail(f"_perform_save_to_file raised unexpected exception: {e}")

    # Assertions
    assert returned_path == final_mock_path  # Should return the final mock path object

    # Verify the filename division was called correctly
    mock_save_dir.__truediv__.assert_called_once_with(expected_save_path_name)

    # Verify write_text was called on the final path object with correct content
    final_mock_path.write_text.assert_called_once_with(
        expected_lines_written, encoding="utf-8"
    )


# Test error scenario
def test_perform_save_to_file_write_error(
    mock_path: MagicMock, mocker: MockerFixture
) -> None:
    """Verify _perform_save_to_file propagates write errors."""
    mock_save_dir = mocker.MagicMock(spec=Path)
    mock_save_dir.configure_mock(**{"__str__": lambda self: "/fake/dir"})
    final_mock_path = mocker.MagicMock(spec=Path)
    mock_save_dir.__truediv__.return_value = final_mock_path

    # Configure write_text to raise an error
    final_mock_path.write_text.side_effect = OSError("Disk full")

    with pytest.raises(OSError, match="Disk full"):
        _perform_save_to_file(
            save_dir=mock_save_dir,
            filename_suggestion="suggest.log",
            user_provided_filename=None,
            all_lines=collections.deque(["data"]),
            filter_re=None,
        )

    final_mock_path.write_text.assert_called_once()  # Verify it was called
