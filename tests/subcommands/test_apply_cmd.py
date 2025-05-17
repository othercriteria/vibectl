from unittest.mock import ANY, MagicMock, patch

import pytest

from vibectl.config import Config
from vibectl.prompt import PLAN_APPLY_PROMPT, apply_output_prompt
from vibectl.subcommands.apply_cmd import run_apply_command
from vibectl.types import Error, OutputFlags, Success


@pytest.mark.asyncio
@patch("vibectl.subcommands.apply_cmd.asyncio.to_thread")
@patch("vibectl.subcommands.apply_cmd.Config")
@patch("vibectl.subcommands.apply_cmd.configure_output_flags")
@patch("vibectl.subcommands.apply_cmd.configure_memory_flags")
@patch("vibectl.subcommands.apply_cmd.logger")
async def test_run_apply_command_direct_success(
    mock_logger: MagicMock,
    mock_configure_memory_flags: MagicMock,
    mock_configure_output_flags: MagicMock,
    mock_config_cls: MagicMock,
    mock_to_thread: MagicMock,
) -> None:
    """Test run_apply_command successful direct kubectl apply execution."""
    mock_config_instance = MagicMock(spec=Config)
    mock_config_cls.return_value = mock_config_instance

    mock_output_flags = MagicMock(spec=OutputFlags)
    mock_configure_output_flags.return_value = mock_output_flags

    mock_kubectl_result = Success(
        message="applied successfully", original_exit_code=0, continue_execution=True
    )
    mock_final_result = Success(
        message="Processed: applied successfully",
        original_exit_code=0,
        continue_execution=True,
    )

    mock_to_thread.side_effect = [mock_kubectl_result, mock_final_result]

    args_tuple = ("-f", "my-deployment.yaml", "-n", "default")
    result = await run_apply_command(
        args=args_tuple,
        show_raw_output=False,
        show_vibe=True,
        show_kubectl=False,
        model="test-model",
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=False,
    )

    assert isinstance(result, Success)
    assert result.message == "Processed: applied successfully"
    assert result.original_exit_code == 0
    # No hack for continue_execution in apply_cmd
    mock_logger.info.assert_any_call(
        f"Invoking 'apply' subcommand with args: {args_tuple}"
    )
    mock_logger.info.assert_any_call("Completed direct 'apply' subcommand execution.")
    assert mock_logger.info.call_count == 2
    mock_configure_memory_flags.assert_called_once_with(False, False)
    mock_configure_output_flags.assert_called_once_with(
        show_raw_output=False,
        show_vibe=True,
        model="test-model",
        show_kubectl=False,
        show_metrics=False,
    )
    mock_config_cls.assert_called_once()

    assert mock_to_thread.call_count == 2
    mock_to_thread.assert_any_call(
        ANY,  # run_kubectl function
        cmd=["apply", "-f", "my-deployment.yaml", "-n", "default"],
        config=mock_config_instance,
        # allowed_exit_codes is not specified for apply, defaults to (0,)
    )
    mock_to_thread.assert_any_call(
        ANY,  # handle_command_output function
        output=mock_kubectl_result,
        output_flags=mock_output_flags,
        summary_prompt_func=apply_output_prompt,
    )


@pytest.mark.asyncio
@patch("vibectl.subcommands.apply_cmd.asyncio.to_thread")
@patch("vibectl.subcommands.apply_cmd.Config")
@patch("vibectl.subcommands.apply_cmd.configure_output_flags")
@patch("vibectl.subcommands.apply_cmd.configure_memory_flags")
@patch("vibectl.subcommands.apply_cmd.logger")
async def test_run_apply_command_direct_kubectl_error(
    mock_logger: MagicMock,
    mock_configure_memory_flags: MagicMock,
    mock_configure_output_flags: MagicMock,
    mock_config_cls: MagicMock,
    mock_to_thread: MagicMock,
) -> None:
    """Test run_apply_command when direct kubectl apply returns an error."""
    mock_config_instance = MagicMock(spec=Config)
    mock_config_cls.return_value = mock_config_instance

    mock_output_flags = MagicMock(spec=OutputFlags)
    mock_configure_output_flags.return_value = mock_output_flags

    mock_kubectl_error = Error(error="kubectl apply failed")
    mock_to_thread.return_value = mock_kubectl_error

    args_tuple = (
        "-f",
        "nonexistent.yaml",
    )
    result = await run_apply_command(
        args=args_tuple,
        show_raw_output=False,
        show_vibe=False,
        show_kubectl=False,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=False,
    )

    assert isinstance(result, Error)
    assert result.error == "kubectl apply failed"
    mock_logger.info.assert_called_once_with(
        f"Invoking 'apply' subcommand with args: {args_tuple}"
    )
    mock_logger.error.assert_called_once_with(
        f"Error running kubectl for direct apply: {mock_kubectl_error.error}"
    )
    mock_configure_memory_flags.assert_called_once_with(False, False)
    mock_configure_output_flags.assert_called_once_with(
        show_raw_output=False,
        show_vibe=False,
        model=None,
        show_kubectl=False,
        show_metrics=False,
    )
    mock_config_cls.assert_called_once()

    assert mock_to_thread.call_count == 1
    mock_to_thread.assert_called_once_with(
        ANY,  # run_kubectl function
        cmd=["apply", "-f", "nonexistent.yaml"],
        config=mock_config_instance,
    )


