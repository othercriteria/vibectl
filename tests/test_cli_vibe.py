from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from vibectl.cli import cli
from vibectl.command_handler import OutputFlags
from vibectl.model_adapter import LLMModelAdapter
from vibectl.schema import (
    ActionType,
    CommandAction,
    ErrorAction,
    FeedbackAction,
    LLMPlannerResponse,
)
from vibectl.subcommands.vibe_cmd import run_vibe_command
from vibectl.types import Error, Result, Success


# Local fixtures specifically for these tests
@pytest.fixture
def mock_handle_vibe_request() -> Generator[Mock, None, None]:
    """Mock handle_vibe_request for vibe command tests."""
    with patch("vibectl.subcommands.vibe_cmd.handle_vibe_request") as mock:
        yield mock


@pytest.fixture
def mock_get_memory() -> Generator[Mock, None, None]:
    """Mock the get_memory function in vibe_cmd for CLI tests."""
    with patch("vibectl.subcommands.vibe_cmd.get_memory") as mock:
        mock.return_value = "Memory context"
        yield mock


@patch("vibectl.subcommands.vibe_cmd.configure_output_flags")
@patch("vibectl.memory.get_memory")
@patch("vibectl.execution.vibe.get_model_adapter")
@patch("vibectl.memory.get_model_adapter")
@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.execution.vibe._execute_command")
@pytest.mark.asyncio
async def test_vibe_command_with_request(
    mock_execute_command: Mock,
    mock_ch_get_model_adapter: Mock,
    mock_mem_get_model_adapter: Mock,
    mock_exec_vibe_get_model_adapter: Mock,
    mock_global_get_memory: Mock,
    mock_configure_flags: Mock,
    default_output_flags: OutputFlags,
) -> None:
    """Test the main vibe command with a request and OutputFlags."""
    mock_configure_flags.return_value = default_output_flags
    mock_global_get_memory.return_value = ""

    # 1. Mock get_model_adapter factory to return our mock adapter instance
    mock_adapter_instance = MagicMock(spec=LLMModelAdapter)
    mock_exec_vibe_get_model_adapter.return_value = mock_adapter_instance
    mock_mem_get_model_adapter.return_value = mock_adapter_instance
    mock_ch_get_model_adapter.return_value = mock_adapter_instance

    # 2. The adapter's get_model method will be called to get a model object.
    #    This model object is passed to adapter.execute(), but our mocked execute
    #    won't use it. We just need get_model() to not fail.
    mock_adapter_instance.get_model.return_value = MagicMock()

    # Mock the execute_and_log_metrics method which is called by _get_llm_plan,
    # update_memory, and _get_llm_summary
    planned_commands = ["create", "deployment", "nginx", "--image=nginx"]
    mock_adapter_instance.execute_and_log_metrics.side_effect = [
        (
            LLMPlannerResponse(
                action=CommandAction(
                    action_type=ActionType.COMMAND,
                    commands=planned_commands,
                )
            ).model_dump_json(),
            None,
        ),  # 1. For _get_llm_plan call
        ("Memory updated after execution.", None),  # 2. For first update_memory call
        ("Deployment created successfully.", None),  # 3. For _get_llm_summary call
        ("Memory updated after summary.", None),  # 4. For second update_memory call
    ]

    mock_execute_command.return_value = Success(data="deployment created")

    cmd_obj = cli.commands["vibe"]
    with pytest.raises(SystemExit) as exc_info:
        # Add --yes to bypass potential confirmation prompts
        await cmd_obj.main(["Create a deployment", "--show-raw-output", "--yes"])

    assert exc_info.value.code == 0
    # Assert _execute_command was called with the planned commands
    mock_execute_command.assert_called_once_with(
        planned_commands[0], planned_commands[1:], None, allowed_exit_codes=(0,)
    )
    assert mock_exec_vibe_get_model_adapter.call_count >= 1
    assert mock_mem_get_model_adapter.call_count >= 1
    assert mock_ch_get_model_adapter.call_count >= 1
    assert (
        mock_adapter_instance.get_model.call_count >= 1
    )  # get_model is called by _get_llm_plan and update_memory
    assert (
        mock_adapter_instance.execute_and_log_metrics.call_count >= 1
    )  # Plan + at least one memory/summary


