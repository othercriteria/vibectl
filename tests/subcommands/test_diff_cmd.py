from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from vibectl.config import Config
from vibectl.prompt import diff_output_prompt
from vibectl.subcommands.diff_cmd import run_diff_command
from vibectl.types import Error, OutputFlags, Success


@pytest.mark.asyncio
@patch("vibectl.subcommands.diff_cmd.asyncio.to_thread")
@patch("vibectl.subcommands.diff_cmd.Config")
@patch("vibectl.subcommands.diff_cmd.configure_output_flags")
@patch("vibectl.subcommands.diff_cmd.configure_memory_flags")
@patch("vibectl.subcommands.diff_cmd.logger")
@patch("vibectl.subcommands.diff_cmd.handle_command_output", new_callable=AsyncMock)
async def test_run_diff_command_success_no_differences(
    mock_handle_command_output: AsyncMock,
    mock_logger: MagicMock,
    mock_configure_memory_flags: MagicMock,
    mock_configure_output_flags: MagicMock,
    mock_config_cls: MagicMock,
    mock_to_thread: MagicMock,
) -> None:
    """Test run_diff_command successful execution with no differences."""
    mock_config_instance = MagicMock(spec=Config)
    mock_config_cls.return_value = mock_config_instance

    mock_output_flags = MagicMock(spec=OutputFlags)
    mock_output_flags.show_raw = False
    mock_output_flags.show_vibe = True
    mock_output_flags.show_kubectl = False
    mock_output_flags.model_name = "test-model"
    mock_output_flags.warn_no_output = False
    mock_output_flags.show_metrics = False
    mock_configure_output_flags.return_value = mock_output_flags

    mock_kubectl_result = Success(
        message="no differences found",
        data=None,
        original_exit_code=0,
        continue_execution=True,
        metrics=None,
    )
    mock_final_result = Success(
        message="Original data, no Vibe summary due to empty processed output.",
        original_exit_code=0,
        continue_execution=False,
        # This will be set to False by the hack in run_diff_command
    )

    mock_to_thread.return_value = mock_kubectl_result
    mock_handle_command_output.return_value = mock_final_result

    result = await run_diff_command(
        resource="pod/my-pod",
        args=("-n", "default"),
        show_raw_output=False,
        show_vibe=True,
        show_kubectl=False,
        model="test-model",
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=False,
    )

    assert isinstance(result, Success)
    assert (
        result.message
        == "Original data, no Vibe summary due to empty processed output."
    )
    assert result.original_exit_code == 0
    assert not result.continue_execution  # Check the hack
    mock_logger.info.assert_any_call(
        "Invoking 'diff' subcommand with resource: pod/my-pod, args: ('-n', 'default')"
    )
    mock_logger.info.assert_any_call("Completed direct 'diff' subcommand execution.")
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

    # Check calls made by asyncio.to_thread (only run_kubectl)
    mock_to_thread.assert_called_once_with(
        ANY,  # run_kubectl function
        cmd=["diff", "pod/my-pod", "-n", "default"],
        config=mock_config_instance,
        allowed_exit_codes=(0, 1),
    )

    # Check that handle_command_output was awaited correctly
    mock_handle_command_output.assert_awaited_once_with(
        mock_kubectl_result,
        output_flags=mock_output_flags,
        summary_prompt_func=diff_output_prompt,
        command="diff",
    )


@pytest.mark.asyncio
@patch("vibectl.subcommands.diff_cmd.asyncio.to_thread")
@patch("vibectl.subcommands.diff_cmd.Config")
@patch("vibectl.subcommands.diff_cmd.configure_output_flags")
@patch("vibectl.subcommands.diff_cmd.configure_memory_flags")
@patch("vibectl.subcommands.diff_cmd.logger")
@patch("vibectl.subcommands.diff_cmd.handle_command_output", new_callable=AsyncMock)
async def test_run_diff_command_success_with_differences(
    mock_handle_command_output: AsyncMock,
    mock_logger: MagicMock,
    mock_configure_memory_flags: MagicMock,
    mock_configure_output_flags: MagicMock,
    mock_config_cls: MagicMock,
    mock_to_thread: MagicMock,
) -> None:
    """Test run_diff_command successful execution with differences found."""
    mock_config_instance = MagicMock(spec=Config)
    mock_config_cls.return_value = mock_config_instance

    mock_output_flags = MagicMock(spec=OutputFlags)
    mock_output_flags.show_raw = True
    mock_output_flags.show_vibe = False
    mock_output_flags.show_kubectl = True
    mock_output_flags.model_name = None
    mock_output_flags.warn_no_output = False
    mock_output_flags.show_metrics = True
    mock_configure_output_flags.return_value = mock_output_flags

    mock_kubectl_result = Success(
        message="differences found",
        data=None,
        original_exit_code=1,
        continue_execution=True,
        metrics=None,
    )
    mock_final_result = Success(
        message="",
        original_exit_code=1,
        continue_execution=False,
        # This will be set to False by the hack in run_diff_command
    )

    mock_to_thread.return_value = mock_kubectl_result
    mock_handle_command_output.return_value = mock_final_result

    result = await run_diff_command(
        resource="deployment/my-app",
        args=("-n", "prod", "-f", "app.yaml"),
        show_raw_output=True,
        show_vibe=False,
        show_kubectl=True,
        model=None,
        freeze_memory=True,
        unfreeze_memory=False,
        show_metrics=True,
    )

    assert isinstance(result, Success)
    assert result.message == ""
    assert result.original_exit_code == 1
    assert not result.continue_execution  # Check the hack
    mock_logger.info.assert_any_call(
        "Invoking 'diff' subcommand with resource: deployment/my-app, "
        "args: ('-n', 'prod', '-f', 'app.yaml')"
    )
    mock_logger.info.assert_any_call("Completed direct 'diff' subcommand execution.")
    assert mock_logger.info.call_count == 2
    mock_configure_memory_flags.assert_called_once_with(True, False)
    mock_configure_output_flags.assert_called_once_with(
        show_raw_output=True,
        show_vibe=False,
        model=None,
        show_kubectl=True,
        show_metrics=True,
    )
    mock_config_cls.assert_called_once()

    mock_to_thread.assert_called_once_with(
        ANY,  # run_kubectl function
        cmd=["diff", "deployment/my-app", "-n", "prod", "-f", "app.yaml"],
        config=mock_config_instance,
        allowed_exit_codes=(0, 1),
    )

    # Check that handle_command_output was awaited correctly
    mock_handle_command_output.assert_awaited_once_with(
        mock_kubectl_result,
        output_flags=mock_output_flags,
        summary_prompt_func=diff_output_prompt,
        command="diff",
    )


