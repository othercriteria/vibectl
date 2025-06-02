from typing import Any
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from vibectl.config import Config
from vibectl.prompts.apply import apply_output_prompt
from vibectl.subcommands.apply_cmd import run_apply_command
from vibectl.types import Error, MetricsDisplayMode, OutputFlags, Success


@pytest.mark.asyncio
@patch("vibectl.subcommands.apply_cmd.Config")
@patch("vibectl.subcommands.apply_cmd.configure_output_flags")
@patch("vibectl.subcommands.apply_cmd.configure_memory_flags")
@patch("vibectl.subcommands.apply_cmd.logger")
@patch("vibectl.subcommands.apply_cmd.run_kubectl")
@patch("vibectl.subcommands.apply_cmd.handle_command_output", autospec=True)
async def test_run_apply_command_direct_success(
    mock_handle_command_output: MagicMock,
    mock_run_kubectl: MagicMock,
    mock_logger: MagicMock,
    mock_configure_memory_flags: MagicMock,
    mock_configure_output_flags: MagicMock,
    mock_config_cls: MagicMock,
) -> None:
    """Test run_apply_command successful direct kubectl apply execution."""
    mock_config_instance = MagicMock(spec=Config)
    mock_config_cls.return_value = mock_config_instance

    mock_output_flags = MagicMock(spec=OutputFlags)
    mock_output_flags.show_raw_output = False
    mock_output_flags.show_vibe = True
    mock_output_flags.show_kubectl = False
    mock_output_flags.model_name = "test-model"
    mock_output_flags.warn_no_output = False
    mock_output_flags.show_metrics = False
    mock_output_flags.show_streaming = True
    mock_configure_output_flags.return_value = mock_output_flags

    mock_kubectl_result = Success(
        message="Raw kubectl apply output",
        original_exit_code=0,
        data="Original data from kubectl",
    )
    mock_final_processed_result = Success(
        message="Processed: applied successfully",
        original_exit_code=0,
        continue_execution=False,
        data="Processed data from handle_command_output",
    )

    mock_run_kubectl.return_value = mock_kubectl_result

    # Custom side effect to capture arguments
    captured_hco_kwargs: dict[str, Any] = {}

    def hco_side_effect(*args: Any, **kwargs: Any) -> Success:
        nonlocal captured_hco_kwargs
        captured_hco_kwargs = kwargs
        return mock_final_processed_result

    mock_handle_command_output.side_effect = hco_side_effect

    args_tuple = ("-f", "my-deployment.yaml", "-n", "default")

    result = await run_apply_command(
        args=args_tuple,
        show_raw_output=False,
        show_vibe=True,
        show_kubectl=False,
        model="test-model",
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=MetricsDisplayMode.NONE,
        show_streaming=True,
    )

    assert isinstance(result, Success)
    assert result.message == "Processed: applied successfully"
    assert result.original_exit_code == 0
    assert result.continue_execution is False

    mock_logger.info.assert_any_call(
        f"Invoking 'apply' subcommand with args: {args_tuple}"
    )
    mock_logger.info.assert_any_call("Completed direct 'apply' subcommand execution.")

    mock_configure_memory_flags.assert_called_once_with(False, False)
    mock_configure_output_flags.assert_called_once_with(
        show_raw_output=False,
        show_vibe=True,
        model="test-model",
        show_kubectl=False,
        show_metrics=MetricsDisplayMode.NONE,
        show_streaming=True,
    )
    mock_config_cls.assert_called_once()

    mock_run_kubectl.assert_called_once_with(
        cmd=["apply", "-f", "my-deployment.yaml", "-n", "default"],
        config=mock_config_instance,
    )
    mock_handle_command_output.assert_called_once()
    # Now check the captured kwargs
    assert captured_hco_kwargs.get("output") == mock_kubectl_result
    assert captured_hco_kwargs.get("output_flags") == mock_output_flags
    assert captured_hco_kwargs.get("summary_prompt_func") == apply_output_prompt