@pytest.mark.asyncio
@patch("vibectl.subcommands.apply_cmd.asyncio.to_thread")
@patch("vibectl.subcommands.apply_cmd.Config")
@patch("vibectl.subcommands.apply_cmd.configure_output_flags")
@patch("vibectl.subcommands.apply_cmd.configure_memory_flags")
@patch("vibectl.subcommands.apply_cmd.logger")
async def test_run_apply_command_direct_handle_output_error(
    mock_logger: MagicMock,
    mock_configure_memory_flags: MagicMock,
    mock_configure_output_flags: MagicMock,
    mock_config_cls: MagicMock,
    mock_to_thread: MagicMock,
) -> None:
    """Test run_apply_command with error in handle_command_output for direct apply."""
    mock_config_instance = MagicMock(spec=Config)
    mock_config_cls.return_value = mock_config_instance

    mock_output_flags = MagicMock(spec=OutputFlags)
    mock_configure_output_flags.return_value = mock_output_flags

    mock_kubectl_result = Success(
        message="apply output", original_exit_code=0, continue_execution=True
    )
    mock_handle_output_error = Error(error="Failed to process apply output")

    mock_to_thread.side_effect = [mock_kubectl_result, mock_handle_output_error]

    args_tuple = (
        "-f",
        "some.yaml",
    )
    result = await run_apply_command(
        args=args_tuple,
        show_raw_output=False,
        show_vibe=True,
        show_kubectl=False,
        model="test-model",
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=False,
    )

    assert isinstance(result, Error)
    assert result.error == "Failed to process apply output"
    mock_logger.info.assert_any_call(
        f"Invoking 'apply' subcommand with args: {args_tuple}"
    )
    mock_logger.info.assert_any_call("Completed direct 'apply' subcommand execution.")
    assert mock_logger.info.call_count == 2
    mock_logger.error.assert_not_called()
    mock_configure_memory_flags.assert_called_once_with(False, False)
    mock_configure_output_flags.assert_called_once_with(
        show_raw_output=False,
        show_vibe=True,
        model="test-model",
        show_kubectl=False,
        show_metrics=False,
    )
    mock_config_cls.assert_called_once()

    assert mock_to_thread.call_count == 2
    mock_to_thread.assert_any_call(
        ANY,  # run_kubectl function
        cmd=["apply", "-f", "some.yaml"],
        config=mock_config_instance,
    )
    mock_to_thread.assert_any_call(
        ANY,  # handle_command_output function
        output=mock_kubectl_result,
        output_flags=mock_output_flags,
        summary_prompt_func=apply_output_prompt,
    )


@pytest.mark.asyncio
@patch("vibectl.subcommands.apply_cmd.configure_output_flags")
@patch("vibectl.subcommands.apply_cmd.configure_memory_flags")
async def test_run_apply_command_vibe_missing_request(
    mock_configure_memory_flags: MagicMock,
    mock_configure_output_flags: MagicMock,
) -> None:
    """Test run_apply_command with 'vibe' but no request args."""
    mock_output_flags = MagicMock(spec=OutputFlags)
    mock_configure_output_flags.return_value = mock_output_flags

    result = await run_apply_command(
        args=("vibe",),  # Only "vibe" provided
        show_raw_output=False,
        show_vibe=True,
        show_kubectl=False,
        model="test-model",
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=False,
    )

    assert isinstance(result, Error)
    assert "Missing request after 'vibe' command" in result.error
    mock_configure_memory_flags.assert_called_once_with(False, False)
    mock_configure_output_flags.assert_called_once_with(
        show_raw_output=False,
        show_vibe=True,
        model="test-model",
        show_kubectl=False,
        show_metrics=False,
    )


