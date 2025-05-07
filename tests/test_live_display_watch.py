"""Tests for live_display_watch.py helper functions."""

import pytest
from rich.table import Table
from rich.text import Text
from pathlib import Path
import collections
import re
from unittest.mock import MagicMock, Mock
from pytest_mock import MockerFixture
from typing import Any

from vibectl.live_display_watch import (
    _create_watch_summary_table,
    WatchDisplayState,
    WatchKeypressAction,
    process_keypress,
    _perform_save_to_file,
    _apply_filter_to_lines,
    _refresh_footer_controls_text,
    WatchOutcome,
    WatchReason,
    WatchStatusInfo,
)

# Test cases for _create_watch_summary_table
# Parameters: (command_str, status_info, elapsed_time, lines_streamed, expected_rows, expected_message_row)
test_data = [
    # 1. Basic success case
    (
        "get pods my-pod",
        WatchStatusInfo(
            outcome=WatchOutcome.SUCCESS, reason=WatchReason.PROCESS_EXIT_0, exit_code=0
        ),
        10.55,
        150,
        4,  # Command, Status, Duration, Lines
        None,
    ),
    # 2. Completed with warnings (Success with detail message)
    (
        "get pods --watch",
        WatchStatusInfo(
            outcome=WatchOutcome.SUCCESS,
            reason=WatchReason.PROCESS_EXIT_0,
            detail="Connection timed out",
            exit_code=0,
        ),
        25.1,
        300,
        5,  # Command, Status, Duration, Lines, Message
        (
            "Message",
            Text("Connection timed out", style="yellow"),
        ),  # Warnings/details are yellow
    ),
    # 3. Operation had error (kubectl non-zero exit)
    (
        "get pods non-existent",
        WatchStatusInfo(
            outcome=WatchOutcome.ERROR,
            reason=WatchReason.PROCESS_EXIT_NONZERO,
            detail="pods 'non-existent' not found",
            exit_code=1,
        ),
        5.2,
        10,
        5,  # Command, Status, Duration, Lines, Message
        (
            "Message",
            Text("pods 'non-existent' not found", style="red"),
        ),  # Errors are red
    ),
    # 4. Cancelled by user (with message)
    (
        "get events --watch",
        WatchStatusInfo(
            outcome=WatchOutcome.CANCELLED,
            reason=WatchReason.USER_EXIT_KEY,
            detail="Operation cancelled by user.",
        ),
        120.0,
        5000,
        5,  # Command, Status, Duration, Lines, Message
        (
            "Message",
            Text("Operation cancelled by user.", style="yellow"),
        ),  # Cancellations are yellow
    ),
    # 5. Cancelled by user (no message)
    (
        "logs my-pod -f",
        WatchStatusInfo(
            outcome=WatchOutcome.CANCELLED, reason=WatchReason.CTRL_C, detail=None
        ),  # Example using CTRL_C reason
        60.3,
        1000,
        4,  # Command, Status, Duration, Lines (No Message)
        None,
    ),
    # 6. Operation had internal error (no message)
    (
        "get pods",
        WatchStatusInfo(
            outcome=WatchOutcome.ERROR, reason=WatchReason.INTERNAL_ERROR, detail=None
        ),
        2.1,
        5,
        4,  # Command, Status, Duration, Lines (No Message)
        None,
    ),
    # 7. Setup Error
    (
        "get pods",
        WatchStatusInfo(
            outcome=WatchOutcome.ERROR,
            reason=WatchReason.SETUP_ERROR,
            detail="kubectl not found",
        ),
        0.1,
        0,
        5,  # Command, Status, Duration, Lines, Message
        ("Message", Text("kubectl not found", style="red")),
    ),
]