@pytest.mark.asyncio
@patch("vibectl.subcommands.apply_cmd.Config")
@patch("vibectl.subcommands.apply_cmd.configure_output_flags")
@patch("vibectl.subcommands.apply_cmd.configure_memory_flags")
@patch("vibectl.subcommands.apply_cmd.logger")
@patch("vibectl.subcommands.apply_cmd.run_kubectl")
async def test_run_apply_command_direct_kubectl_error(
    mock_run_kubectl: MagicMock,
    mock_logger: MagicMock,
    mock_configure_memory_flags: MagicMock,
    mock_configure_output_flags: MagicMock,
    mock_config_cls: MagicMock,
) -> None:
    """Test run_apply_command when direct kubectl apply returns an error."""
    mock_config_instance = MagicMock(spec=Config)
    mock_config_cls.return_value = mock_config_instance

    mock_output_flags = MagicMock(spec=OutputFlags)
    mock_output_flags.show_raw_output = False
    mock_output_flags.show_vibe = False
    mock_output_flags.show_kubectl = False
    mock_output_flags.model_name = None
    mock_output_flags.warn_no_output = False
    mock_output_flags.show_metrics = False
    mock_output_flags.show_streaming = True
    mock_configure_output_flags.return_value = mock_output_flags

    mock_kubectl_error = Error(error="kubectl apply failed: specific reason")
    mock_run_kubectl.return_value = mock_kubectl_error

    args_tuple = ("-f", "nonexistent.yaml")
    result = await run_apply_command(
        args=args_tuple,
        show_raw_output=False,
        show_vibe=False,
        show_kubectl=False,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=MetricsDisplayMode.NONE,
        show_streaming=True,
    )

    assert isinstance(result, Error)
    assert result.error == "kubectl apply failed: specific reason"

    mock_logger.info.assert_any_call(
        f"Invoking 'apply' subcommand with args: {args_tuple}"
    )
    mock_logger.error.assert_any_call(
        f"Error running kubectl for direct apply: {mock_kubectl_error.error}"
    )

    mock_configure_memory_flags.assert_called_once_with(False, False)
    mock_configure_output_flags.assert_called_once_with(
        show_raw_output=False,
        show_vibe=False,
        model=None,
        show_kubectl=False,
        show_metrics=MetricsDisplayMode.NONE,
        show_streaming=True,
    )
    mock_config_cls.assert_called_once()
    mock_run_kubectl.assert_called_once_with(
        cmd=["apply", "-f", "nonexistent.yaml"],
        config=mock_config_instance,
    )


@pytest.mark.asyncio
@patch("vibectl.subcommands.apply_cmd.Config")
@patch("vibectl.subcommands.apply_cmd.configure_output_flags")
@patch("vibectl.subcommands.apply_cmd.configure_memory_flags")
@patch("vibectl.subcommands.apply_cmd.logger")
@patch("vibectl.subcommands.apply_cmd.run_kubectl")
@patch("vibectl.subcommands.apply_cmd.handle_command_output", autospec=True)
async def test_run_apply_command_direct_handle_output_error(
    mock_handle_command_output: MagicMock,
    mock_run_kubectl: MagicMock,
    mock_logger: MagicMock,
    mock_configure_memory_flags: MagicMock,
    mock_configure_output_flags: MagicMock,
    mock_config_cls: MagicMock,
) -> None:
    """Test run_apply_command with error in handle_command_output for direct apply."""
    mock_config_instance = MagicMock(spec=Config)
    mock_config_cls.return_value = mock_config_instance

    mock_output_flags = MagicMock(spec=OutputFlags)
    mock_output_flags.show_raw_output = False
    mock_output_flags.show_vibe = True
    mock_output_flags.show_kubectl = False
    mock_output_flags.model_name = "test-model"
    mock_output_flags.warn_no_output = False
    mock_output_flags.show_metrics = False
    mock_output_flags.show_streaming = True
    mock_configure_output_flags.return_value = mock_output_flags

    mock_kubectl_result = Success(
        message="Raw kubectl output for HCO error test",
        original_exit_code=0,
        data="Some data from kubectl for HCO error test",
    )
    mock_handle_output_error_obj = Error(
        error="Error from handle_command_output processing"
    )

    mock_run_kubectl.return_value = mock_kubectl_result

    # Custom side effect to capture arguments and return an error
    captured_hco_kwargs_for_error_test: dict[str, Any] = {}

    def hco_side_effect_for_error_test(*args: Any, **kwargs: Any) -> Error:
        nonlocal captured_hco_kwargs_for_error_test
        captured_hco_kwargs_for_error_test = kwargs
        return mock_handle_output_error_obj  # Return the error object

    mock_handle_command_output.side_effect = hco_side_effect_for_error_test

    args_tuple = ("-f", "some_direct_apply.yaml")
    result = await run_apply_command(
        args=args_tuple,
        show_raw_output=False,
        show_vibe=True,
        show_kubectl=False,
        model="test-model",
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=MetricsDisplayMode.NONE,
        show_streaming=True,
    )

    assert isinstance(result, Error)
    assert result.error == "Error from handle_command_output processing"

    mock_logger.info.assert_any_call(
        f"Invoking 'apply' subcommand with args: {args_tuple}"
    )
    mock_logger.info.assert_any_call("Completed direct 'apply' subcommand execution.")

    mock_configure_memory_flags.assert_called_once_with(False, False)
    mock_configure_output_flags.assert_called_once_with(
        show_raw_output=False,
        show_vibe=True,
        model="test-model",
        show_kubectl=False,
        show_metrics=MetricsDisplayMode.NONE,
        show_streaming=True,
    )
    mock_config_cls.assert_called_once()

    mock_run_kubectl.assert_called_once_with(
        cmd=["apply", "-f", "some_direct_apply.yaml"],
        config=mock_config_instance,
    )

    mock_handle_command_output.assert_called_once()
    # Check the captured kwargs for this error test
    assert captured_hco_kwargs_for_error_test.get("output") == mock_kubectl_result
    assert captured_hco_kwargs_for_error_test.get("output_flags") == mock_output_flags
    assert (
        captured_hco_kwargs_for_error_test.get("summary_prompt_func")
        == apply_output_prompt
    )


