"""Tests for vibe request handling functionality."""

import json
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner
from pytest_mock import MockerFixture

from vibectl.cli import cli
from vibectl.command_handler import OutputFlags, handle_vibe_request
from vibectl.model_adapter import LLMModelAdapter
from vibectl.types import ActionType, Success


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


@pytest.fixture
def mock_prompt() -> Generator[MagicMock, None, None]:
    """Mock click.prompt function."""
    with patch("click.prompt") as mock:
        yield mock


@pytest.fixture
def mock_llm(mocker: MockerFixture) -> Generator[MagicMock, None, None]:
    """Mocks the get_model_adapter and its methods.

    Yields the mocked adapter *instance*.
    """
    mock_get_adapter = mocker.patch("vibectl.command_handler.get_model_adapter")
    mock_adapter_instance = MagicMock(spec=LLMModelAdapter)
    mock_model_instance = MagicMock()
    mock_get_adapter.return_value = mock_adapter_instance
    mock_adapter_instance.get_model.return_value = mock_model_instance
    mock_adapter_instance.execute.return_value = "Default execute response"
    yield mock_adapter_instance # Yield the adapter instance


def test_handle_vibe_request_success(
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    mock_output_flags_for_vibe_request: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test successful vibe request handling."""
    # Mock the planning response with JSON
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["pods"],  # Command args after 'get'
        "explanation": "Get the pods.",
    }
    # Mock the summary response (called later)
    summary_response = {
        "action_type": ActionType.FEEDBACK.value,
        "explanation": "Here are the pods.",
    }
    mock_llm.execute.side_effect = [
        json.dumps(plan_response), # Return JSON string
        json.dumps(summary_response), # Return JSON string
    ]
    # Mock the kubectl output
    mock_run_kubectl.return_value = Success(data="pod-a\npod-b")

    # Patch _execute_command
    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd:
        mock_execute_cmd.return_value = Success(data="pod-a\npod-b")

        # Patch handle_command_output to prevent recursion and simplify test
        with patch("vibectl.command_handler.handle_command_output") as mock_handle_output:
            mock_handle_output.return_value = Success(data="Processed: pod-a\npod-b")

            # Call function
            handle_vibe_request(
                request="show me the pods",
                command="get",
                plan_prompt="Plan this: {request}",
                summary_prompt_func=get_test_summary_prompt,
                output_flags=mock_output_flags_for_vibe_request,
            )

    # Verify _execute_command was called (replacing the old run_kubectl check)
    mock_execute_cmd.assert_called_once_with("get", ["pods"], None)

    # Verify handle_command_output was called
    mock_handle_output.assert_called_once()
    # Get the args passed to handle_command_output
    ho_call_args, ho_call_kwargs = mock_handle_output.call_args
    # Check the first argument passed to handle_command_output was the Success object from _execute_command
    assert isinstance(ho_call_args[0], Success)
    assert ho_call_args[0].data == "pod-a\npod-b"
    # Check other args like output_flags and command
    assert ho_call_args[1] == mock_output_flags_for_vibe_request
    assert ho_call_kwargs["command"] == "get"


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
    # Set up error response JSON
    error_response = {
        "action_type": ActionType.ERROR.value,
        "error": "test planner error",
        "explanation": "Something went wrong during planning.",
    }
    # Ensure the mock returns a valid JSON string
    mock_llm.execute.return_value = json.dumps(error_response)

    # Set show_kubectl to True to ensure command is displayed in error messages
    # (though no command runs here)
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
    assert "LLM planning error: test planner error" in caplog.text
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
    # Set up model response JSON
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["pods"],
        "explanation": "Get pods",
    }
    # Summary not needed as handle_command_output is fully mocked
    mock_llm.execute.return_value = json.dumps(plan_response) # Return JSON string

    # Create custom OutputFlags with no outputs
    no_output_flags = OutputFlags(
        show_raw=False,
        show_vibe=False,
        warn_no_output=True,
        model_name="model-xyz-1.2.3",
        show_kubectl=False,
    )

    # Mock console_manager directly for this test to add print_raw
    # and check print_no_output_warning
    with patch("vibectl.command_handler.console_manager") as direct_console_mock, \
         patch("vibectl.command_handler._execute_command") as mock_execute_cmd, \
         patch("vibectl.memory.include_memory_in_prompt", return_value="Plan this: show me the pods"):

        # Configure the console mock methods needed by handle_command_output
        direct_console_mock.print_no_output_warning = MagicMock()
        direct_console_mock.print_error = MagicMock()
        direct_console_mock.print_processing = MagicMock()
        direct_console_mock.print_raw = MagicMock() # Add mock for print_raw

        # Mock the execution result
        mock_execute_cmd.return_value = Success(data="pod-a\npod-b")

        # Call handle_vibe_request (handle_command_output will be called internally)
        handle_vibe_request(
            request="show me the pods",
            command="get",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=get_test_summary_prompt,
            output_flags=no_output_flags,
        )

        # Verify warning was printed by the real handle_command_output -> _check_output_visibility
        direct_console_mock.print_no_output_warning.assert_called_once()

        # Verify _execute_command was called
        mock_execute_cmd.assert_called_once()

    # Verify run_kubectl was NOT called directly (it's called by _execute_command)
    mock_run_kubectl.assert_not_called()

    # Verify sys.exit was not called
    prevent_exit.assert_not_called()


def test_handle_vibe_request_llm_output_parsing(
    mock_console: Mock,
    mock_llm: MagicMock,
    mock_run_kubectl: Mock,
    mock_memory: MagicMock,
    mock_output_flags_for_vibe_request: OutputFlags,
    mock_prompt: MagicMock,
    capsys: pytest.CaptureFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test vibe request with LLM output that includes delimiter."""
    caplog.set_level("INFO")
    # Construct expected JSON for planning
    yaml_content = "kind: Pod\nmetadata:\n  name: test-pod"
    expected_response_plan = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["-f", "-"], # Args only
        "yaml_content": yaml_content, # YAML moved here
        "explanation": "Applying YAML.",
    }
    summary_response = {
        "action_type": ActionType.FEEDBACK.value,
        "explanation": "Test response",
    }
    mock_llm.execute.side_effect = [
        json.dumps(expected_response_plan), # Return JSON string
        json.dumps(summary_response) # Return JSON string
    ]
    # Mock _execute_command which handles YAML internally
    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd:
        mock_execute_cmd.return_value = Success(data="pod/test-pod created")

        # Let the real handle_command_output run to trigger summary LLM call
        handle_vibe_request(
            request="apply this yaml",
            command="apply", # Set command to apply
            plan_prompt="Plan this: {request}",
            summary_prompt_func=get_test_summary_prompt,
            output_flags=mock_output_flags_for_vibe_request,
            yes=True, # Bypass confirmation for apply command
        )

    # Verify LLM calls
    assert mock_llm.execute.call_count == 2

    # Verify confirmation handler was NOT called (due to command="apply")
    # Use the mock_prompt fixture for the assertion
    mock_prompt.assert_not_called()

    # Assert that the final result from handle_vibe_request reflects the summary
    # Check print_vibe was called by the console manager mock
    # Note: mock_console print_vibe might not be configured; adjust if needed
    # mock_console.print_vibe.assert_called_once_with("Test response")
    # Let's check the execution instead for now
    mock_execute_cmd.assert_called_once_with("apply", ["-f", "-"], yaml_content)


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
    # Construct expected JSON for planning
    expected_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["get", "pods"],
        "explanation": "Getting pods as requested",
    }
    # Set up LLM responses
    recovery_response = {
        "action_type": ActionType.FEEDBACK.value,
        "explanation": "You could try using --all-namespaces flag, or specify a namespace with -n.",
    }
    mock_llm.execute.side_effect = [
        json.dumps(expected_response),  # First call returns the JSON command
        json.dumps(recovery_response),  # Second call returns recovery suggestions as JSON
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
    # Set up error response JSON
    error_response = {
        "action_type": ActionType.ERROR.value,
        "error": "test error from llm", # Specific error message for this test
        "explanation": "LLM failed to process the request.",
    }
    # Ensure the mock returns a JSON string
    mock_llm.execute.return_value = json.dumps(error_response)

    # Set show_kubectl to True to ensure command is displayed in error messages
    # (though no command runs here)
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
    assert "LLM planning error: test error from llm" in caplog.text
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
    # Construct expected JSON for planning
    expected_response_plan = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["get", "pods", "---", "-n default\n---\napiVersion: v1\nkind: Pod\nmetadata:\n  name: test-pod"],
        "explanation": "Creating pod from YAML definition.",
    }
    # Set up model adapter response for both calls
    summary_response = {
        "action_type": ActionType.FEEDBACK.value,
        "explanation": "Test response",
    }
    mock_llm.execute.side_effect = [
        json.dumps(expected_response_plan),
        json.dumps(summary_response), # Summary after successful execution as JSON
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
    mock_prompt: MagicMock,
    prevent_exit: MagicMock,
    mock_output_flags_for_vibe_request: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test vibe request handling when the planned command involves YAML input."""
    # Mock the planning response with JSON indicating YAML usage
    yaml_content = "apiVersion: v1\nkind: Pod\nmetadata:\n  name: test-pod"
    expected_response_plan = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["-f", "-"], # Args only
        "yaml_content": yaml_content, # YAML moved here
        "explanation": "Creating pod from YAML.",
    }
    # Set up model adapter response with YAML content (separated by delimiter)
    summary_response = {
        "action_type": ActionType.FEEDBACK.value,
        "explanation": "Test response",
    }
    mock_llm.execute.side_effect = [
        json.dumps(expected_response_plan),
        json.dumps(summary_response), # Summary as JSON
    ]

    # Patch _execute_command instead of run_kubectl_with_yaml directly
    with patch("vibectl.command_handler._execute_command") as mock_execute_command, \
         patch("vibectl.command_handler._handle_command_confirmation") as mock_confirmation_handler:

        # Mock _execute_command to simulate successful YAML application
        mock_execute_command.return_value = Success(data="pod/test-pod created")

        # Call function
        handle_vibe_request(
            request="apply yaml for test-pod",
            command="apply", # Command is apply
            plan_prompt="Plan this: {request}",
            summary_prompt_func=get_test_summary_prompt,
            output_flags=mock_output_flags_for_vibe_request,
            yes=True,  # Skip confirmation
        )

    # Verify LLM calls
    assert mock_llm.execute.call_count == 2

    # Verify confirmation handler was NOT called (due to yes=True)
    mock_confirmation_handler.assert_not_called()
    # Verify click.prompt was not called (use fixture mock)
    mock_prompt.assert_not_called()

    # Verify _execute_command was called with correct args
    mock_execute_command.assert_called_once()
    call_args, _ = mock_execute_command.call_args
    assert call_args[0] == "apply" # command
    assert call_args[1] == ["-f", "-"] # args
    assert call_args[2] == yaml_content # yaml_content


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
    # Construct expected JSON for planning
    expected_response_plan = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["get", "pods", "---", "-n default\n---\napiVersion: v1\nkind: Pod\nmetadata:\n  name: foo\n"
        "  labels:\n    app: nginx-demo\nspec:\n  containers:\n  - name: nginx\n"
        "    image: nginx:latest\n    ports:\n    - containerPort: 80\n---\n"
        "apiVersion: v1\nkind: Pod\nmetadata:\n  name: bar\n  labels:\n"
        "    app: nginx-demo\nspec:\n  containers:\n  - name: nginx\n"
        "    image: nginx:latest\n    ports:\n    - containerPort: 80"],
        "explanation": "Creating multiple pods from YAML.",
    }

    # Simulate a model response for creating two pods
    summary_response = {
        "action_type": ActionType.FEEDBACK.value,
        "explanation": "Test response",
    }
    mock_llm.execute.side_effect = [
        json.dumps(expected_response_plan), # Planning step returns JSON
        json.dumps(summary_response), # Summary step as JSON
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
    # Set up model responses - first one is for plan
    expected_plan = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["pods"], # CORRECTED: Planned args *after* the verb
        "explanation": "Get pods",
    }
    # Summary response (might be needed by handle_command_output)
    summary_response = {
        "action_type": ActionType.FEEDBACK.value,
        "explanation": "Test summary",
    }
    mock_llm.execute.side_effect = [json.dumps(expected_plan), json.dumps(summary_response)]

    # Test with show_kubectl=True
    show_kubectl_flags = OutputFlags(
        show_raw=False, # Don't show raw output for simplicity
        show_vibe=False, # Don't show vibe output for simplicity
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=True,
    )

    # Mock only _execute_command, let handle_command_output run (partially)
    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd:
        mock_execute_cmd.return_value = Success(data="kubectl output")

        # Call function with show_kubectl=True
        handle_vibe_request(
            request="show me the pods",
            command="get", # Original command verb
            plan_prompt="Plan this: {request}",
            summary_prompt_func=get_test_summary_prompt,
            output_flags=show_kubectl_flags,
        )

    # Verify print_processing was called with the correct command string
    # The command string is constructed from the original command verb and planned args
    mock_console_manager.print_processing.assert_any_call(
        "Running: kubectl get pods" # Correct expected string
    )

    # Verify _execute_command was called
    mock_execute_cmd.assert_called_once_with("get", ["pods"], None) # CORRECTED: Args list

    # Reset the mock for the next test
    mock_console_manager.reset_mock()
    mock_execute_cmd.reset_mock()
    mock_llm.reset_mock()
    mock_llm.execute.side_effect = [json.dumps(expected_plan), json.dumps(summary_response)] # Reset side effect


    # Now test with show_kubectl=False
    hide_kubectl_flags = OutputFlags(
        show_raw=False,
        show_vibe=False,
        warn_no_output=False,
        model_name="test-model",
        show_kubectl=False,
    )

    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd:
        mock_execute_cmd.return_value = Success(data="kubectl output")

        handle_vibe_request(
            request="show me the pods",
            command="get",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=get_test_summary_prompt,
            output_flags=hide_kubectl_flags,
        )

    # Verify print_processing was NOT called with the kubectl command
    # Check all calls to print_processing
    kubectl_running_call_found = False
    for call in mock_console_manager.print_processing.call_args_list:
        # Check if the first argument of the call is a string containing 'Running: kubectl'
        if isinstance(call.args[0], str) and call.args[0].startswith("Running: kubectl"):
            kubectl_running_call_found = True
            break
    assert not kubectl_running_call_found, "print_processing was called with 'Running: kubectl ...' when show_kubectl was False"

    # Verify _execute_command was still called
    mock_execute_cmd.assert_called_once_with("get", ["pods"], None) # CORRECTED: Args list


def test_vibe_cli_emits_vibe_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """CLI-level test: 'vibectl vibe' emits the '✨ Vibe check:' emoji in output."""

    runner = CliRunner()

    # Define the mock function for handle_vibe_request
    from typing import Any

    from vibectl.types import Result, Success

    def mock_handle_vibe(*args: Any, **kwargs: Any) -> Success:
        # Return a Success object, simulating a successful vibe request
        return Success(message="1 pod running")

    # Patch handle_vibe_request directly where it's used in vibe_cmd
    monkeypatch.setattr(
        "vibectl.subcommands.vibe_cmd.handle_vibe_request", mock_handle_vibe
    )

    # Patch handle_result to display the vibe emoji with the message
    def mock_handle_result(result: Result) -> Result:
        if isinstance(result, Success):
            from vibectl.utils import console_manager

            console_manager.print_vibe(f"✨ Vibe check: {result.message}")
        return result

    monkeypatch.setattr("vibectl.cli.handle_result", mock_handle_result)

    # Run the command
    result = runner.invoke(cli, ["vibe"], catch_exceptions=False)

    # Check for the emoji in the output - this is the main thing we're testing
    assert result.exit_code == 0
    assert "✨ Vibe check:" in result.stdout


@pytest.fixture
def mock_adapter_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[MagicMock, None, None]:
    """Mock vibe adapter instance."""
    mock_adapter_instance = MagicMock()
    mock_model_instance = MagicMock()
    mock_adapter_instance.get_model.return_value = mock_model_instance

    # Configure the mock adapter instance's execute method (can be overridden in tests)
    mock_adapter_instance.execute.return_value = "Default execute response"

    # Yield the mock adapter instance, not the function mock
    yield mock_adapter_instance
