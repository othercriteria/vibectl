from unittest.mock import ANY, MagicMock, patch

import pytest

from vibectl.config import Config
from vibectl.prompt import diff_output_prompt
from vibectl.subcommands.diff_cmd import run_diff_command
from vibectl.types import Error, OutputFlags, Success

# TODO: Add comprehensive tests to achieve 100% coverage.


@pytest.mark.asyncio
@patch("vibectl.subcommands.diff_cmd.asyncio.to_thread")
@patch("vibectl.subcommands.diff_cmd.Config")
@patch("vibectl.subcommands.diff_cmd.configure_output_flags")
@patch("vibectl.subcommands.diff_cmd.configure_memory_flags")
@patch("vibectl.subcommands.diff_cmd.logger")
async def test_run_diff_command_success_no_differences(
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
    mock_configure_output_flags.return_value = mock_output_flags

    # Mock run_kubectl to return Success with original_exit_code 0
    mock_kubectl_result = Success(
        message="no differences found", original_exit_code=0, continue_execution=True
    )
    # Mock handle_command_output
    mock_final_result = Success(
        message="Processed: no differences found",
        original_exit_code=0,
        continue_execution=True,
    )

    # Configure asyncio.to_thread to return the mocked results in sequence
    mock_to_thread.side_effect = [mock_kubectl_result, mock_final_result]

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
    assert result.message == "Processed: no differences found"
    assert result.original_exit_code == 0
    assert not result.continue_execution  # Check the hack
    mock_logger.info.assert_called_once_with(
        "Invoking 'diff' subcommand with resource: pod/my-pod, args: ('-n', 'default')"
    )
    mock_configure_memory_flags.assert_called_once_with(False, False)
    mock_configure_output_flags.assert_called_once_with(
        show_raw_output=False,
        show_vibe=True,
        model="test-model",
        show_kubectl=False,
        show_metrics=False,
    )
    mock_config_cls.assert_called_once()

    # Check calls made by asyncio.to_thread
    assert mock_to_thread.call_count == 2
    # First call is run_kubectl
    mock_to_thread.assert_any_call(
        ANY,  # run_kubectl function
        cmd=["diff", "pod/my-pod", "-n", "default"],
        config=mock_config_instance,
        allowed_exit_codes=(0, 1),
    )
    # Second call is handle_command_output
    mock_to_thread.assert_any_call(
        ANY,  # handle_command_output function
        output=mock_kubectl_result,
        output_flags=mock_output_flags,
        summary_prompt_func=diff_output_prompt,
    )


@pytest.mark.asyncio
@patch("vibectl.subcommands.diff_cmd.asyncio.to_thread")
@patch("vibectl.subcommands.diff_cmd.Config")
@patch("vibectl.subcommands.diff_cmd.configure_output_flags")
@patch("vibectl.subcommands.diff_cmd.configure_memory_flags")
@patch("vibectl.subcommands.diff_cmd.logger")
async def test_run_diff_command_success_with_differences(
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
    mock_configure_output_flags.return_value = mock_output_flags

    # Mock run_kubectl to return Success with original_exit_code 1
    mock_kubectl_result = Success(
        message="differences found", original_exit_code=1, continue_execution=True
    )
    # Mock handle_command_output
    mock_final_result = Success(
        message="Processed: differences found",
        original_exit_code=1,
        continue_execution=True,
    )

    mock_to_thread.side_effect = [mock_kubectl_result, mock_final_result]

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
    assert result.message == "Processed: differences found"
    assert result.original_exit_code == 1
    assert not result.continue_execution  # Check the hack
    mock_logger.info.assert_called_once_with(
        "Invoking 'diff' subcommand with resource: deployment/my-app, "
        "args: ('-n', 'prod', '-f', 'app.yaml')"
    )
    mock_configure_memory_flags.assert_called_once_with(True, False)
    mock_configure_output_flags.assert_called_once_with(
        show_raw_output=True,
        show_vibe=False,
        model=None,
        show_kubectl=True,
        show_metrics=True,
    )
    mock_config_cls.assert_called_once()

    assert mock_to_thread.call_count == 2
    mock_to_thread.assert_any_call(
        ANY,  # run_kubectl function
        cmd=["diff", "deployment/my-app", "-n", "prod", "-f", "app.yaml"],
        config=mock_config_instance,
        allowed_exit_codes=(0, 1),
    )
    mock_to_thread.assert_any_call(
        ANY,  # handle_command_output function
        output=mock_kubectl_result,
        output_flags=mock_output_flags,
        summary_prompt_func=diff_output_prompt,
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

    mock_output_flags = MagicMock(
        spec=OutputFlags
    )  # Not strictly needed for this test path but good for consistency
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
    # handle_command_output should not be called
    # (Can't directly assert not_called with side_effect list, but count implies it)


@pytest.mark.asyncio
@patch("vibectl.subcommands.diff_cmd.asyncio.to_thread")
@patch("vibectl.subcommands.diff_cmd.Config")
@patch("vibectl.subcommands.diff_cmd.configure_output_flags")
@patch("vibectl.subcommands.diff_cmd.configure_memory_flags")
@patch("vibectl.subcommands.diff_cmd.logger")
async def test_run_diff_command_handle_output_error(
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
    mock_configure_output_flags.return_value = mock_output_flags

    # Mock run_kubectl to return Success
    mock_kubectl_result = Success(message="kubectl success", original_exit_code=0)
    # Mock handle_command_output to return Error
    mock_handle_output_error = Error(error="handle_output failed")

    mock_to_thread.side_effect = [mock_kubectl_result, mock_handle_output_error]

    result = await run_diff_command(
        resource="configmap/my-cm",
        args=(),
        show_raw_output=False,
        show_vibe=True,
        show_kubectl=False,
        model="test-model",
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=False,
    )

    assert isinstance(result, Error)
    assert result.error == "handle_output failed"
    mock_logger.info.assert_called_once_with(
        "Invoking 'diff' subcommand with resource: configmap/my-cm, args: ()"
    )
    # logger.error should NOT be called here, as the error is from
    # handle_command_output, not kubectl
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
        cmd=["diff", "configmap/my-cm"],
        config=mock_config_instance,
        allowed_exit_codes=(0, 1),
    )
    mock_to_thread.assert_any_call(
        ANY,  # handle_command_output function
        output=mock_kubectl_result,
        output_flags=mock_output_flags,
        summary_prompt_func=diff_output_prompt,
    )


# Remove placeholder test
# @pytest.mark.asyncio
# async def test_placeholder():
#    """Placeholder test."""
#    assert True
