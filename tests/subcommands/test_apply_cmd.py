from unittest.mock import ANY, MagicMock, patch

import pytest

from vibectl.config import Config
from vibectl.prompt import apply_output_prompt
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
        f"Error running kubectl: {mock_kubectl_error.error}"
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
@patch("vibectl.subcommands.apply_cmd.PLAN_APPLY_PROMPT", new_callable=MagicMock)
@patch("vibectl.subcommands.apply_cmd.configure_output_flags")
@patch("vibectl.subcommands.apply_cmd.configure_memory_flags")
@patch("vibectl.subcommands.apply_cmd.logger")
async def test_run_apply_command_vibe_success(
    mock_logger: MagicMock,
    mock_configure_memory_flags: MagicMock,
    mock_configure_output_flags: MagicMock,
    mock_plan_apply_prompt: MagicMock,
    mock_handle_vibe_request: MagicMock,
) -> None:
    """Test run_apply_command with 'vibe' and successful execution."""
    mock_output_flags = MagicMock(spec=OutputFlags)
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
    mock_logger.info.assert_any_call("Completed 'apply' subcommand for vibe request.")
    assert mock_logger.info.call_count == 3
    mock_logger.error.assert_not_called()

    mock_configure_memory_flags.assert_called_once_with(True, False)
    mock_configure_output_flags.assert_called_once_with(
        show_raw_output=True,
        show_vibe=False,
        model=None,
        show_kubectl=True,
        show_metrics=True,
    )
    mock_handle_vibe_request.assert_called_once()
    call_args_hvr = mock_handle_vibe_request.call_args.kwargs
    assert call_args_hvr["request"] == request_str
    assert call_args_hvr["command"] == "apply"
    assert call_args_hvr["plan_prompt_func"]() is mock_plan_apply_prompt
    assert call_args_hvr["summary_prompt_func"] == apply_output_prompt
    assert call_args_hvr["output_flags"] is mock_output_flags
    assert call_args_hvr["yes"] is False


@pytest.mark.asyncio
@patch("vibectl.subcommands.apply_cmd.handle_vibe_request")
@patch("vibectl.subcommands.apply_cmd.PLAN_APPLY_PROMPT", new_callable=MagicMock)
@patch("vibectl.subcommands.apply_cmd.configure_output_flags")
@patch("vibectl.subcommands.apply_cmd.configure_memory_flags")
@patch("vibectl.subcommands.apply_cmd.logger")
async def test_run_apply_command_vibe_error_from_handler(
    mock_logger: MagicMock,
    mock_configure_memory_flags: MagicMock,
    mock_configure_output_flags: MagicMock,
    mock_plan_apply_prompt: MagicMock,
    mock_handle_vibe_request: MagicMock,
) -> None:
    """Test run_apply_command with 'vibe' where handle_vibe_request returns Error."""
    mock_output_flags = MagicMock(spec=OutputFlags)
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
    mock_logger.error.assert_called_once_with(
        f"Error from handle_vibe_request: {mock_vibe_error_result.error}"
    )
    assert all(
        "Completed 'apply' subcommand for vibe request." not in call.args[0]
        for call in mock_logger.info.call_args_list
    )
    assert mock_logger.info.call_count == 2  # Invoking and Planning logs

    mock_configure_memory_flags.assert_called_once_with(False, True)
    mock_configure_output_flags.assert_called_once_with(
        show_raw_output=False,
        show_vibe=False,
        model=None,
        show_kubectl=False,
        show_metrics=False,
    )
    mock_handle_vibe_request.assert_called_once()
    call_args_hvr = mock_handle_vibe_request.call_args.kwargs
    assert call_args_hvr["request"] == request_str
    assert call_args_hvr["command"] == "apply"
    assert call_args_hvr["plan_prompt_func"]() is mock_plan_apply_prompt
    assert call_args_hvr["summary_prompt_func"] == apply_output_prompt
    assert call_args_hvr["output_flags"] is mock_output_flags
    assert call_args_hvr["yes"] is False