@pytest.mark.asyncio
@patch("vibectl.subcommands.diff_cmd.asyncio.to_thread")
@patch("vibectl.subcommands.diff_cmd.Config")
@patch("vibectl.subcommands.diff_cmd.configure_output_flags")
@patch("vibectl.subcommands.diff_cmd.configure_memory_flags")
@patch("vibectl.subcommands.diff_cmd.logger")
async def test_run_diff_command_kubectl_error(
    mock_logger: MagicMock,
    mock_configure_memory_flags: MagicMock,
    mock_configure_output_flags: MagicMock,
    mock_config_cls: MagicMock,
    mock_to_thread: MagicMock,
) -> None:
    """Test run_diff_command when kubectl returns an error."""
    mock_config_instance = MagicMock(spec=Config)
    mock_config_cls.return_value = mock_config_instance

    mock_output_flags = MagicMock(spec=OutputFlags)
    mock_output_flags.show_raw = False
    mock_output_flags.show_vibe = False
    mock_output_flags.show_kubectl = False
    mock_output_flags.model_name = None
    mock_output_flags.warn_no_output = False
    mock_output_flags.show_metrics = False
    mock_configure_output_flags.return_value = mock_output_flags

    # Mock run_kubectl to return Error
    mock_kubectl_error = Error(error="kubectl failed miserably")
    mock_to_thread.return_value = (
        mock_kubectl_error  # Only one call to to_thread in this path
    )

    result = await run_diff_command(
        resource="service/my-service",
        args=(),
        show_raw_output=False,
        show_vibe=False,
        show_kubectl=False,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=False,
    )

    assert isinstance(result, Error)
    assert result.error == "kubectl failed miserably"
    mock_logger.info.assert_called_once_with(
        "Invoking 'diff' subcommand with resource: service/my-service, args: ()"
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
        cmd=["diff", "service/my-service"],
        config=mock_config_instance,
        allowed_exit_codes=(0, 1),
    )