@pytest.mark.asyncio
@patch("vibectl.subcommands.apply_cmd.configure_output_flags")
@patch("vibectl.subcommands.apply_cmd.configure_memory_flags")
async def test_run_apply_command_vibe_missing_request(
    mock_configure_memory_flags: MagicMock,
    mock_configure_output_flags: MagicMock,
) -> None:
    """Test run_apply_command with vibe subcommand but missing request."""
    mock_output_flags = MagicMock(spec=OutputFlags)
    # Set all flags to default/False for this test, including show_streaming
    mock_output_flags.show_raw_output = False
    mock_output_flags.show_vibe = False
    mock_output_flags.show_kubectl = False
    mock_output_flags.model_name = None
    mock_output_flags.warn_no_output = False
    mock_output_flags.show_metrics = False
    mock_output_flags.show_streaming = True  # Explicitly set based on call
    mock_configure_output_flags.return_value = mock_output_flags

    args_tuple = ("vibe",)  # Missing the actual request string
    result = await run_apply_command(
        args=args_tuple,
        show_raw_output=False,
        show_vibe=False,  # Corresponds to mock_output_flags
        show_kubectl=False,  # Corresponds to mock_output_flags
        model=None,  # Corresponds to mock_output_flags
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=MetricsDisplayMode.NONE,  # Corresponds to mock_output_flags
        show_streaming=True,  # This is passed and should be asserted
    )

    assert isinstance(result, Error)
    assert "Missing request after 'vibe' command" in result.error

    mock_configure_memory_flags.assert_called_once_with(False, False)
    mock_configure_output_flags.assert_called_once_with(
        show_raw_output=False,
        show_vibe=False,
        model=None,
        show_kubectl=False,
        show_metrics=MetricsDisplayMode.NONE,
        show_streaming=True,  # Added show_streaming assertion
    )