@pytest.mark.asyncio
@patch("vibectl.subcommands.apply_cmd.handle_vibe_request")
@patch("vibectl.subcommands.apply_cmd.get_model_adapter")
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
    mock_get_model_adapter_apply_cmd: MagicMock,
    mock_handle_vibe_request: MagicMock,
) -> None:
    """Test run_apply_command with non-intelligent 'vibe' and successful execution."""
    mock_config_instance = MagicMock(spec=Config)
    mock_config_instance.get_typed.return_value = False
    mock_config_cls.return_value = mock_config_instance

    # Configure the new mock for apply_cmd.get_model_adapter
    mock_adapter_instance_for_apply_cmd = MagicMock()
    mock_adapter_instance_for_apply_cmd.get_model.return_value = (
        MagicMock()
    )  # Simulate successful model get
    mock_get_model_adapter_apply_cmd.return_value = mock_adapter_instance_for_apply_cmd

    mock_adapter_instance_ch = MagicMock()
    mock_adapter_instance_ch.get_model.return_value = MagicMock()
    mock_get_model_adapter_ch.return_value = mock_adapter_instance_ch

    mock_output_flags = MagicMock(spec=OutputFlags)
    mock_output_flags.model_name = "default-test-model"
    mock_configure_output_flags.return_value = mock_output_flags

    mock_vibe_success_result = Success(message="Vibe apply successful")
    mock_handle_vibe_request.return_value = mock_vibe_success_result

    request_str = "apply this cool manifest"
    args_tuple = ("vibe", *request_str.split(" "))

    result = await run_apply_command(
        args=args_tuple,
        show_raw_output=True,
        show_vibe=False,
        show_kubectl=True,
        model=None,
        freeze_memory=True,
        unfreeze_memory=False,
        show_metrics=True,
    )

    assert result is mock_vibe_success_result
    mock_logger.info.assert_any_call(
        f"Invoking 'apply' subcommand with args: {args_tuple}"
    )
    mock_logger.info.assert_any_call(f"Planning how to: {request_str}")
    mock_logger.info.assert_any_call("Using standard vibe request handler for apply.")
    mock_logger.info.assert_any_call(
        "Completed 'apply' subcommand for standard vibe request."
    )
    assert mock_logger.info.call_count == 4
    mock_logger.error.assert_not_called()

    mock_configure_memory_flags.assert_called_once_with(True, False)
    mock_configure_output_flags.assert_called_once_with(
        show_raw_output=True,
        show_vibe=False,
        model=None,
        show_kubectl=True,
        show_metrics=True,
    )
    mock_config_cls.assert_called_once()
    mock_config_instance.get_typed.assert_called_once_with("intelligent_apply", True)

    mock_handle_vibe_request.assert_called_once()
    call_args_hvr = mock_handle_vibe_request.call_args.kwargs
    assert call_args_hvr["request"] == request_str
    assert call_args_hvr["command"] == "apply"
    assert call_args_hvr["plan_prompt_func"]() == PLAN_APPLY_PROMPT
    assert call_args_hvr["summary_prompt_func"] == apply_output_prompt
    assert call_args_hvr["output_flags"] is mock_output_flags
    assert call_args_hvr["yes"] is False


@pytest.mark.asyncio
@patch("vibectl.subcommands.apply_cmd.handle_vibe_request")
@patch("vibectl.subcommands.apply_cmd.get_model_adapter")
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
    mock_get_model_adapter_apply_cmd: MagicMock,
    mock_handle_vibe_request: MagicMock,
) -> None:
    """Test non-intelligent vibe run_apply_command on handle_vibe_request Error."""
    mock_config_instance = MagicMock(spec=Config)
    mock_config_instance.get_typed.return_value = False
    mock_config_cls.return_value = mock_config_instance

    # Configure the new mock for apply_cmd.get_model_adapter
    mock_adapter_instance_for_apply_cmd = MagicMock()
    mock_adapter_instance_for_apply_cmd.get_model.return_value = (
        MagicMock()
    )  # Simulate successful model get
    mock_get_model_adapter_apply_cmd.return_value = mock_adapter_instance_for_apply_cmd

    # Configure mock for get_model_adapter in command_handler
    # (potentially unused but kept for safety)
    # TODO: Remove this mock if it's not used in the test
    mock_adapter_instance_ch = MagicMock()
    mock_adapter_instance_ch.get_model.return_value = MagicMock()
    mock_get_model_adapter_ch.return_value = mock_adapter_instance_ch

    mock_output_flags = MagicMock(spec=OutputFlags)
    mock_output_flags.model_name = "default-test-model"
    mock_configure_output_flags.return_value = mock_output_flags

    mock_vibe_error_result = Error(error="Vibe apply failed")
    mock_handle_vibe_request.return_value = mock_vibe_error_result

    request_str = "this apply request will fail"
    args_tuple = ("vibe", *request_str.split(" "))

    result = await run_apply_command(
        args=args_tuple,
        show_raw_output=False,
        show_vibe=False,
        show_kubectl=False,
        model=None,
        freeze_memory=False,
        unfreeze_memory=True,
        show_metrics=False,
    )

    assert result is mock_vibe_error_result

    mock_logger.info.assert_any_call(
        f"Invoking 'apply' subcommand with args: {args_tuple}"
    )
    mock_logger.info.assert_any_call(f"Planning how to: {request_str}")
    mock_logger.info.assert_any_call("Using standard vibe request handler for apply.")
    mock_logger.error.assert_called_once_with(
        f"Error from handle_vibe_request: {mock_vibe_error_result.error}"
    )
    assert all(
        "Completed 'apply' subcommand for vibe request." not in call.args[0]
        for call in mock_logger.info.call_args_list
    )
    assert (
        mock_logger.info.call_count == 3
    )  # Invoking, Planning, Using standard handler logs

    mock_configure_memory_flags.assert_called_once_with(False, True)
    mock_configure_output_flags.assert_called_once_with(
        show_raw_output=False,
        show_vibe=False,
        model=None,
        show_kubectl=False,
        show_metrics=False,
    )
    mock_config_cls.assert_called_once()
    mock_config_instance.get_typed.assert_called_once_with("intelligent_apply", True)

    mock_handle_vibe_request.assert_called_once()
    call_args_hvr = mock_handle_vibe_request.call_args.kwargs
    assert call_args_hvr["request"] == request_str
    assert call_args_hvr["command"] == "apply"
    assert call_args_hvr["plan_prompt_func"]() == PLAN_APPLY_PROMPT
    assert call_args_hvr["summary_prompt_func"] == apply_output_prompt
    assert call_args_hvr["output_flags"] is mock_output_flags
    assert call_args_hvr["yes"] is False