@pytest.mark.asyncio
@patch("vibectl.subcommands.diff_cmd.asyncio.to_thread")
@patch("vibectl.subcommands.diff_cmd.Config")
@patch("vibectl.subcommands.diff_cmd.configure_output_flags")
@patch("vibectl.subcommands.diff_cmd.configure_memory_flags")
@patch("vibectl.subcommands.diff_cmd.logger")
@patch("vibectl.subcommands.diff_cmd.handle_command_output", new_callable=AsyncMock)
async def test_run_diff_command_handle_output_error(
    mock_handle_command_output: AsyncMock,
    mock_logger: MagicMock,
    mock_configure_memory_flags: MagicMock,
    mock_configure_output_flags: MagicMock,
    mock_config_cls: MagicMock,
    mock_to_thread: MagicMock,
) -> None:
    """Test run_diff_command when handle_command_output returns an error."""
    mock_config_instance = MagicMock(spec=Config)
    mock_config_cls.return_value = mock_config_instance

    mock_output_flags = MagicMock(spec=OutputFlags)
    mock_output_flags.show_raw = False
    mock_output_flags.show_vibe = True
    mock_output_flags.show_kubectl = False
    mock_output_flags.model_name = "test-model"
    mock_output_flags.warn_no_output = False
    mock_output_flags.show_metrics = False
    mock_configure_output_flags.return_value = mock_output_flags

    mock_kubectl_as_input_to_handler = Success(
        message="diff output",
        data=None,
        original_exit_code=0,
        continue_execution=True,
        metrics=None,
    )
    mock_handler_produces_this_success_obj = Success(
        message="Original data, no Vibe summary due to empty processed output.",
        data="",
        original_exit_code=0,
        continue_execution=True,  # This will be set to False by run_diff_command's hack
        metrics=None,
    )

    mock_to_thread.return_value = mock_kubectl_as_input_to_handler
    mock_handle_command_output.return_value = mock_handler_produces_this_success_obj

    result = await run_diff_command(
        resource="configmap/my-config",
        args=("-n", "test"),
        show_raw_output=False,
        show_vibe=True,
        show_kubectl=False,
        model="test-model",
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=False,
    )

    assert isinstance(result, Success)  # It is a Success object
    assert (
        result.message
        == "Original data, no Vibe summary due to empty processed output."
    )
    assert result.original_exit_code == 0
    assert not result.continue_execution  # Due to the hack in run_diff_command

    # Verify calls
    mock_logger.info.assert_any_call(
        "Invoking 'diff' subcommand with resource: configmap/my-config, "
        "args: ('-n', 'test')"
    )
    mock_logger.info.assert_any_call("Completed direct 'diff' subcommand execution.")
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

    # Check call to to_thread (only run_kubectl)
    mock_to_thread.assert_called_once_with(
        ANY,  # run_kubectl function
        cmd=["diff", "configmap/my-config", "-n", "test"],
        config=ANY,  # mock_config_instance
        allowed_exit_codes=(0, 1),
    )

    # Check that handle_command_output was awaited correctly
    mock_handle_command_output.assert_awaited_once_with(
        mock_kubectl_as_input_to_handler,
        output_flags=mock_output_flags,
        summary_prompt_func=diff_output_prompt,
        command="diff",
    )


@pytest.mark.asyncio
@patch("vibectl.subcommands.diff_cmd.configure_output_flags")
@patch("vibectl.subcommands.diff_cmd.configure_memory_flags")
async def test_run_diff_command_vibe_missing_request(
    mock_configure_memory_flags: MagicMock,
    mock_configure_output_flags: MagicMock,
) -> None:
    """Test run_diff_command with 'vibe' resource but no request args."""
    mock_output_flags = MagicMock(spec=OutputFlags)
    mock_output_flags.show_raw = False
    mock_output_flags.show_vibe = True
    mock_output_flags.show_kubectl = False
    mock_output_flags.model_name = "test-model"
    mock_output_flags.warn_no_output = False
    mock_output_flags.show_metrics = False
    mock_configure_output_flags.return_value = mock_output_flags

    result = await run_diff_command(
        resource="vibe",
        args=(),  # No arguments provided
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
@patch("vibectl.subcommands.diff_cmd.handle_vibe_request")
@patch("vibectl.subcommands.diff_cmd.PLAN_DIFF_PROMPT", new_callable=MagicMock)
@patch("vibectl.subcommands.diff_cmd.configure_output_flags")
@patch("vibectl.subcommands.diff_cmd.configure_memory_flags")
@patch("vibectl.subcommands.diff_cmd.logger")
async def test_run_diff_command_vibe_error_from_handler(
    mock_logger: MagicMock,
    mock_configure_memory_flags: MagicMock,
    mock_configure_output_flags: MagicMock,
    mock_plan_diff_prompt: MagicMock,
    mock_handle_vibe_request: MagicMock,
) -> None:
    """Test run_diff_command with 'vibe' where handle_vibe_request returns Error."""
    mock_output_flags = MagicMock(spec=OutputFlags)
    mock_output_flags.show_raw = False
    mock_output_flags.show_vibe = True
    mock_output_flags.show_kubectl = False
    mock_output_flags.model_name = "test-diff-model"
    mock_output_flags.warn_no_output = False
    mock_output_flags.show_metrics = False
    mock_configure_output_flags.return_value = mock_output_flags

    mock_vibe_error_result = Error(error="Vibe diff failed badly")
    mock_handle_vibe_request.return_value = mock_vibe_error_result

    request_str = "this request will fail"
    args = tuple(request_str.split(" "))

    result = await run_diff_command(
        resource="vibe",
        args=args,
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
        f"Invoking 'diff' subcommand with resource: vibe, args: {args}"
    )
    mock_logger.info.assert_any_call(f"Planning how to: {request_str}")
    mock_logger.error.assert_called_once_with(
        f"Error from handle_vibe_request: {mock_vibe_error_result.error}"
    )
    # Ensure the "Completed" log is not called in error case
    assert all(
        "Completed 'diff' subcommand for vibe request." not in call.args[0]
        for call in mock_logger.info.call_args_list
    )
    # Invoking and Planning logs = 2 calls
    assert mock_logger.info.call_count == 2

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
    assert call_args_hvr["command"] == "diff"
    assert call_args_hvr["plan_prompt_func"]() is mock_plan_diff_prompt
    assert call_args_hvr["summary_prompt_func"] == diff_output_prompt
    assert call_args_hvr["output_flags"] is mock_output_flags
    assert call_args_hvr["yes"] is False
