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
        "vibectl.memory.include_memory_in_prompt",
        return_value="Plan this: empty response test",
    ):
        handle_vibe_request(
            request="empty response test",
            command="get",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=get_test_summary_prompt,
            output_flags=mock_output_flags_for_vibe_request,
        )

    # Verify error message was printed
    # This is printed directly to stderr, not via mock_console.print_error,
    # so we don't assert on it

    # Verify handle_exception was not called
    mock_handle_exception.assert_not_called()

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
    capsys: pytest.CaptureFixture,
) -> None:
    """Test vibe request with error response from planner."""
    # Set up error response
    mock_llm.execute.side_effect = ["ERROR: test error", "Test response"]

    # Call function
    with patch(
        "vibectl.memory.include_memory_in_prompt",
        return_value="Plan this: error test",
    ):
        handle_vibe_request(
            request="error test",
            command="get",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=get_test_summary_prompt,
            output_flags=mock_output_flags_for_vibe_request,
        )

    # Check stderr for the message instead of using mock assertion
    captured = capsys.readouterr()
    assert "Planning to run: kubectl ERROR: test error" in captured.err

    # Verify kubectl was NOT called (because the command includes ERROR:)
    mock_run_kubectl.assert_not_called()


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
        "vibectl.memory.include_memory_in_prompt",
        return_value="Plan this: show me the pods",
    ):
        handle_vibe_request(
            request="show me the pods",
            command="get",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=get_test_summary_prompt,
            output_flags=standard_output_flags,
        )

    # Verify handle_exception was not called
    mock_handle_exception.assert_not_called()

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
        show_kubectl=False,
    )

    # Call function with mocked console_manager and include_memory_in_prompt
    with (
        patch(
            "vibectl.memory.include_memory_in_prompt",
            return_value="Plan this: show me the pods",
        ),
        patch("vibectl.command_handler.console_manager") as direct_console_mock,
    ):
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
    # Set up LLM response with delimiter - get commands will also be parsed for YAML now
    mock_llm.execute.side_effect = ["get pods\n---\nother content", "Test response"]

    # Mock subprocess.run for kubectl calls with YAML
    with (
        patch(
            "vibectl.memory.include_memory_in_prompt",
            return_value="Plan this: show me the pods",
        ),
        patch("subprocess.run") as mock_subprocess,
    ):
        # Configure mock subprocess to return success
        mock_process = MagicMock()
        mock_process.stdout = "pod-list-output"
        mock_process.returncode = 0
        mock_subprocess.return_value = mock_process

        handle_vibe_request(
            request="show me the pods",
            command="get",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=get_test_summary_prompt,
            output_flags=standard_output_flags,
        )

    # Verify subprocess was called, and run_kubectl was not called directly
    mock_subprocess.assert_called_once()
    mock_run_kubectl.assert_not_called()

    # Verify exception handler was not called
    mock_handle_exception.assert_not_called()


