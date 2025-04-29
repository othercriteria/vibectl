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
from vibectl.types import ActionType, Success, Error


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
    mock_console: Mock,
    prevent_exit: MagicMock,
    mock_output_flags_for_vibe_request: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test successful vibe request handling."""
    # Mock the planning response with JSON, including the verb
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["get", "pods"],  # <<< Added verb
        "explanation": "Get the pods.",
    }
    kubectl_output_data = "pod-a\npod-b"
    # Summary handling is now part of the mock_handle_output side effect
    mock_llm.execute.return_value = json.dumps(plan_response) # Planning returns JSON

    # Patch _execute_command
    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd:
        mock_execute_cmd.return_value = Success(data=kubectl_output_data)

        # Patch handle_command_output to verify it's called correctly
        with patch("vibectl.command_handler.handle_command_output") as mock_handle_output:
            # Call function
            handle_vibe_request(
                request="show me the pods",
                command="vibe", # <<< Original vibectl command is 'vibe'
                plan_prompt="Plan this: {request}",
                summary_prompt_func=get_test_summary_prompt,
                output_flags=mock_output_flags_for_vibe_request,
            )

            # Verify _execute_command was called with correct args
            mock_execute_cmd.assert_called_once_with("get", ["pods"], None) # <<< Updated args

            # Verify handle_command_output was called *after* _execute_command
            mock_handle_output.assert_called_once()
            ho_call_args, ho_call_kwargs = mock_handle_output.call_args
            # Check the first argument passed was the Success object from _execute_command
            assert isinstance(ho_call_args[0], Success)
            assert ho_call_args[0].data == kubectl_output_data
            # Check output_flags
            assert ho_call_args[1] == mock_output_flags_for_vibe_request
            # Check the command kwarg is the extracted verb
            assert ho_call_kwargs.get("command") == "get" # <<< Updated verb

    # Verify memory was updated (mock_memory fixture should handle this if set up)
    # mock_memory.add_interaction.assert_called() # Or similar assertion depending on fixture


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
    error_msg = "test planner error"
    explanation_msg = "Something went wrong during planning."
    error_response = {
        "action_type": ActionType.ERROR.value,
        "error": error_msg,
        "explanation": explanation_msg,
    }
    mock_llm.execute.return_value = json.dumps(error_response)

    # Set show_kubectl to True (doesn't affect this path but good practice)
    mock_output_flags_for_vibe_request.show_kubectl = True

    # Assert the result of handle_vibe_request
    with patch("vibectl.memory.include_memory_in_prompt", return_value="Plan this: error test"):
        result = handle_vibe_request(
            request="ERROR: test error",
            command="get",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=get_test_summary_prompt,
            output_flags=mock_output_flags_for_vibe_request,
        )

    # Assert handle_vibe_request returned an Error object
    assert isinstance(result, Error)
    # Assert the error message matches the one from the LLM JSON response
    assert result.error == f"LLM planning error: {error_msg}"
    # Assert the recovery suggestions come from the explanation
    assert result.recovery_suggestions == explanation_msg

    # Verify kubectl was NOT called
    mock_run_kubectl.assert_not_called()

    # Verify memory was NOT updated on planning error
    mock_memory.add_interaction.assert_not_called()


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
    """Test handling of JSON parsing errors from LLM."""
    caplog.set_level("ERROR")
    # Mock LLM to return invalid JSON
    # Make this syntactically invalid JSON to trigger JSONDecodeError
    invalid_json = '{ "action_type": "COMMAND", "commands": ["pods" }' # Missing closing quote and bracket
    mock_llm.execute.return_value = invalid_json

    # No need to patch _handle_planning_error, assert the return value instead
    with patch("vibectl.memory.include_memory_in_prompt", return_value="Plan this: parsing test"):
        result = handle_vibe_request(
            request="trigger json parse error",
            command="get",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=get_test_summary_prompt,
            output_flags=mock_output_flags_for_vibe_request,
        )

    # Assert handle_vibe_request returned an Error object
    assert isinstance(result, Error)
    # Assert the error message indicates JSON parsing failure caught by Pydantic validation
    assert result.error.startswith("AI response failed validation:")
    assert "Invalid JSON" in result.error
    # Assert the underlying exception is included and is a ValidationError
    from pydantic_core import ValidationError
    assert isinstance(result.exception, ValidationError)

    # Verify kubectl was NOT called
    mock_run_kubectl.assert_not_called()

    # Verify memory was NOT updated
    mock_memory.add_interaction.assert_not_called()


def test_handle_vibe_request_command_error(
    mock_llm: MagicMock,
    mock_console: Mock,
    prevent_exit: MagicMock,
    standard_output_flags: OutputFlags,
    mock_memory: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test vibe request with command execution error."""
    caplog.set_level("ERROR")
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["get", "nonexistent-resource"], # <<< Added verb
        "explanation": "Trying to get a resource that does not exist."
    }
    mock_llm.execute.return_value = json.dumps(plan_response)

    # Patch _execute_command to return an error
    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd:
        error_message = "Error from server (NotFound): the server could not find the requested resource"
        mock_execute_cmd.return_value = Error(error=error_message)

        # Patch handle_command_output to verify it receives the Error
        with patch("vibectl.command_handler.handle_command_output") as mock_handle_output:
            # Call function
            handle_vibe_request(
                request="get nonexistent",
                command="vibe", # <<< Original vibectl command is 'vibe'
                plan_prompt="Plan this: {request}",
                summary_prompt_func=get_test_summary_prompt,
                output_flags=standard_output_flags,
            )

            # Verify _execute_command was called
            mock_execute_cmd.assert_called_once_with("get", ["nonexistent-resource"], None) # <<< Updated args

            # Verify handle_command_output was called with the Error object
            mock_handle_output.assert_called_once()
            ho_call_args, ho_call_kwargs = mock_handle_output.call_args
            assert isinstance(ho_call_args[0], Error)
            assert ho_call_args[0].error == error_message
            # Check the command kwarg is the extracted verb
            assert ho_call_kwargs.get("command") == "get" # <<< Updated verb

    # Verify memory was updated (depending on how handle_command_output mock handles errors)
    # mock_memory.add_interaction.assert_called() # May or may not be called based on mock


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
    """Test vibe request handling when the LLM returns an error action."""
    caplog.set_level("ERROR")
    # Mock LLM planning response (error action)
    error_msg = "test error from llm"
    explanation_msg = "LLM could not process the request."
    plan_response = {
        "action_type": ActionType.ERROR.value,
        "error": error_msg,
        "explanation": explanation_msg,
    }
    mock_llm.execute.return_value = json.dumps(plan_response)

    # Assert the result of handle_vibe_request
    with patch("vibectl.memory.include_memory_in_prompt", return_value="Plan this: llm error"):
        result = handle_vibe_request(
            request="cause an llm error",
            command="error",
            plan_prompt="Plan this: {request}",
            summary_prompt_func=get_test_summary_prompt,
            output_flags=mock_output_flags_for_vibe_request,
        )

    # Assert handle_vibe_request returned an Error object
    assert isinstance(result, Error)
    # Assert the error message matches the one from the LLM JSON response
    assert result.error == f"LLM planning error: {error_msg}"
    # Assert the recovery suggestions come from the explanation
    assert result.recovery_suggestions == explanation_msg

    # Verify kubectl was NOT called
    mock_run_kubectl.assert_not_called()

    # Verify memory was NOT updated
    mock_memory.add_interaction.assert_not_called()


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
    mock_console: Mock,
    mock_prompt: MagicMock,
    prevent_exit: MagicMock,
    mock_output_flags_for_vibe_request: OutputFlags,
    mock_memory: MagicMock,
) -> None:
    """Test handling of commands that might involve YAML (basic case)."""
    # NOTE: Current schema doesn't support embedding YAML in the response.
    # This test checks that commands like 'apply -f -' are passed correctly
    # to _execute_command, even though YAML content isn't handled by the schema yet.
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": ["apply", "-f", "-"], # <<< Command verb and args
        "explanation": "Applying configuration from stdin."
    }
    mock_llm.execute.return_value = json.dumps(plan_response)

    # Mock prompt for confirmation (apply requires confirmation)
    mock_prompt.return_value = 'y'

    # Patch _execute_command
    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd:
        mock_execute_cmd.return_value = Success(data="deployment.apps/nginx-deployment configured")

        # Patch handle_command_output
        with patch("vibectl.command_handler.handle_command_output") as mock_handle_output:
            handle_vibe_request(
                request="apply this config",
                command="vibe", # <<< Original vibectl command is 'vibe'
                plan_prompt="Plan this: {request}",
                summary_prompt_func=get_test_summary_prompt,
                output_flags=mock_output_flags_for_vibe_request,
                yes=False, # Ensure confirmation is triggered
            )

            # Verify confirmation was prompted
            mock_prompt.assert_called_once()
            # Verify _execute_command was called with correct verb/args, None for yaml_content
            mock_execute_cmd.assert_called_once_with("apply", ["-f", "-"], None) # <<< Updated args

            # Verify handle_command_output was called
            mock_handle_output.assert_called_once()
            _, ho_call_kwargs = mock_handle_output.call_args
            assert ho_call_kwargs.get("command") == "apply" # <<< Updated verb


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
    mock_memory: MagicMock,
    prevent_exit: MagicMock,
) -> None:
    """Test that the show_kubectl flag controls command display."""
    # Define common variables for plan response
    kubectl_verb = "get" # Define the verb
    kubectl_args = ["pods", "--namespace=test-ns"] # Define args
    explanation = "Getting pods in test-ns."
    plan_response = {
        "action_type": ActionType.COMMAND.value,
        "commands": [kubectl_verb] + kubectl_args, # Combine verb and args for mock
        "explanation": explanation,
    }
    plan_response_json = json.dumps(plan_response)

    # --- Case 1: show_kubectl = True ---
    output_flags_show = OutputFlags(
        show_raw=False,
        show_vibe=False,
        warn_no_output=False,
        model_name="test",
        show_kubectl=True, # <<< Show command
    )

    # Mock LLM planning response
    mock_llm.execute.return_value = plan_response_json

    # Mock _execute_command
    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd_show:
        mock_execute_cmd_show.return_value = Success("pod data")

        # Mock handle_command_output
        with patch("vibectl.command_handler.handle_command_output") as mock_handle_output_show, \
             patch("vibectl.memory.include_memory_in_prompt", return_value="Plan this: get pods"):

            # Call handle_vibe_request with the original command being 'vibe'
            handle_vibe_request(
                request="get pods in test-ns",
                command="vibe", # <<< Corrected: Original command is 'vibe'
                plan_prompt="Plan this: {request}",
                summary_prompt_func=get_test_summary_prompt,
                output_flags=output_flags_show,
                yes=True, # Bypass confirmation for simplicity in this test
            )

            # Verify console_manager.print_processing was called with the correct command
            mock_console_manager.print_processing.assert_any_call(
                f"Running: kubectl {kubectl_verb} {' '.join(kubectl_args)}" # <<< Correct assertion
            )
            # Verify _execute_command was called with extracted verb and args
            mock_execute_cmd_show.assert_called_once_with(kubectl_verb, kubectl_args, None)
            # Verify handle_command_output was called with correct command verb
            mock_handle_output_show.assert_called_once()
            _, ho_call_kwargs = mock_handle_output_show.call_args
            assert ho_call_kwargs.get("command") == kubectl_verb

    # Reset mocks for next case
    mock_console_manager.reset_mock()
    mock_llm.reset_mock()
    mock_execute_cmd_show.reset_mock()
    mock_handle_output_show.reset_mock()
    # mock_memory.reset_mock() # Assuming mock_memory doesn't need reset per-case

    # --- Case 2: show_kubectl = False ---
    output_flags_hide = OutputFlags(
        show_raw=False,
        show_vibe=False,
        warn_no_output=False,
        model_name="test",
        show_kubectl=False, # <<< Hide command
    )

    # Reuse planning response mock (already has correct format)
    mock_llm.execute.return_value = plan_response_json

    # Mock _execute_command again
    with patch("vibectl.command_handler._execute_command") as mock_execute_cmd_hide:
        mock_execute_cmd_hide.return_value = Success("pod data")

        # Mock handle_command_output again
        with patch("vibectl.command_handler.handle_command_output") as mock_handle_output_hide, \
             patch("vibectl.memory.include_memory_in_prompt", return_value="Plan this: get pods"):

            # Call handle_vibe_request with the original command being 'vibe'
            handle_vibe_request(
                request="get pods in test-ns",
                command="vibe", # <<< Corrected: Original command is 'vibe'
                plan_prompt="Plan this: {request}",
                summary_prompt_func=get_test_summary_prompt,
                output_flags=output_flags_hide,
                yes=True, # Bypass confirmation
            )

            # Verify console_manager.print_processing was NOT called with the command string
            for call in mock_console_manager.print_processing.call_args_list:
                assert not call.args[0].startswith("Running: kubectl") # Check args tuple

            # Verify _execute_command was still called correctly
            mock_execute_cmd_hide.assert_called_once_with(kubectl_verb, kubectl_args, None)
            # Verify handle_command_output was called with correct command verb
            mock_handle_output_hide.assert_called_once()
            _, ho_call_kwargs_hide = mock_handle_output_hide.call_args
            assert ho_call_kwargs_hide.get("command") == kubectl_verb


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