@pytest.mark.asyncio
@patch("vibectl.subcommands.apply_cmd.handle_vibe_request")
@patch("vibectl.execution.apply.get_model_adapter")
@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.subcommands.apply_cmd.Config")
@patch("vibectl.subcommands.apply_cmd.configure_output_flags")
@patch("vibectl.subcommands.apply_cmd.configure_memory_flags")
@patch("vibectl.subcommands.apply_cmd.logger")
async def test_run_apply_command_vibe_success(
    mock_logger: MagicMock,
    mock_configure_memory_flags: MagicMock,
    mock_configure_output_flags: MagicMock,
    mock_config_cls: MagicMock,
    mock_get_model_adapter_ch: MagicMock,
    mock_get_model_adapter_ac: MagicMock,
    mock_handle_vibe_request: MagicMock,
) -> None:
    """Test run_apply_command successful vibe execution."""
    mock_config_instance = MagicMock(spec=Config)
    mock_config_instance.get_typed.return_value = False  # Not intelligent apply
    mock_config_cls.return_value = mock_config_instance

    mock_output_flags = MagicMock(spec=OutputFlags)
    mock_output_flags.show_raw_output = False
    mock_output_flags.show_vibe = True
    mock_output_flags.show_kubectl = False
    mock_output_flags.model_name = "test-model-vibe"
    mock_output_flags.warn_no_output = False
    mock_output_flags.show_metrics = False
    mock_output_flags.show_streaming = True  # Added show_streaming
    mock_configure_output_flags.return_value = mock_output_flags

    mock_model_adapter_instance_ch = MagicMock()
    mock_get_model_adapter_ch.return_value = mock_model_adapter_instance_ch

    mock_model_adapter_instance_ac = MagicMock()
    mock_get_model_adapter_ac.return_value = mock_model_adapter_instance_ac

    mock_vibe_success_result = Success(
        message="Vibe apply successful", original_exit_code=0
    )
    mock_handle_vibe_request.return_value = mock_vibe_success_result

    args_tuple = ("vibe", "deploy this thing")
    result = await run_apply_command(
        args=args_tuple,
        show_raw_output=False,
        show_vibe=True,
        show_kubectl=False,
        model="test-model-vibe",
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=MetricsDisplayMode.NONE,
        show_streaming=True,  # Passed here
    )

    assert result == mock_vibe_success_result
    mock_logger.info.assert_any_call(
        f"Invoking 'apply' subcommand with args: {args_tuple}"
    )
    mock_logger.info.assert_any_call("Using standard vibe request handler for apply.")
    mock_logger.info.assert_any_call(
        "Completed 'apply' subcommand for standard vibe request."
    )

    mock_configure_memory_flags.assert_called_once_with(False, False)
    mock_configure_output_flags.assert_called_once_with(
        show_raw_output=False,
        show_vibe=True,
        model="test-model-vibe",
        show_kubectl=False,
        show_metrics=MetricsDisplayMode.NONE,
        show_streaming=True,  # Added show_streaming
    )
    mock_config_cls.assert_called_once()
    mock_config_instance.get_typed.assert_called_once_with("intelligent_apply", True)

    mock_handle_vibe_request.assert_called_once_with(
        request="deploy this thing",
        command="apply",
        plan_prompt_func=ANY,
        summary_prompt_func=ANY,
        output_flags=mock_output_flags,
        yes=False,
    )


@pytest.mark.asyncio
@patch("vibectl.subcommands.apply_cmd.handle_vibe_request")
@patch("vibectl.execution.apply.get_model_adapter")
@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.subcommands.apply_cmd.Config")
@patch("vibectl.subcommands.apply_cmd.configure_output_flags")
@patch("vibectl.subcommands.apply_cmd.configure_memory_flags")
@patch("vibectl.subcommands.apply_cmd.logger")
async def test_run_apply_command_vibe_error_from_handler(
    mock_logger: MagicMock,
    mock_configure_memory_flags: MagicMock,
    mock_configure_output_flags: MagicMock,
    mock_config_cls: MagicMock,
    mock_get_model_adapter_ch: MagicMock,
    mock_get_model_adapter_ac: MagicMock,
    mock_handle_vibe_request: MagicMock,
) -> None:
    """Test run_apply_command with vibe execution that returns an error."""
    mock_config_instance = MagicMock(spec=Config)
    mock_config_instance.get_typed.return_value = False  # Not intelligent apply
    mock_config_cls.return_value = mock_config_instance

    mock_output_flags = MagicMock(spec=OutputFlags)
    mock_output_flags.show_raw_output = False
    mock_output_flags.show_vibe = False  # Test with vibe off for this error path
    mock_output_flags.show_kubectl = False
    mock_output_flags.model_name = "error-model"
    mock_output_flags.warn_no_output = False
    mock_output_flags.show_metrics = False
    mock_output_flags.show_streaming = True  # Added show_streaming
    mock_configure_output_flags.return_value = mock_output_flags

    mock_model_adapter_instance_ch = MagicMock()
    mock_get_model_adapter_ch.return_value = mock_model_adapter_instance_ch

    mock_model_adapter_instance_ac = MagicMock()
    mock_get_model_adapter_ac.return_value = mock_model_adapter_instance_ac

    mock_vibe_error_result = Error(error="Vibe handler failed")
    mock_handle_vibe_request.return_value = mock_vibe_error_result

    args_tuple = ("vibe", "do something that fails")
    result = await run_apply_command(
        args=args_tuple,
        show_raw_output=False,
        show_vibe=False,  # Corresponds to mock
        show_kubectl=False,
        model="error-model",  # Corresponds to mock
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=MetricsDisplayMode.NONE,
        show_streaming=True,  # Passed here
    )

    assert result == mock_vibe_error_result
    mock_logger.info.assert_any_call(
        f"Invoking 'apply' subcommand with args: {args_tuple}"
    )
    mock_logger.info.assert_any_call("Using standard vibe request handler for apply.")
    mock_logger.error.assert_any_call(
        f"Error from handle_vibe_request: {mock_vibe_error_result.error}"
    )

    mock_configure_memory_flags.assert_called_once_with(False, False)
    mock_configure_output_flags.assert_called_once_with(
        show_raw_output=False,
        show_vibe=False,
        model="error-model",
        show_kubectl=False,
        show_metrics=MetricsDisplayMode.NONE,
        show_streaming=True,  # Added show_streaming
    )
    mock_config_cls.assert_called_once()
    mock_config_instance.get_typed.assert_called_once_with("intelligent_apply", True)

    mock_handle_vibe_request.assert_called_once_with(
        request="do something that fails",
        command="apply",
        plan_prompt_func=ANY,
        summary_prompt_func=ANY,
        output_flags=mock_output_flags,
        yes=False,
    )


