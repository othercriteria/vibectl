"""Tests for vibe request handling functionality."""

from collections.abc import Generator
from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.command_handler import OutputFlags, handle_vibe_request


def get_test_summary_prompt() -> str:
    """Get a test summary prompt.

    Returns:
        str: The test summary prompt template
    """
    return "Summarize this: {output}"


@pytest.fixture
def mock_confirm() -> Generator[MagicMock, None, None]:
    """Mock click.confirm function."""
    with patch("click.confirm") as mock:
        mock.return_value = True  # Default to confirming actions
        yield mock


def test_handle_vibe_request_success(
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    mock_output_flags_for_vibe_request: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test successful vibe request handling."""
    # Set the return value on the mocked model adapter
    mock_llm.execute.return_value = "get pods"

    # Call function
    handle_vibe_request(
        request="show me the pods",
        command="get",
        plan_prompt="Plan this: {request}",
        summary_prompt_func=get_test_summary_prompt,
        output_flags=mock_output_flags_for_vibe_request,
    )

    # Verify the mock was called correctly
    assert mock_llm.execute.call_count > 0

    # Verify kubectl was called
    mock_run_kubectl.assert_called_once()

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


@patch("vibectl.command_handler.handle_exception")
def test_handle_vibe_request_empty_response(
    mock_handle_exception: MagicMock,
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    mock_output_flags_for_vibe_request: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test vibe request with empty response from planner."""
    # Set up empty response
    mock_llm.execute.return_value = ""

    # Call function
    with patch(
        "vibectl.command_handler.include_memory_in_prompt",
        return_value="Plan this: empty response test",
    ):
        handle_vibe_request(
            request="empty response test",
            command="get",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=get_test_summary_prompt,
            output_flags=mock_output_flags_for_vibe_request,
        )

    # Verify error handling
    mock_handle_exception.assert_called_once()

    # Verify kubectl was NOT called
    mock_run_kubectl.assert_not_called()

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


@patch("vibectl.command_handler.handle_exception")
def test_handle_vibe_request_error_response(
    mock_handle_exception: MagicMock,
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    mock_output_flags_for_vibe_request: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test vibe request with error response from planner."""
    # Set up error response
    mock_llm.execute.return_value = "ERROR: test error"

    # Call function
    with patch(
        "vibectl.command_handler.include_memory_in_prompt",
        return_value="Plan this: error test",
    ):
        handle_vibe_request(
            request="error test",
            command="get",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=get_test_summary_prompt,
            output_flags=mock_output_flags_for_vibe_request,
        )

    # Verify error handling
    mock_handle_exception.assert_called_once()

    # Verify kubectl was NOT called
    mock_run_kubectl.assert_not_called()

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


@patch("vibectl.command_handler.handle_exception")
def test_handle_vibe_request_invalid_format(
    mock_handle_exception: MagicMock,
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test vibe request with invalid format from planner."""
    # Set up invalid response for both calls to execute
    # First call - planning
    # Second call - summary
    mock_llm.execute.side_effect = ["", "Test response"]

    # Call function
    with patch(
        "vibectl.command_handler.include_memory_in_prompt",
        return_value="Plan this: show me the pods",
    ):
        handle_vibe_request(
            request="show me the pods",
            command="get",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=get_test_summary_prompt,
            output_flags=standard_output_flags,
        )

    # Verify exception was handled
    mock_handle_exception.assert_called_once()

    # Verify kubectl was NOT called
    mock_run_kubectl.assert_not_called()

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


def test_handle_vibe_request_no_output(
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: MagicMock,
    prevent_exit: MagicMock,
    mock_memory: MagicMock,
) -> None:
    """Test vibe request with no output flags."""
    # Set up model response
    mock_llm.execute.return_value = "get pods"

    # Create custom OutputFlags with no outputs
    no_output_flags = OutputFlags(
        show_raw=False,
        show_vibe=False,
        warn_no_output=True,
        model_name="model-xyz-1.2.3",
    )

    # Patch the include_memory_in_prompt to return a predictable string
    with patch(
        "vibectl.command_handler.include_memory_in_prompt",
        return_value="Plan this: show me the pods",
    ):
        # Mock console_manager directly for this test
        with patch("vibectl.command_handler.console_manager") as direct_console_mock:
            # Call function
            handle_vibe_request(
                request="show me the pods",
                command="get",
                plan_prompt="Plan this: {request}",
                summary_prompt_func=get_test_summary_prompt,
                output_flags=no_output_flags,
            )

            # Verify warning was printed
            direct_console_mock.print_no_output_warning.assert_called_once()

    # Verify kubectl was called
    mock_run_kubectl.assert_called_once()

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


@patch("vibectl.command_handler.handle_exception")
def test_handle_vibe_request_llm_output_parsing(
    mock_handle_exception: MagicMock,
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test vibe request with LLM output that includes delimiter."""
    # Set up LLM response with delimiter
    mock_llm.execute.side_effect = ["get pods\n---\nother content", "Test response"]

    # Call function
    with patch(
        "vibectl.command_handler.include_memory_in_prompt",
        return_value="Plan this: show me the pods",
    ):
        handle_vibe_request(
            request="show me the pods",
            command="get",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=get_test_summary_prompt,
            output_flags=standard_output_flags,
        )

    # Verify exception handler was not called
    mock_handle_exception.assert_not_called()

    # Verify kubectl was called
    mock_run_kubectl.assert_called_once()

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


@patch("vibectl.command_handler.handle_exception")
def test_handle_vibe_request_command_error(
    mock_handle_exception: MagicMock,
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test vibe request with command execution error."""
    # Set up LLM response
    mock_llm.execute.return_value = "get pods"

    # Set up kubectl to throw an exception
    mock_run_kubectl.side_effect = Exception("Command failed")

    # Call function
    with patch(
        "vibectl.command_handler.include_memory_in_prompt",
        return_value="Plan this: show me the pods",
    ):
        handle_vibe_request(
            request="show me the pods",
            command="get",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=get_test_summary_prompt,
            output_flags=standard_output_flags,
        )

    # Verify exception was handled
    mock_handle_exception.assert_called_once_with(mock_run_kubectl.side_effect)

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


@patch("vibectl.command_handler.handle_exception")
def test_handle_vibe_request_error(
    mock_handle_exception: MagicMock,
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    mock_output_flags_for_vibe_request: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test vibe request with error response."""
    # Set up error response in first line format
    mock_llm.execute.side_effect = ["ERROR: test error", "Test response"]

    # Call function
    with patch(
        "vibectl.command_handler.include_memory_in_prompt",
        return_value="Plan this: error test",
    ):
        handle_vibe_request(
            request="ERROR: test error",
            command="get",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=get_test_summary_prompt,
            output_flags=mock_output_flags_for_vibe_request,
        )

    # Verify error handling
    mock_handle_exception.assert_called_once()

    # Verify kubectl was NOT called
    mock_run_kubectl.assert_not_called()

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


def test_handle_vibe_request_yaml_creation(
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: Mock,
    mock_confirm: MagicMock,
    prevent_exit: MagicMock,
    mock_output_flags_for_vibe_request: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test vibe request with YAML creation."""
    # Set up model adapter response for both calls
    # First call - planning with YAML content (separated by delimiter)
    # Second call - output summarization
    mock_llm.execute.side_effect = [
        "-n\ndefault\n---\napiVersion: v1\nkind: Pod\nmetadata:\n  name: test-pod",
        "Test response",
    ]

    # Set up confirmation to be True (explicitly, although it's the default)
    mock_confirm.return_value = True

    # Call function
    with patch(
        "vibectl.command_handler.include_memory_in_prompt",
        return_value="Plan this: create pod yaml",
    ):
        handle_vibe_request(
            request="create pod yaml",
            command="create",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=get_test_summary_prompt,
            output_flags=mock_output_flags_for_vibe_request,
        )

    # Verify confirmation was shown (create is a dangerous command)
    mock_confirm.assert_called_once()

    # Verify kubectl was called with the correct args
    mock_run_kubectl.assert_called_once()
    args = mock_run_kubectl.call_args[0][0]
    assert args[0] == "create"  # First arg should be the command
    assert args[1] == "-n"  # Check the next args are parsed from the LLM response
    assert args[2] == "default"

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


def test_handle_vibe_request_yaml_response(
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: Mock,
    mock_confirm: MagicMock,
    prevent_exit: MagicMock,
    mock_output_flags_for_vibe_request: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test vibe request with YAML response from planner."""
    # Set up model adapter response with YAML content (separated by delimiter)
    mock_llm.execute.side_effect = [
        "pod\npod-name\n---\napiVersion: v1\nkind: Pod\nmetadata:\n  name: test-pod",
        "Test response",
    ]

    # Call function with yes=True to bypass confirmation
    with patch(
        "vibectl.command_handler.include_memory_in_prompt",
        return_value="Plan this: yaml test",
    ):
        handle_vibe_request(
            request="yaml test",
            command="create",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=get_test_summary_prompt,
            output_flags=mock_output_flags_for_vibe_request,
            yes=True,  # Skip confirmation
        )

    # Verify confirmation was NOT shown (yes=True skips confirmation)
    mock_confirm.assert_not_called()

    # Verify kubectl was called with the correct args
    mock_run_kubectl.assert_called_once()
    args = mock_run_kubectl.call_args[0][0]
    assert args[0] == "create"  # First arg should be the command
    assert args[1] == "pod"  # Check the next args are parsed from the LLM response
    assert args[2] == "pod-name"

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()