@pytest.mark.asyncio
@patch("vibectl.subcommands.apply_cmd.asyncio.to_thread")
@patch("vibectl.subcommands.apply_cmd.get_model_adapter")
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
    mock_to_thread: MagicMock,
) -> None:
    """Test intelligent apply vibe mode fails early on LLM empty scope response."""
    mock_config_instance = MagicMock(spec=Config)
    # Ensure intelligent_apply is True
    mock_config_instance.get_typed.side_effect = (
        lambda key, default: True if key == "intelligent_apply" else default
    )
    mock_config_cls.return_value = mock_config_instance

    mock_output_flags = MagicMock(spec=OutputFlags)
    mock_configure_output_flags.return_value = mock_output_flags

    # Mock the model adapter and its execute_and_log_metrics method
    mock_model_adapter_instance = MagicMock()
    mock_get_model_adapter.return_value = mock_model_adapter_instance

    # Simulate empty LLM response for the first call (file scoping)
    # model_adapter.execute_and_log_metrics is called via asyncio.to_thread
    # The actual function run in the thread is
    # model_adapter_instance.execute_and_log_metrics
    # So we mock its direct return value.
    mock_model_adapter_instance.execute_and_log_metrics.return_value = (
        None,
        {"tokens_in": 10, "tokens_out": 0, "latency_ms": 100.0},
    )  # Empty response_text

    mock_to_thread.side_effect = lambda func, *args, **kwargs: func(*args, **kwargs)

    request_str = "intelligent apply this"
    args_tuple = ("vibe", *request_str.split(" "))

    result = await run_apply_command(
        args=args_tuple,
        show_raw_output=False,
        show_vibe=True,
        show_kubectl=False,
        model="test-intelligent-model",
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=True,
    )

    assert isinstance(result, Error)
    assert result.error == "LLM returned an empty response for file scoping."
    assert result.metrics is not None  # Metrics should still be passed through

    mock_logger.info.assert_any_call(
        f"Invoking 'apply' subcommand with args: {args_tuple}"
    )
    mock_logger.info.assert_any_call(f"Planning how to: {request_str}")
    mock_logger.info.assert_any_call("Starting intelligent apply workflow...")
    mock_logger.error.assert_any_call(
        "LLM returned an empty response for file scoping."
    )

    mock_configure_memory_flags.assert_called_once_with(False, False)
    mock_configure_output_flags.assert_called_once_with(
        show_raw_output=False,
        show_vibe=True,
        model="test-intelligent-model",
        show_kubectl=False,
        show_metrics=True,
    )
    mock_config_cls.assert_called_once()
    mock_config_instance.get_typed.assert_any_call("intelligent_apply", True)

    # Check that get_model_adapter was called
    mock_get_model_adapter.assert_called_once_with(config=mock_config_instance)

    # Check that execute_and_log_metrics was called (via to_thread)
    # The actual call to the threaded function is what we care about
    mock_model_adapter_instance.execute_and_log_metrics.assert_called_once()
    call_args_elam = (
        mock_model_adapter_instance.execute_and_log_metrics.call_args.kwargs
    )
    assert call_args_elam["response_model"].__name__ == "ApplyFileScopeResponse"