@patch("vibectl.memory.get_memory")
@patch("vibectl.subcommands.vibe_cmd.handle_vibe_request", new_callable=AsyncMock)
@patch("vibectl.subcommands.vibe_cmd.configure_output_flags")
@pytest.mark.asyncio
async def test_vibe_command_without_request(
    mock_configure_flags: Mock,
    mock_handle_vibe_request: AsyncMock,
    mock_get_memory: Mock,
) -> None:
    """Test the main vibe command without a request and OutputFlags."""
    mock_get_memory.return_value = ""
    mock_handle_vibe_request.return_value = Success()  # Keep simple for now

    # Call run_vibe_command directly
    result = await run_vibe_command(
        request=None,  # Explicitly None for no request
        show_raw_output=True,
        show_vibe=None,  # Let configure_output_flags handle defaults
        show_kubectl=None,
        model=None,
        exit_on_error=False,
        show_streaming=True,
    )

    assert isinstance(result, Success)  # Can now assert Success
    mock_handle_vibe_request.assert_called_once()
    args, kwargs = mock_handle_vibe_request.call_args
    assert kwargs["request"] == ""  # Should be empty string
    # Check flags passed to handle_vibe_request were configured correctly
    mock_configure_flags.assert_called_once_with(
        show_raw_output=True,
        show_vibe=None,
        model=None,
        show_kubectl=None,
        show_metrics=None,
        show_streaming=True,
    )


@patch("vibectl.subcommands.vibe_cmd.configure_output_flags")
@patch("vibectl.memory.get_memory")
@patch("vibectl.execution.vibe.get_model_adapter")
@patch("vibectl.memory.get_model_adapter")
@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.execution.vibe._execute_command")
@pytest.mark.asyncio
async def test_vibe_command_with_yes_flag(
    mock_execute_command: Mock,
    mock_ch_get_model_adapter: Mock,
    mock_mem_get_model_adapter: Mock,
    mock_exec_vibe_get_model_adapter: Mock,
    mock_global_get_memory: Mock,
    mock_configure_flags: Mock,
    default_output_flags: OutputFlags,
) -> None:
    """Test the main vibe command with the yes flag, mocking network calls."""
    mock_configure_flags.return_value = default_output_flags
    mock_global_get_memory.return_value = ""

    # 1. Mock get_model_adapter factory
    mock_adapter_instance = MagicMock(spec=LLMModelAdapter)
    mock_exec_vibe_get_model_adapter.return_value = mock_adapter_instance
    mock_mem_get_model_adapter.return_value = mock_adapter_instance
    mock_ch_get_model_adapter.return_value = mock_adapter_instance

    # 2. Mock adapter's get_model
    mock_adapter_instance.get_model.return_value = MagicMock()

    # 3. Mock adapter's execute_and_log_metrics method for sequential plan and feedback
    planned_commands = ["create", "deployment", "my-deploy", "--image=nginx"]
    plan_json = LLMPlannerResponse(
        action=CommandAction(
            action_type=ActionType.COMMAND,
            commands=planned_commands,
        )
    ).model_dump_json()
    mock_adapter_instance.execute_and_log_metrics.side_effect = [
        (plan_json, None),  # For _get_llm_plan
        (
            LLMPlannerResponse(
                action=FeedbackAction(
                    action_type=ActionType.FEEDBACK,
                    message="kubectl failed",
                )
            ).model_dump_json(),
            None,
        ),  # For recovery
        ("Memory updated after initial plan.", None),  # For first update_memory
        ("Memory updated after recovery feedback.", None),  # For second update_memory
    ]

    # 4. Mock _execute_command to simulate failure
    mock_execute_command.return_value = Error(error="kubectl create failed")

    # Let the actual handle_vibe_request run, relying on inner mocks

    cmd_obj = cli.commands["vibe"]
    with pytest.raises(SystemExit) as exc_info:
        # Run with --yes
        await cmd_obj.main(["Create a deployment", "--yes", "--show-raw-output"])

    # We expect it to fail because _execute_command (simulating kubectl)
    # failed, even with --yes
    assert exc_info.value.code != 0

    # Verify mocks were called
    assert mock_exec_vibe_get_model_adapter.call_count >= 1
    assert mock_mem_get_model_adapter.call_count >= 1
    assert mock_ch_get_model_adapter.call_count >= 1
    assert mock_adapter_instance.get_model.call_count >= 1
    assert (
        mock_adapter_instance.execute_and_log_metrics.call_count >= 2
    )  # Plan + recovery feedback
    mock_execute_command.assert_called_once_with(
        planned_commands[0], planned_commands[1:], None, allowed_exit_codes=(0,)
    )