@patch("vibectl.execution.apply.get_model_adapter")
@patch("vibectl.subcommands.apply_cmd.Config")
@patch("vibectl.subcommands.apply_cmd.configure_output_flags")
@patch("vibectl.subcommands.apply_cmd.configure_memory_flags")
@patch("vibectl.subcommands.apply_cmd.logger")
async def test_run_apply_command_intelligent_vibe_empty_scope_response(
    mock_logger: MagicMock,
    mock_configure_memory_flags: MagicMock,
    mock_configure_output_flags: MagicMock,
    mock_config_cls: MagicMock,
    mock_get_model_adapter: MagicMock,
) -> None:
    """Test intelligent apply workflow when LLM returns empty scope response."""
    mock_config_instance = MagicMock(spec=Config)
    mock_config_instance.get_typed.side_effect = lambda key, default: {
        "intelligent_apply": True,
        "model": "claude-3.7-sonnet",
    }.get(key, default)
    mock_config_cls.return_value = mock_config_instance

    mock_output_flags = MagicMock(spec=OutputFlags)
    mock_output_flags.show_raw_output = False
    mock_output_flags.show_vibe = True
    mock_output_flags.show_kubectl = False
    mock_output_flags.model_name = "intelligent-model"
    mock_output_flags.warn_no_output = False
    mock_output_flags.show_metrics = True
    mock_output_flags.show_streaming = True  # Added show_streaming
    mock_configure_output_flags.return_value = mock_output_flags

    mock_adapter_instance = MagicMock()
    # Simulate LLM returning an empty string for file scoping
    mock_adapter_instance.execute_and_log_metrics = AsyncMock(
        return_value=("", {"some": "metric"})
    )
    mock_get_model_adapter.return_value = mock_adapter_instance

    request_str = "intelligent apply this"
    args_tuple = ("vibe", request_str)

    result = await run_apply_command(
        args=args_tuple,
        show_raw_output=False,
        show_vibe=True,
        show_kubectl=False,
        model="intelligent-model",  # Corresponds to mock
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=MetricsDisplayMode.ALL,  # Corresponds to mock
        show_streaming=True,  # Passed here
    )

    assert isinstance(result, Error)
    assert "LLM returned an empty response for file scoping" in result.error
    assert result.metrics == {"some": "metric"}

    mock_logger.info.assert_any_call(
        f"Invoking 'apply' subcommand with args: {args_tuple}"
    )
    mock_logger.info.assert_any_call(f"Planning how to: {request_str}")
    # Note: The "Starting intelligent apply workflow..." log is now in
    # execution/apply module

    mock_configure_memory_flags.assert_called_once_with(False, False)
    mock_configure_output_flags.assert_called_once_with(
        show_raw_output=False,
        show_vibe=True,
        model="intelligent-model",
        show_kubectl=False,
        show_metrics=MetricsDisplayMode.ALL,
        show_streaming=True,  # Added show_streaming
    )
    mock_config_cls.assert_called_once()
    mock_config_instance.get_typed.assert_any_call("intelligent_apply", True)
    mock_config_instance.get_typed.assert_any_call("model", "claude-3.7-sonnet")
    mock_get_model_adapter.assert_called_once_with(config=mock_config_instance)
    mock_adapter_instance.execute_and_log_metrics.assert_called_once()


# Further tests for other scenarios in intelligent apply would go here
# (e.g., file discovery errors, validation errors, correction loops, planning errors)
