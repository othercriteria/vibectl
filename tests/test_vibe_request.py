"""Tests for vibe request handling functionality."""

from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.cli import cli
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


def test_handle_vibe_request_empty_response(
    mock_console: Mock,
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_memory: MagicMock,
    mock_output_flags_for_vibe_request: OutputFlags,
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

    # Verify kubectl was NOT called
    mock_run_kubectl.assert_not_called()


def test_handle_vibe_request_error_response(
    capsys: pytest.CaptureFixture,
    mock_console: Mock,
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_output_flags_for_vibe_request: OutputFlags,
    mock_memory: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test vibe request with error response from planner."""
    caplog.set_level("ERROR")
    # Set up error response
    mock_llm.execute.side_effect = ["ERROR: test error", "Test response"]
    # Set show_kubectl to True to ensure command is displayed in error messages
    mock_output_flags_for_vibe_request.show_kubectl = True
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
    # Assert the actual log message is present
    assert any(
        "LLM planning error: test error" in r.getMessage() for r in caplog.records
    )
    # Verify kubectl was NOT called (because the command includes ERROR:)
    mock_run_kubectl.assert_not_called()


def test_handle_vibe_request_invalid_format(
    mock_console: Mock,
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_output_flags_for_vibe_request: OutputFlags,
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
            output_flags=mock_output_flags_for_vibe_request,
        )

    # Verify kubectl was NOT called
    mock_run_kubectl.assert_not_called()


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


def test_handle_vibe_request_llm_output_parsing(
    mock_console: Mock,
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_memory: MagicMock,
    mock_output_flags_for_vibe_request: OutputFlags,
    capsys: pytest.CaptureFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test vibe request with LLM output that includes delimiter."""
    caplog.set_level("INFO")
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
            output_flags=mock_output_flags_for_vibe_request,
        )
    mock_subprocess.assert_called_once()
    mock_run_kubectl.assert_not_called()
    # Assert that the summary was printed via print_vibe
    mock_console.print_vibe.assert_called()
    # Optionally, check the summary content if desired
    summary_arg = mock_console.print_vibe.call_args[0][0]
    assert isinstance(summary_arg, str) and summary_arg


def test_handle_vibe_request_command_error(
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test vibe request with command execution error."""
    caplog.set_level("INFO")
    # Set up LLM responses
    mock_llm.execute.side_effect = [
        "get pods",  # First call returns the command
        "You could try using --all-namespaces flag, or specify"
        " a namespace with -n.",  # Second call returns recovery suggestions
    ]

    # Set up kubectl to throw an exception
    mock_run_kubectl.side_effect = Exception("Command failed")
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
        with (
            patch(
                "vibectl.memory.include_memory_in_prompt",
                return_value="Plan this: show me the pods",
            ),
            patch(
                "vibectl.command_handler.recovery_prompt",
                lambda **kwargs: f"Recovery: {kwargs.get('error')}",
            ),
        ):
            handle_vibe_request(
                request="show me the pods",
                command="get",
                plan_prompt="Plan this: {request}",
                summary_prompt_func=get_test_summary_prompt,
                output_flags=standard_output_flags,
            )
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        mock_run_kubectl.assert_called_once()
        # Now verify that execute was called twice - once for command, once for recovery
        assert mock_llm.execute.call_count == 2
        # Verify the second call contains error information
        second_call_args = mock_llm.execute.call_args_list[1][0][1]
        assert "Command failed" in second_call_args
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr


def test_handle_vibe_request_error(
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    mock_output_flags_for_vibe_request: OutputFlags,
    mock_memory: MagicMock,
    capsys: pytest.CaptureFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test vibe request with error response."""
    caplog.set_level("ERROR")
    # Set up error response in first line format
    mock_llm.execute.side_effect = ["ERROR: test error", "Test response"]
    # Set show_kubectl to True to ensure command is displayed in error messages
    mock_output_flags_for_vibe_request.show_kubectl = True
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
    # Assert the actual log message is present
    assert any(
        "LLM planning error: test error" in r.getMessage() for r in caplog.records
    )
    # Verify kubectl was NOT called (because the command includes ERROR:)
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
            yes=True,  # Bypass the interactive prompt
        )

    # Verify that memory was updated
    mock_memory.assert_called_once()
    # No need to verify specific args as they can vary by implementation


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
            yes=True,  # Bypass the interactive prompt
        )

    # Verify that memory was updated
    mock_memory.assert_called_once()

    # No need to verify specific args as they can vary by implementation


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
    with patch(
        "vibectl.command_handler._create_display_command"
    ) as mock_create_display:
        # Make sure display command returns something simple for consistent testing
        mock_create_display.return_value = "pods"

        handle_vibe_request(
            request="show me the pods",
            command="get",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=get_test_summary_prompt,
            output_flags=show_kubectl_flags,
        )

    # Verify print_processing was called with the kubectl command
    # Command format is "command vibe request" since this is a "vibe" style request
    mock_console_manager.print_processing.assert_any_call(
        "Running: kubectl get vibe show me the pods"
    )

    # Reset the mock for the next test
    mock_console_manager.reset_mock()

    # Now test with show_kubectl=False
    hide_kubectl_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=True,
        model_name="test-model",
        show_kubectl=False,
    )

    with patch(
        "vibectl.command_handler._create_display_command"
    ) as mock_create_display:
        # Make sure display command returns something simple for consistent testing
        mock_create_display.return_value = "pods"

        handle_vibe_request(
            request="show me the pods",
            command="get",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=get_test_summary_prompt,
            output_flags=hide_kubectl_flags,
        )

    # Verify print_processing was NOT called with the kubectl command
    for call in mock_console_manager.print_processing.call_args_list:
        if isinstance(call[0][0], str) and "kubectl" in call[0][0]:
            raise AssertionError(
                f"Should not display kubectl command, but found: {call[0][0]}"
            )


def test_vibe_cli_emits_vibe_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """CLI-level test: 'vibectl vibe' emits the '✨ Vibe check:' emoji in output."""
    from click.testing import CliRunner

    runner = CliRunner()

    # Patch get_memory to return a known value
    monkeypatch.setattr(
        "vibectl.memory.get_memory", lambda *a, **kw: "Test memory context"
    )

    # Patch model adapter to return a known command and summary
    class DummyModel:
        class Resp:
            def __init__(self, text: str) -> None:
                self._text = text

            def text(self) -> str:
                return self._text

        def prompt(self, prompt_text: str) -> object:
            # First call is for planning, second for summary
            if "Plan this" in prompt_text:
                return self.Resp("get pods")
            return self.Resp("1 pod running")

    monkeypatch.setattr(
        "vibectl.model_adapter.llm.get_model",
        lambda name: DummyModel(),
    )
    # Patch run_kubectl to return a known output
    monkeypatch.setattr(
        "vibectl.command_handler.run_kubectl",
        lambda *a, **kw: "dummy kubectl get pods output",
    )
    # Patch update_memory to no-op
    monkeypatch.setattr("vibectl.command_handler.update_memory", lambda *a, **kw: None)
    # Patch click.confirm to always return True
    monkeypatch.setattr("click.confirm", lambda *a, **kw: True)

    result = runner.invoke(cli, ["vibe"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "✨ Vibe check:" in result.output
    assert "1 pod running" in result.output