@patch("vibectl.memory.get_memory")
@patch("vibectl.subcommands.vibe_cmd.handle_vibe_request", new_callable=AsyncMock)
@patch("vibectl.subcommands.vibe_cmd.configure_output_flags")
@pytest.mark.asyncio
async def test_vibe_command_with_no_arguments_plan_prompt(
    mock_configure_flags: Mock,
    mock_handle_vibe: AsyncMock,
    mock_get_memory: Mock,
) -> None:
    """Test 'vibe' command with no arguments: plan prompt and processing message."""
    mock_get_memory.return_value = ""
    mock_handle_vibe.return_value = Success()  # Keep simple for now

    # Call run_vibe_command directly
    result = await run_vibe_command(
        request=None,
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        exit_on_error=False,
        show_streaming=True,
    )

    assert isinstance(result, Success)
    mock_handle_vibe.assert_called_once()
    mock_configure_flags.assert_called_once()  # Verify config was called
    args, kwargs = mock_handle_vibe.call_args
    assert kwargs["request"] == ""


@patch("vibectl.memory.get_memory")
@patch("vibectl.subcommands.vibe_cmd.handle_vibe_request", new_callable=AsyncMock)
@patch("vibectl.subcommands.vibe_cmd.configure_output_flags")
@pytest.mark.asyncio
async def test_vibe_command_with_existing_memory_plan_prompt(
    mock_configure_flags: Mock,
    mock_handle_vibe: AsyncMock,
    mock_get_memory: Mock,
) -> None:
    """Test 'vibe' command with existing memory: plan prompt and processing message."""
    memory_value = "Working in namespace 'test' with deployment 'app'"
    mock_get_memory.return_value = memory_value
    mock_handle_vibe.return_value = Success()  # Keep simple for now

    # Call run_vibe_command directly
    result = await run_vibe_command(
        request=None,
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        exit_on_error=False,
        show_streaming=True,
    )

    assert isinstance(result, Success)
    mock_handle_vibe.assert_called_once()
    mock_configure_flags.assert_called_once()
    args, kwargs = mock_handle_vibe.call_args
    assert kwargs["request"] == ""