def test_handle_vibe_request_command_error(
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

    # Create a dummy stdout capture to verify the expected pattern
    import sys
    from io import StringIO

    captured_stdout = StringIO()
    original_stdout = sys.stdout
    captured_stderr = StringIO()
    original_stderr = sys.stderr

    sys.stdout = captured_stdout
    sys.stderr = captured_stderr

    try:
        # Call function
        with patch(
            "vibectl.memory.include_memory_in_prompt",
            return_value="Plan this: show me the pods",
        ):
            handle_vibe_request(
                request="show me the pods",
                command="get",
                plan_prompt="Plan this: {request}",
                summary_prompt_func=get_test_summary_prompt,
                output_flags=standard_output_flags,
            )

        # Restore streams
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        output = captured_stdout.getvalue()

        # The new robustness improvements print errors to stderr directly
        # and don't use mock_handle_exception anymore
        # Instead, verify the call to run_kubectl
        mock_run_kubectl.assert_called_once()

        # Verify recovery suggestions were shown
        assert mock_llm.execute.call_count >= 2

        # Verify the output contains the expected pattern
        # (vibe check with recovery suggestions)
        assert "✨ Vibe check:" in output
        assert "Test response" in output

    finally:
        # Ensure stdout and stderr are restored even if there's an exception
        sys.stdout = original_stdout
        sys.stderr = original_stderr


@patch("vibectl.command_handler.handle_exception")
def test_handle_vibe_request_error(
    mock_handle_exception: MagicMock,
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    mock_output_flags_for_vibe_request: OutputFlags,
    mock_memory: MagicMock,
    capsys: pytest.CaptureFixture,
) -> None:
    """Test vibe request with error response."""
    # Set up error response in first line format
    mock_llm.execute.side_effect = ["ERROR: test error", "Test response"]

    # Call function
    with patch(
        "vibectl.memory.include_memory_in_prompt",
        return_value="Plan this: error test",
    ):
        handle_vibe_request(
            request="ERROR: test error",
            command="get",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=get_test_summary_prompt,
            output_flags=mock_output_flags_for_vibe_request,
        )

    # Check stderr for the message instead of using mock assertion
    captured = capsys.readouterr()
    assert "Planning to run: kubectl ERROR: test error" in captured.err

    # Verify kubectl was NOT called
    mock_run_kubectl.assert_not_called()


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

    # Mock subprocess.run for kubectl calls with YAML
    with (
        patch(
            "vibectl.memory.include_memory_in_prompt",
            return_value="Plan this: create pod yaml",
        ),
        patch("subprocess.run") as mock_subprocess,
    ):
        # Configure mock subprocess to return success
        mock_process = MagicMock()
        mock_process.stdout = "pod/test-pod created"
        mock_process.returncode = 0
        mock_subprocess.return_value = mock_process

        handle_vibe_request(
            request="create pod yaml",
            command="create",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=get_test_summary_prompt,
            output_flags=mock_output_flags_for_vibe_request,
        )

    # Verify confirmation was shown (create is a dangerous command)
    mock_confirm.assert_called_once()

    # Verify subprocess.run was called with correct command format
    mock_subprocess.assert_called_once()
    args, kwargs = mock_subprocess.call_args
    cmd = args[0]

    # Check that the command is properly structured
    assert cmd[0] == "kubectl"
    assert "-n" in " ".join(cmd)
    assert "default" in " ".join(cmd)
    assert "-f" in cmd

    # Verify temp file was created with .yaml extension
    assert any(arg.endswith(".yaml") for arg in cmd)


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

    # Mock subprocess.run for kubectl calls with YAML
    with (
        patch(
            "vibectl.memory.include_memory_in_prompt",
            return_value="Plan this: yaml test",
        ),
        patch("subprocess.run") as mock_subprocess,
    ):
        # Configure mock subprocess to return success
        mock_process = MagicMock()
        mock_process.stdout = "pod/test-pod created"
        mock_process.returncode = 0
        mock_subprocess.return_value = mock_process

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

    # Verify subprocess.run was called with correct command format
    mock_subprocess.assert_called_once()
    args, kwargs = mock_subprocess.call_args
    cmd = args[0]

    # Check that the command is properly structured
    assert cmd[0] == "kubectl"
    assert "pod" in " ".join(cmd)
    assert "pod-name" in " ".join(cmd) or any("pod-name" in arg for arg in cmd)
    assert "-f" in cmd

    # Verify temp file was created with .yaml extension
    assert any(arg.endswith(".yaml") for arg in cmd)


def test_handle_vibe_request_create_pods_yaml(
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: Mock,
    mock_confirm: MagicMock,
    prevent_exit: MagicMock,
    mock_output_flags_for_vibe_request: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test vibe request that specifically creates multiple pods using a YAML manifest.

    This test ensures the regression with create commands and YAML files
    doesn't happen again.
    """
    # Simulate a model response for creating two pods
    # Similar to the failing case from the issue
    mock_llm.execute.side_effect = [
        "-n default\n---\napiVersion: v1\nkind: Pod\nmetadata:\n  name: foo\n"
        "  labels:\n    app: nginx-demo\nspec:\n  containers:\n  - name: nginx\n"
        "    image: nginx:latest\n    ports:\n    - containerPort: 80\n---\n"
        "apiVersion: v1\nkind: Pod\nmetadata:\n  name: bar\n  labels:\n"
        "    app: nginx-demo\nspec:\n  containers:\n  - name: nginx\n"
        "    image: nginx:latest\n    ports:\n    - containerPort: 80",
        "Test response",
    ]

    # Set up confirmation to be True
    mock_confirm.return_value = True

    # Mock subprocess.run for kubectl calls with YAML
    with (
        patch(
            "vibectl.memory.include_memory_in_prompt",
            return_value="Plan this: Create nginx demo pods foo and bar.",
        ),
        patch("subprocess.run") as mock_subprocess,
    ):
        # Configure mock subprocess to return success
        mock_process = MagicMock()
        mock_process.stdout = "pod/foo created\npod/bar created"
        mock_process.returncode = 0
        mock_subprocess.return_value = mock_process

        handle_vibe_request(
            request="Create nginx demo 'hello, world' pods foo and bar.",
            command="create",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=get_test_summary_prompt,
            output_flags=mock_output_flags_for_vibe_request,
        )

    # Verify confirmation was shown (create is a dangerous command)
    mock_confirm.assert_called_once()

    # Verify subprocess.run was called with correct command format
    mock_subprocess.assert_called_once()
    args, kwargs = mock_subprocess.call_args
    cmd = args[0]

    # Check that the command is properly structured for create with YAML
    # The correct format is: kubectl create [-n namespace] -f file.yaml
    assert cmd[0] == "kubectl"
    assert cmd[1] == "create"  # create must be the second element
    # Check that namespace information is included somewhere in the command
    assert "-n" in cmd, "Namespace flag '-n' not found in command"
    assert "default" in cmd, "Namespace value 'default' not found in command"
    # Check for -f flag and YAML file
    assert "-f" in cmd, "Flag '-f' for file input not found in command"


@patch("vibectl.command_handler.console_manager")
def test_show_kubectl_flag_controls_command_display(
    mock_console_manager: MagicMock,
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_memory: MagicMock,
) -> None:
    """Test that show_kubectl flag controls whether kubectl command is displayed."""
    # Set up model responses - first one is for plan, second for summary
    mock_llm.execute.side_effect = ["get pods", "Test summary"]

    # Test with show_kubectl=True
    show_kubectl_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=True,
        model_name="test-model",
        show_kubectl=True,
    )

    # Call function with show_kubectl=True
    handle_vibe_request(
        request="show me the pods",
        command="get",
        plan_prompt="Plan this: {request}",
        summary_prompt_func=get_test_summary_prompt,
        output_flags=show_kubectl_flags,
    )

    # Check calls to print_note - using a more flexible approach
    kubectl_note_found = False
    for call in mock_console_manager.print_note.call_args_list:
        if (
            isinstance(call[0][0], str)
            and "Planning to run: kubectl get pods" in call[0][0]
        ):
            kubectl_note_found = True
            break
    assert (
        kubectl_note_found
    ), "Kubectl command note not displayed when show_kubectl=True"

    # Reset mocks for next test
    mock_console_manager.reset_mock()
    mock_llm.execute.side_effect = ["get pods", "Test summary"]

    # Test with show_kubectl=False for a non-confirmation command
    hide_kubectl_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=True,
        model_name="test-model",
        show_kubectl=False,
    )

    # Call function with show_kubectl=False for a non-dangerous command
    handle_vibe_request(
        request="show me the pods",
        command="get",
        plan_prompt="Plan this: {request}",
        summary_prompt_func=get_test_summary_prompt,
        output_flags=hide_kubectl_flags,
    )

    # Verify print_note was NOT called with the kubectl command
    kubectl_note_found = False
    for call in mock_console_manager.print_note.call_args_list:
        if isinstance(call[0][0], str) and "Planning to run: kubectl" in call[0][0]:
            kubectl_note_found = True
            break
    assert (
        not kubectl_note_found
    ), "Kubectl command note was displayed when show_kubectl=False"