@pytest.mark.parametrize(
    "command_str, status_info, elapsed_time, lines_streamed, expected_rows, expected_message_content",
    test_data,
)
def test_create_watch_summary_table(
    command_str: str,
    status_info: WatchStatusInfo,
    elapsed_time: float,
    lines_streamed: int,
    expected_rows: int,
    expected_message_content: tuple[str, Text] | None,
) -> None:
    """Verify _create_watch_summary_table generates the correct table structure and content."""
    table = _create_watch_summary_table(
        command_str=command_str,
        status_info=status_info,
        elapsed_time=elapsed_time,
        lines_streamed=lines_streamed,
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
    # assert str(row_data["Status"]) == status_info.outcome.value # This was incorrect
    # Correctly check the formatted status text based on how _create_watch_summary_table formats it
    expected_status_text = f"{status_info.outcome.name.capitalize()}"
    if status_info.reason != WatchReason.PROCESS_EXIT_0:
        expected_status_text += f" ({status_info.reason.name.replace('_', ' ')})"
    if status_info.exit_code is not None:
        expected_status_text += f" (rc={status_info.exit_code})"
    actual_status_text = str(
        row_data["Status"]
    )  # Get the plain text from the Text object
    # Need to handle potential Rich markup in actual_status_text if Text object has style
    # For simplicity, let's assert the plain text content matches
    # A more robust check might involve checking the Text object's spans/style
    assert actual_status_text == expected_status_text

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


# --- Tests for _apply_filter_to_lines ---

filter_lines_test_data = [
    # 1. No filter
    (
        collections.deque(["line a", "line b", "line c"]),
        None,
        ["line a", "line b", "line c"],
    ),
    # 2. Filter matches some (deque input)
    (
        collections.deque(["apple pie", "banana bread", "apple tart"]),
        re.compile(r"apple"),
        ["apple pie", "apple tart"],
    ),
    # 3. Filter matches some (list input)
    (
        ["apple pie", "banana bread", "apple tart"],
        re.compile(r"apple"),
        ["apple pie", "apple tart"],
    ),
    # 4. Filter matches none
    (
        collections.deque(["one", "two", "three"]),
        re.compile(r"four"),
        [],
    ),
    # 5. Filter matches all
    (
        ["test1", "test2", "test3"],
        re.compile(r"test\d"),
        ["test1", "test2", "test3"],
    ),
    # 6. Empty input
    (collections.deque([]), re.compile(r"any"), []),
    ([], None, []),
]


@pytest.mark.parametrize(
    "lines_to_filter, compiled_filter_regex, expected_output", filter_lines_test_data
)
def test_apply_filter_to_lines(
    lines_to_filter: collections.deque[str] | list[str],
    compiled_filter_regex: re.Pattern | None,
    expected_output: list[str],
) -> None:
    """Verify _apply_filter_to_lines correctly filters lines."""
    result = _apply_filter_to_lines(lines_to_filter, compiled_filter_regex)
    assert result == expected_output


# --- Tests for _refresh_footer_controls_text ---


@pytest.fixture
def mock_text_obj() -> Mock:
    """Fixture for a mock Rich Text object."""
    # We only need to mock the 'plain' attribute for assignment
    mock = Mock(spec=Text)
    # Initialize plain attribute so it can be asserted
    mock.plain = ""
    return mock


# Parameters: (state, expected_plain_text)
refresh_footer_test_data = [
    # 1. Default state (wrap on, running, no filter)
    (
        WatchDisplayState(wrap_text=True, is_paused=False, filter_regex_str=None),
        "[E]xit | [W]rap: on | [P]ause: running | [S]ave | [F]ilter: off",
    ),
    # 2. Wrap off, paused, filter active
    (
        WatchDisplayState(
            wrap_text=False, is_paused=True, filter_regex_str="error|warn"
        ),
        "[E]xit | [W]rap: off | [P]ause: paused | [S]ave | [F]ilter: 'error|warn'",
    ),
    # 3. Wrap on, running, filter active
    (
        WatchDisplayState(wrap_text=True, is_paused=False, filter_regex_str="^pod/"),
        "[E]xit | [W]rap: on | [P]ause: running | [S]ave | [F]ilter: '^pod/'",
    ),
    # 4. Wrap off, paused, no filter
    (
        WatchDisplayState(wrap_text=False, is_paused=True, filter_regex_str=None),
        "[E]xit | [W]rap: off | [P]ause: paused | [S]ave | [F]ilter: off",
    ),
]


@pytest.mark.parametrize("state, expected_plain_text", refresh_footer_test_data)
def test_refresh_footer_controls_text(
    mock_text_obj: Mock,
    state: WatchDisplayState,
    expected_plain_text: str,
) -> None:
    """Verify _refresh_footer_controls_text sets the correct plain text."""
    _refresh_footer_controls_text(mock_text_obj, state)
    # Assert that the mock Text object's plain attribute was set correctly
    assert mock_text_obj.plain == expected_plain_text