# Tests calling run_vibe_command directly should be async and await
@patch("vibectl.memory.get_memory")
@patch("vibectl.subcommands.vibe_cmd.handle_vibe_request", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_vibe_command_with_explicit_request_plan_prompt(
    mock_handle_vibe: AsyncMock,
    mock_get_memory: Mock,
) -> None:
    """Test 'vibe' command with an explicit request."""
    # Set up mocks
    mock_get_memory.return_value = "Working in namespace 'test'"
    mock_handle_vibe.return_value = Success(message="Command executed successfully")

    # Call the function directly and await it
    request = "scale deployment app to 3 replicas"
    result = await run_vibe_command(
        request=request,
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        exit_on_error=False,  # Important for testing the return value
        show_streaming=True,
    )

    # Verify results
    assert isinstance(result, Success)
    assert result.message == "Command executed successfully"
    mock_handle_vibe.assert_called_once()
    args, kwargs = mock_handle_vibe.call_args
    assert kwargs["request"] == request


@patch("vibectl.subcommands.vibe_cmd.logger")
@patch("vibectl.memory.get_memory")
@patch(
    "vibectl.subcommands.vibe_cmd.handle_vibe_request",
    new_callable=AsyncMock,
    side_effect=Exception("fail!"),
)
@pytest.mark.asyncio
async def test_vibe_command_handle_vibe_request_exception(
    mock_handle_vibe: AsyncMock,
    mock_get_memory: Mock,
    mock_logger: Mock,
) -> None:
    """Test that an exception in handle_vibe_request is caught and returns Error."""
    mock_get_memory.return_value = "mem"
    result = await run_vibe_command(
        "do something", None, None, None, None, exit_on_error=False, show_streaming=True
    )
    assert isinstance(result, Error)
    assert "fail!" in result.error
    mock_logger.error.assert_called_once()
    mock_handle_vibe.assert_called_once()


# Removed redundant test - vibe_command_calls_logger_and_console


@patch("vibectl.subcommands.vibe_cmd.configure_memory_flags")
@patch("vibectl.subcommands.vibe_cmd.configure_output_flags")
@patch("vibectl.subcommands.vibe_cmd.logger")
@patch("vibectl.memory.get_memory")
@patch("vibectl.subcommands.vibe_cmd.handle_vibe_request", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_vibe_command_logs_and_console_for_empty_request(
    mock_handle_vibe: AsyncMock,
    mock_get_memory: Mock,
    mock_logger: Mock,
    mock_configure_output: Mock,
    mock_configure_memory: Mock,
) -> None:
    """Test that logger is called for empty request."""
    mock_get_memory.return_value = "mem"
    mock_handle_vibe.return_value = Success()

    result = await run_vibe_command(
        "", None, None, None, None, exit_on_error=False, show_streaming=True
    )
    assert isinstance(result, Success)
    mock_logger.info.assert_any_call("Invoking 'vibe' subcommand with request: ''")
    mock_logger.info.assert_any_call(
        "No request provided; using memory context for planning."
    )
    mock_handle_vibe.assert_called_once()
    mock_configure_output.assert_called_once_with(
        show_raw_output=None,
        show_vibe=None,
        model=None,
        show_kubectl=None,
        show_metrics=None,
        show_streaming=True,
    )
    mock_configure_memory.assert_called_once()


@patch("vibectl.subcommands.vibe_cmd.logger")
@patch("vibectl.memory.get_memory")
@patch("vibectl.subcommands.vibe_cmd.handle_vibe_request", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_vibe_command_logs_and_console_for_nonempty_request(
    mock_handle_vibe: AsyncMock,
    mock_get_memory: Mock,
    mock_logger: Mock,
) -> None:
    """Test that logger is called for non-empty request."""
    mock_get_memory.return_value = "mem"
    mock_handle_vibe.return_value = Success()

    result = await run_vibe_command(
        "do something", None, None, None, None, show_streaming=True
    )
    assert isinstance(result, Success)
    mock_logger.info.assert_any_call(
        "Invoking 'vibe' subcommand with request: 'do something'"
    )
    mock_logger.info.assert_any_call("Planning how to: do something")
    mock_handle_vibe.assert_called_once()


@patch("vibectl.subcommands.vibe_cmd.logger")
@patch("vibectl.memory.get_memory")
@patch(
    "vibectl.subcommands.vibe_cmd.handle_vibe_request",
    new_callable=AsyncMock,
    side_effect=Exception("fail!"),
)
@pytest.mark.asyncio
async def test_vibe_command_handle_vibe_request_exception_exit_on_error_true(
    mock_handle_vibe: AsyncMock,
    mock_get_memory: Mock,
    mock_logger: Mock,
) -> None:
    """Test that an exception in handle_vibe_request is raised if exit_on_error=True."""
    mock_get_memory.return_value = "mem"
    with pytest.raises(Exception, match="fail!"):
        await run_vibe_command(
            "do something",
            None,
            None,
            None,
            None,
            exit_on_error=True,
            show_streaming=True,
        )
    mock_handle_vibe.assert_called_once()
    # Expect logger.error to be called twice due to re-raise
    assert mock_logger.error.call_count == 2


# Test for handling ValueError specifically (recoverable in auto mode)
@patch("vibectl.subcommands.vibe_cmd.logger")
@patch("vibectl.memory.get_memory")
@patch(
    "vibectl.subcommands.vibe_cmd.handle_vibe_request",
    new_callable=AsyncMock,
    side_effect=ValueError("LLM parse error"),
)
@pytest.mark.asyncio
async def test_vibe_command_handle_vibe_request_value_error(
    mock_handle_vibe: AsyncMock,
    mock_get_memory: Mock,
    mock_logger: Mock,
) -> None:
    """Test ValueError from handler returns Error(halt_auto_loop=False)."""
    mock_get_memory.return_value = "mem"
    result = await run_vibe_command(
        "do something", None, None, None, None, exit_on_error=False, show_streaming=True
    )
    assert isinstance(result, Error)
    assert "LLM parse error" in result.error
    assert result.halt_auto_loop is False  # Check if marked as recoverable
    mock_logger.warning.assert_called_once()
    mock_handle_vibe.assert_called_once()


@patch(
    "vibectl.execution.vibe.handle_vibe_request"
)  # To ensure we are testing the right function if called via CLI
@patch("vibectl.memory.get_model_adapter")  # For memory updates
@patch(
    "vibectl.execution.vibe.get_model_adapter"
)  # For planning in handle_vibe_request
@pytest.mark.asyncio
async def test_handle_vibe_with_unknown_model(
    mock_exec_vibe_get_model_adapter: Mock,  # Patches execution.vibe.get_model_adapter
    mock_mem_get_model_adapter: Mock,  # Patches memory.get_model_adapter
    mock_actual_handle_vibe_request_call: AsyncMock,  # Mock of the function itself
) -> None:
    """Test that the vibe command properly reports errors for unknown model names."""
    # cfg = Config() # Unused variable

    # 1. Configure the mock for vibectl.execution.vibe.get_model_adapter
    #    This is called by handle_vibe_request.
    mock_adapter_instance_exec = MagicMock(spec=LLMModelAdapter)
    mock_exec_vibe_get_model_adapter.return_value = mock_adapter_instance_exec
    mock_adapter_instance_exec.get_model.side_effect = ValueError(
        "Unknown model: invalid-model-name"
    )

    # 2. Configure the mock for vibectl.memory.get_model_adapter
    # This is called by update_memory
    mock_adapter_instance_mem = MagicMock(spec=LLMModelAdapter)
    mock_mem_get_model_adapter.return_value = mock_adapter_instance_mem
    mock_mem_model_obj = MagicMock()
    mock_mem_get_model_adapter.return_value.get_model.return_value = mock_mem_model_obj
    # Ensure execute_and_log_metrics on this instance doesn't fail
    # if called by update_memory
    mock_mem_get_model_adapter.return_value.execute_and_log_metrics.return_value = (
        "Memory updated during error handling.",
        None,
    )

    # Set up the mock for the direct call to handle_vibe_request if called by CLI
    # We are testing the CLI command behavior here
    async def side_effect_handle_vibe_request(*args: Any, **kwargs: Any) -> Result:
        # Actually call the real function from vibectl.execution.vibe
        # This requires importing the real function within the test scope or
        # globally in the test file
        from vibectl.execution.vibe import handle_vibe_request as real_hvr

        return await real_hvr(*args, **kwargs)

    mock_actual_handle_vibe_request_call.side_effect = side_effect_handle_vibe_request

    # Call the CLI command entry point directly
    cmd_obj = cli.commands["vibe"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["show me pods", "--model", "invalid-model-name"])

    assert exc_info.value.code == 1

    # Assert that our patched vibectl.execution.vibe.get_model_adapter was called
    mock_exec_vibe_get_model_adapter.assert_called_once()
    mock_adapter_instance_exec.get_model.assert_called_once_with("invalid-model-name")

    # Assert that vibectl.memory.get_model_adapter was also called (by update_memory)
    mock_mem_get_model_adapter.assert_called_once()
    mock_mem_get_model_adapter.return_value.get_model.assert_called_once()
    mock_mem_get_model_adapter.return_value.execute_and_log_metrics.assert_called_once()


@patch("vibectl.memory.get_model_adapter")
@patch("vibectl.execution.vibe.get_model_adapter")
@patch("vibectl.command_handler.get_model_adapter")  # Added
@patch("vibectl.memory.get_memory")
@patch("vibectl.subcommands.vibe_cmd.configure_output_flags")
@patch("vibectl.execution.vibe._execute_command")  # Changed from Popen
@pytest.mark.asyncio
async def test_vibe_command_with_yaml_input(
    mock_execute_command: Mock,  # Changed
    mock_configure_flags: Mock,
    mock_global_get_memory: Mock,
    mock_ch_get_model_adapter: Mock,  # Added
    mock_exec_vibe_get_model_adapter: Mock,
    mock_mem_get_model_adapter: Mock,
    default_output_flags: OutputFlags,
) -> None:
    """Test vibe command when LLM plan includes YAML content and kubeconfig handling."""
    mock_configure_flags.return_value = default_output_flags
    mock_global_get_memory.return_value = ""

    # --- Mock LLM and Memory Adapters ---
    mock_adapter_instance = MagicMock(spec=LLMModelAdapter)
    mock_exec_vibe_get_model_adapter.return_value = mock_adapter_instance
    mock_mem_get_model_adapter.return_value = mock_adapter_instance
    mock_ch_get_model_adapter.return_value = mock_adapter_instance  # Added
    mock_adapter_instance.get_model.return_value = MagicMock()

    yaml_content_str = "apiVersion: v1\\nkind: ConfigMap\\nmetadata:\\n  name: my-cm"
    planned_commands = ["apply", "-f", "-"]
    plan_json = LLMPlannerResponse(
        action=CommandAction(
            action_type=ActionType.COMMAND,
            commands=planned_commands,
            yaml_manifest=yaml_content_str,
        )
    ).model_dump_json()

    mock_adapter_instance.execute_and_log_metrics.side_effect = [
        (plan_json, None),
        ("Memory updated after execution.", None),
        ("ConfigMap applied.", None),
        ("Memory updated after summary.", None),
    ]

    # --- Mock _execute_command ---
    # This now replaces the Popen mock and Config mock for kubeconfig path
    mock_execute_command.return_value = Success(data="configmap/my-cm created")

    # --- Execute Command ---
    cmd_obj = cli.commands["vibe"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["Apply a configmap", "--yes"])

    # --- Assertions ---
    assert exc_info.value.code == 0
    mock_execute_command.assert_called_once_with(
        planned_commands[0],
        planned_commands[1:],
        yaml_content_str,
        allowed_exit_codes=(0,),
    )
    # Remove or adjust mock_ch_config assertions if no longer relevant
    # mock_ch_config.return_value.get.assert_any_call("kubeconfig", default=None)
    assert mock_exec_vibe_get_model_adapter.call_count >= 1
    assert mock_mem_get_model_adapter.call_count >= 1
    assert mock_ch_get_model_adapter.call_count >= 1


@patch("vibectl.subcommands.vibe_cmd.configure_output_flags")
@patch("vibectl.memory.get_memory")
@patch("vibectl.execution.vibe.get_model_adapter")
@patch("vibectl.memory.get_model_adapter")
@patch("vibectl.command_handler.get_model_adapter")  # Added
@patch(
    "vibectl.execution.vibe._execute_command"
)  # Changed from vibectl.k8s_utils.run_kubectl
@pytest.mark.asyncio
async def test_vibe_command_kubectl_failure_no_recovery_plan(
    mock_execute_command: Mock,  # Changed
    mock_ch_get_model_adapter: Mock,  # Added
    mock_mem_get_model_adapter: Mock,
    mock_exec_vibe_get_model_adapter: Mock,
    mock_global_get_memory: Mock,
    mock_configure_flags: Mock,
    default_output_flags: OutputFlags,
) -> None:
    """Test vibe command when kubectl fails and LLM doesn't provide a recovery plan."""
    mock_configure_flags.return_value = default_output_flags
    mock_global_get_memory.return_value = ""

    mock_adapter_instance = MagicMock(spec=LLMModelAdapter)
    mock_exec_vibe_get_model_adapter.return_value = mock_adapter_instance
    mock_mem_get_model_adapter.return_value = mock_adapter_instance
    mock_ch_get_model_adapter.return_value = mock_adapter_instance  # Added

    mock_adapter_instance.get_model.return_value = MagicMock()

    planned_commands = ["delete", "pod", "my-pod"]
    plan_json = LLMPlannerResponse(
        action=CommandAction(
            action_type=ActionType.COMMAND,
            commands=planned_commands,
        )
    ).model_dump_json()

    # LLM returns an error when asked for recovery (e.g. no useful suggestion)
    recovery_error_json = LLMPlannerResponse(
        action=ErrorAction(
            action_type=ActionType.ERROR,
            message="Cannot recover from kubectl failure.",
        )
    ).model_dump_json()

    mock_adapter_instance.execute_and_log_metrics.side_effect = [
        (plan_json, None),  # For _get_llm_plan
        (recovery_error_json, None),  # For recovery prompt in handle_command_output
        ("Memory updated after plan.", None),  # For first update_memory (after plan)
        (
            "Memory updated after recovery attempt.",
            None,
        ),  # For second update_memory (after recovery)
    ]

    # _execute_command (simulating kubectl) itself fails
    mock_execute_command.return_value = Error(
        error="kubectl delete failed miserably"
    )  # Changed

    cmd_obj = cli.commands["vibe"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["delete the pod my-pod", "--yes"])

    assert exc_info.value.code != 0  # Should exit with error

    # Assertions
    mock_execute_command.assert_called_once_with(  # Changed
        planned_commands[0], planned_commands[1:], None, allowed_exit_codes=(0,)
    )
    assert mock_ch_get_model_adapter.call_count >= 1  # Added


# More tests might follow that need similar treatment
