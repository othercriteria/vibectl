"""Tests for vibectl.subcommands.rollout_cmd."""

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vibectl.config import DEFAULT_CONFIG
from vibectl.k8s_utils import run_kubectl
from vibectl.subcommands.rollout_cmd import (
    rollout_general_prompt,
    rollout_history_prompt,
    rollout_status_prompt,
    run_rollout_command,
)
from vibectl.types import (
    Error,
    ExecutionMode,
    MetricsDisplayMode,
    OutputFlags,
    PromptFragments,
    Result,
    Success,
    SystemFragments,
    UserFragments,
)


# Fixture for default OutputFlags
@pytest.fixture
def default_rollout_output_flags() -> OutputFlags:
    return OutputFlags(
        show_raw_output=bool(DEFAULT_CONFIG.get("show_raw_output", False)),
        show_vibe=bool(DEFAULT_CONFIG.get("show_vibe", True)),
        warn_no_output=bool(DEFAULT_CONFIG.get("warn_no_output", True)),
        model_name=str(DEFAULT_CONFIG.get("model", "default_model_name_fixture")),
        show_metrics=MetricsDisplayMode.from_value(
            str(DEFAULT_CONFIG.get("show_metrics", "none"))
        ),
        show_kubectl=bool(DEFAULT_CONFIG.get("show_kubectl", False)),
        warn_no_proxy=bool(DEFAULT_CONFIG.get("warn_no_proxy", True)),
    )


# Fixture for a dummy summary_prompt_func
@pytest.fixture
def dummy_rollout_summary_prompt_func() -> MagicMock:
    mock_func = MagicMock(
        spec=lambda config: PromptFragments((SystemFragments([]), UserFragments([])))
    )
    mock_func.__name__ = (
        "dummy_rollout_summary_prompt_func"  # To help with debugging if needed
    )
    return mock_func


@pytest.mark.asyncio
async def test_run_rollout_command_successful_flow(
    default_rollout_output_flags: OutputFlags,
    dummy_rollout_summary_prompt_func: MagicMock,
) -> None:
    """Test success flow of run_rollout_command, mocking underlying threaded calls."""

    rollout_subcommand = "history"
    resource_type_or_name = "deployment/test-deploy"
    args_tuple = ("--revision=1",)
    expected_kubectl_cmd_list = [
        "rollout",
        rollout_subcommand,
        resource_type_or_name,
        *args_tuple,
    ]

    mock_kubectl_output = Success(data="kubectl history data")
    # expected_final_result now comes from the run_rollout_command itself,
    # not handle_command_output directly as handle_command_output is awaited
    # but its direct return isn't used by run_rollout_command's final return.
    # The final return of run_rollout_command is a generic success if
    # all steps complete.
    expected_final_result = Success(
        message=(
            f"Completed 'rollout' subcommand: {rollout_subcommand} for "
            f"resource: {resource_type_or_name}"
        )
    )

    async def mock_to_thread_side_effect(
        func_to_run_in_thread: Callable, *args_for_func: Any, **kwargs_for_func: Any
    ) -> Result | None:
        if func_to_run_in_thread is run_kubectl:
            assert args_for_func[0] == expected_kubectl_cmd_list
            return mock_kubectl_output
        # handle_command_output is no longer called via to_thread
        raise AssertionError(
            "asyncio.to_thread called with unexpected function: "
            f"{func_to_run_in_thread}"
        )

    with (
        patch(
            "vibectl.subcommands.rollout_cmd.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=mock_to_thread_side_effect,
        ) as mock_async_to_thread,
        patch(
            "vibectl.subcommands.rollout_cmd.handle_command_output",
            new_callable=AsyncMock,
            return_value=Success(message="Mocked output from handle_command_output"),
        ) as mock_handle_command_output_direct,
        patch(
            "vibectl.subcommands.rollout_cmd.configure_output_flags",
            return_value=default_rollout_output_flags,
        ) as mock_configure_output,
        patch(
            "vibectl.subcommands.rollout_cmd.configure_memory_flags"
        ) as mock_configure_memory,
    ):
        result = await run_rollout_command(
            subcommand=rollout_subcommand,
            resource=resource_type_or_name,
            args=args_tuple,
            show_raw_output=default_rollout_output_flags.show_raw_output,
            show_vibe=default_rollout_output_flags.show_vibe,
            model=default_rollout_output_flags.model_name,
            show_kubectl=default_rollout_output_flags.show_kubectl,
            freeze_memory=False,
            unfreeze_memory=False,
            show_streaming=True,
        )

        assert result == expected_final_result
        assert (
            mock_async_to_thread.call_count == 1
        )  # Only run_kubectl is called via to_thread
        mock_configure_output.assert_called_once()
        mock_configure_memory.assert_called_once()
        mock_handle_command_output_direct.assert_called_once_with(
            output=mock_kubectl_output,
            output_flags=default_rollout_output_flags,
            summary_prompt_func=rollout_history_prompt,
        )


@pytest.mark.asyncio
async def test_run_rollout_status(default_rollout_output_flags: OutputFlags) -> None:
    """Test normal execution of the rollout status command via run_rollout_command."""
    mock_kubectl_output = Success(data="deployment/nginx successfully rolled out")
    resource_type_or_name = "deployment/nginx"
    args_tuple = ("-n", "default")
    subcommand = "status"
    expected_kubectl_cmd_list = [
        "rollout",
        subcommand,
        resource_type_or_name,
        *args_tuple,
    ]
    expected_final_result = Success(
        message=(
            f"Completed 'rollout' subcommand: {subcommand} for "
            f"resource: {resource_type_or_name}"
        )
    )

    async def mock_to_thread_side_effect(
        func: Callable, *args_to_func: Any, **kwargs_to_func: Any
    ) -> Result | None:
        if func is run_kubectl:
            assert args_to_func[0] == expected_kubectl_cmd_list
            return mock_kubectl_output
        raise AssertionError(
            f"asyncio.to_thread called with unexpected function: {func}"
        )

    with (
        patch(
            "vibectl.subcommands.rollout_cmd.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=mock_to_thread_side_effect,
        ) as mock_async_to_thread,
        patch(
            "vibectl.subcommands.rollout_cmd.handle_command_output",
            new_callable=AsyncMock,
            return_value=Success(message="Mocked handler output"),
        ) as mock_handle_output_direct,
        patch(
            "vibectl.subcommands.rollout_cmd.configure_output_flags",
            return_value=default_rollout_output_flags,
        ),
        patch("vibectl.subcommands.rollout_cmd.configure_memory_flags"),
    ):
        result = await run_rollout_command(
            subcommand="status",
            resource="deployment/nginx",
            args=("-n", "default"),
            show_raw_output=default_rollout_output_flags.show_raw_output,
            show_vibe=default_rollout_output_flags.show_vibe,
            model=default_rollout_output_flags.model_name,
            show_kubectl=default_rollout_output_flags.show_kubectl,
            freeze_memory=False,
            unfreeze_memory=False,
            show_streaming=True,
        )
        assert mock_async_to_thread.call_count == 1  # Only run_kubectl
        assert result == expected_final_result
        mock_handle_output_direct.assert_called_once_with(
            output=mock_kubectl_output,
            output_flags=default_rollout_output_flags,
            summary_prompt_func=rollout_status_prompt,
        )


@pytest.mark.asyncio
async def test_run_rollout_history(default_rollout_output_flags: OutputFlags) -> None:
    """Test normal execution of the rollout history command via run_rollout_command."""
    mock_kubectl_output = Success(data="REVISION\\n1\\n2")
    resource_type_or_name = "deployment/nginx"
    args_tuple = ()
    subcommand = "history"
    expected_kubectl_cmd_list = [
        "rollout",
        subcommand,
        resource_type_or_name,
        *args_tuple,
    ]
    expected_final_result = Success(
        message=(
            f"Completed 'rollout' subcommand: {subcommand} for "
            f"resource: {resource_type_or_name}"
        )
    )

    async def mock_to_thread_side_effect(
        func: Callable, *args_to_func: Any, **kwargs_to_func: Any
    ) -> Result | None:
        if func is run_kubectl:
            assert args_to_func[0] == expected_kubectl_cmd_list
            return mock_kubectl_output
        # handle_command_output is no longer called via to_thread
        raise AssertionError(
            f"asyncio.to_thread called with unexpected function: {func}"
        )

    with (
        patch(
            "vibectl.subcommands.rollout_cmd.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=mock_to_thread_side_effect,
        ) as mock_async_to_thread,
        patch(
            "vibectl.subcommands.rollout_cmd.handle_command_output",
            new_callable=AsyncMock,
            return_value=Success(message="Mocked handler output"),
        ) as mock_handle_output_direct,
        patch(
            "vibectl.subcommands.rollout_cmd.configure_output_flags",
            return_value=default_rollout_output_flags,
        ),
        patch("vibectl.subcommands.rollout_cmd.configure_memory_flags"),
    ):
        result = await run_rollout_command(
            subcommand="history",
            resource="deployment/nginx",
            args=(),
            show_raw_output=default_rollout_output_flags.show_raw_output,
            show_vibe=default_rollout_output_flags.show_vibe,
            model=default_rollout_output_flags.model_name,
            show_kubectl=default_rollout_output_flags.show_kubectl,
            freeze_memory=False,
            unfreeze_memory=False,
            show_streaming=True,
        )
        assert mock_async_to_thread.call_count == 1  # Only run_kubectl
        assert result == expected_final_result
        mock_handle_output_direct.assert_called_once_with(
            output=mock_kubectl_output,
            output_flags=default_rollout_output_flags,
            summary_prompt_func=rollout_history_prompt,
        )


@pytest.mark.asyncio
async def test_run_rollout_undo_with_confirmation(
    default_rollout_output_flags: OutputFlags,
) -> None:
    """Test rollout undo command with user confirmation via run_rollout_command."""
    mock_kubectl_output = Success(data="deployment.apps/nginx rolled back")
    resource_type_or_name = "deployment/nginx"
    args_tuple = ("--to-revision=2",)
    subcommand = "undo"
    expected_kubectl_cmd_list = [
        "rollout",
        subcommand,
        resource_type_or_name,
        *args_tuple,
    ]
    expected_final_result = Success(
        message=(
            f"Completed 'rollout' subcommand: {subcommand} for "
            f"resource: {resource_type_or_name}"
        )
    )

    async def mock_to_thread_side_effect(
        func: Callable, *args_to_func: Any, **kwargs_to_func: Any
    ) -> Result | None:
        if func is run_kubectl:
            assert args_to_func[0] == expected_kubectl_cmd_list
            return mock_kubectl_output
        # handle_command_output is no longer called via to_thread
        raise AssertionError(
            f"asyncio.to_thread called with unexpected function: {func}"
        )

    with (
        patch(
            "vibectl.subcommands.rollout_cmd.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=mock_to_thread_side_effect,
        ) as mock_async_to_thread,
        patch("click.confirm", return_value=True) as mock_click_confirm,
        patch(
            "vibectl.subcommands.rollout_cmd.handle_command_output",
            new_callable=AsyncMock,
            return_value=Success(message="Mocked handler output"),
        ) as mock_handle_output_direct,
        patch(
            "vibectl.subcommands.rollout_cmd.configure_output_flags",
            return_value=default_rollout_output_flags,
        ),
        patch("vibectl.subcommands.rollout_cmd.configure_memory_flags"),
    ):
        result = await run_rollout_command(
            subcommand="undo",
            resource="deployment/nginx",
            args=("--to-revision=2",),
            show_raw_output=default_rollout_output_flags.show_raw_output,
            show_vibe=default_rollout_output_flags.show_vibe,
            model=default_rollout_output_flags.model_name,
            show_kubectl=default_rollout_output_flags.show_kubectl,
            freeze_memory=False,
            unfreeze_memory=False,
            show_streaming=True,
        )
        mock_click_confirm.assert_called_once()
        assert mock_async_to_thread.call_count == 1  # Only run_kubectl
        mock_handle_output_direct.assert_called_once_with(
            output=mock_kubectl_output,
            output_flags=default_rollout_output_flags,
            summary_prompt_func=rollout_general_prompt,
        )
        assert result == expected_final_result


@pytest.mark.asyncio
async def test_run_rollout_undo_auto_mode(
    default_rollout_output_flags: OutputFlags,
) -> None:
    """Test rollout undo command when execution mode is AUTO (non-interactive)."""
    mock_kubectl_output = Success(data="deployment.apps/nginx rolled back")
    resource_type_or_name = "deployment/nginx"
    args_tuple = ("--to-revision=2",)
    subcommand = "undo"
    expected_kubectl_cmd_list = [
        "rollout",
        subcommand,
        resource_type_or_name,
        *args_tuple,
    ]
    expected_final_result = Success(
        message=(
            f"Completed 'rollout' subcommand: {subcommand} for "
            f"resource: {resource_type_or_name}"
        )
    )

    async def mock_to_thread_side_effect(
        func: Callable, *args_to_func: Any, **kwargs_to_func: Any
    ) -> Result | None:
        if func is run_kubectl:
            assert args_to_func[0] == expected_kubectl_cmd_list
            return mock_kubectl_output
        # handle_command_output is no longer called via to_thread
        raise AssertionError(
            f"asyncio.to_thread called with unexpected function: {func}"
        )

    with (
        patch(
            "vibectl.subcommands.rollout_cmd.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=mock_to_thread_side_effect,
        ) as mock_async_to_thread,
        patch(
            "vibectl.subcommands.rollout_cmd.determine_execution_mode",
            return_value=ExecutionMode.AUTO,
        ),
        patch("click.confirm") as mock_click_confirm,
        patch(
            "vibectl.subcommands.rollout_cmd.handle_command_output",
            new_callable=AsyncMock,
            return_value=Success(message="Mocked handler output"),
        ) as mock_handle_output_direct,
        patch(
            "vibectl.subcommands.rollout_cmd.configure_output_flags",
            return_value=default_rollout_output_flags,
        ),
        patch("vibectl.subcommands.rollout_cmd.configure_memory_flags"),
    ):
        result = await run_rollout_command(
            subcommand="undo",
            resource="deployment/nginx",
            args=("--to-revision=2",),
            show_raw_output=default_rollout_output_flags.show_raw_output,
            show_vibe=default_rollout_output_flags.show_vibe,
            model=default_rollout_output_flags.model_name,
            show_kubectl=default_rollout_output_flags.show_kubectl,
            freeze_memory=False,
            unfreeze_memory=False,
            show_streaming=True,
        )
        mock_click_confirm.assert_not_called()
        assert mock_async_to_thread.call_count == 1  # Only run_kubectl
        mock_handle_output_direct.assert_called_once_with(
            output=mock_kubectl_output,
            output_flags=default_rollout_output_flags,
            summary_prompt_func=rollout_general_prompt,
        )
        assert result == expected_final_result


@pytest.mark.asyncio
async def test_run_rollout_undo_cancelled(
    default_rollout_output_flags: OutputFlags,
) -> None:
    """Test rollout undo when user cancels confirmation via run_rollout_command."""
    expected_cancellation_result_message = "Operation cancelled"

    with (
        patch(
            "vibectl.subcommands.rollout_cmd.asyncio.to_thread", new_callable=AsyncMock
        ) as mock_async_to_thread,
        patch("click.confirm", return_value=False) as mock_click_confirm,
        patch("vibectl.subcommands.rollout_cmd.console_manager") as mock_console,
        patch(
            "vibectl.subcommands.rollout_cmd.handle_command_output",
            new_callable=AsyncMock,
            return_value=Success(message="Mocked handler output"),
        ) as mock_handle_output_direct,
        patch(
            "vibectl.subcommands.rollout_cmd.configure_output_flags",
            return_value=default_rollout_output_flags,
        ),
        patch("vibectl.subcommands.rollout_cmd.configure_memory_flags"),
    ):
        result = await run_rollout_command(
            subcommand="undo",
            resource="deployment/nginx",
            args=(),
            show_raw_output=default_rollout_output_flags.show_raw_output,
            show_vibe=default_rollout_output_flags.show_vibe,
            model=default_rollout_output_flags.model_name,
            show_kubectl=default_rollout_output_flags.show_kubectl,
            freeze_memory=False,
            unfreeze_memory=False,
            show_streaming=True,
        )
        mock_click_confirm.assert_called_once()
        mock_async_to_thread.assert_not_called()
        mock_console.print_note.assert_called_once_with(
            expected_cancellation_result_message
        )
        assert isinstance(result, Success)
        assert result.message == expected_cancellation_result_message
        mock_handle_output_direct.assert_not_called()


@pytest.mark.asyncio
async def test_run_rollout_restart(default_rollout_output_flags: OutputFlags) -> None:
    """Test normal execution of rollout restart command via run_rollout_command."""
    mock_kubectl_output = Success(data="deployment.apps/nginx restarted")
    resource_type_or_name = "deployment/nginx"
    args_tuple = ()
    subcommand = "restart"
    expected_kubectl_cmd_list = [
        "rollout",
        subcommand,
        resource_type_or_name,
        *args_tuple,
    ]
    expected_final_result = Success(
        message=(
            f"Completed 'rollout' subcommand: {subcommand} for "
            f"resource: {resource_type_or_name}"
        )
    )

    async def mock_to_thread_side_effect(
        func: Callable, *args_to_func: Any, **kwargs_to_func: Any
    ) -> Result | None:
        if func is run_kubectl:
            assert args_to_func[0] == expected_kubectl_cmd_list
            return mock_kubectl_output
        # handle_command_output is no longer called via to_thread
        raise AssertionError(
            f"asyncio.to_thread called with unexpected function: {func}"
        )

    with (
        patch(
            "vibectl.subcommands.rollout_cmd.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=mock_to_thread_side_effect,
        ) as mock_async_to_thread,
        patch(
            "vibectl.subcommands.rollout_cmd.handle_command_output",
            new_callable=AsyncMock,
            return_value=Success(message="Mocked handler output"),
        ) as mock_handle_output_direct,
        patch(
            "vibectl.subcommands.rollout_cmd.configure_output_flags",
            return_value=default_rollout_output_flags,
        ),
        patch("vibectl.subcommands.rollout_cmd.configure_memory_flags"),
    ):
        result = await run_rollout_command(
            subcommand="restart",
            resource="deployment/nginx",
            args=(),
            show_raw_output=default_rollout_output_flags.show_raw_output,
            show_vibe=default_rollout_output_flags.show_vibe,
            model=default_rollout_output_flags.model_name,
            show_kubectl=default_rollout_output_flags.show_kubectl,
            freeze_memory=False,
            unfreeze_memory=False,
            show_streaming=True,
        )
        assert mock_async_to_thread.call_count == 1  # Only run_kubectl
        assert result == expected_final_result
        mock_handle_output_direct.assert_called_once_with(
            output=mock_kubectl_output,
            output_flags=default_rollout_output_flags,
            summary_prompt_func=rollout_general_prompt,
        )


@pytest.mark.asyncio
async def test_run_rollout_pause(default_rollout_output_flags: OutputFlags) -> None:
    """Test normal execution of rollout pause command via run_rollout_command."""
    mock_kubectl_output = Success(data="deployment.apps/nginx paused")
    resource_type_or_name = "deployment/nginx"
    args_tuple = ()
    subcommand = "pause"
    expected_kubectl_cmd_list = [
        "rollout",
        subcommand,
        resource_type_or_name,
        *args_tuple,
    ]
    expected_final_result = Success(
        message=(
            f"Completed 'rollout' subcommand: {subcommand} for "
            f"resource: {resource_type_or_name}"
        )
    )

    async def mock_to_thread_side_effect(
        func: Callable, *args_to_func: Any, **kwargs_to_func: Any
    ) -> Result | None:
        if func is run_kubectl:
            assert args_to_func[0] == expected_kubectl_cmd_list
            return mock_kubectl_output
        # handle_command_output is no longer called via to_thread
        raise AssertionError(
            f"asyncio.to_thread called with unexpected function: {func}"
        )

    with (
        patch(
            "vibectl.subcommands.rollout_cmd.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=mock_to_thread_side_effect,
        ) as mock_async_to_thread,
        patch(
            "vibectl.subcommands.rollout_cmd.handle_command_output",
            new_callable=AsyncMock,
            return_value=Success(message="Mocked handler output"),
        ) as mock_handle_output_direct,
        patch(
            "vibectl.subcommands.rollout_cmd.configure_output_flags",
            return_value=default_rollout_output_flags,
        ),
        patch("vibectl.subcommands.rollout_cmd.configure_memory_flags"),
    ):
        result = await run_rollout_command(
            subcommand="pause",
            resource="deployment/nginx",
            args=(),
            show_raw_output=default_rollout_output_flags.show_raw_output,
            show_vibe=default_rollout_output_flags.show_vibe,
            model=default_rollout_output_flags.model_name,
            show_kubectl=default_rollout_output_flags.show_kubectl,
            freeze_memory=False,
            unfreeze_memory=False,
            show_streaming=True,
        )
        assert mock_async_to_thread.call_count == 1  # Only run_kubectl
        assert result == expected_final_result
        mock_handle_output_direct.assert_called_once_with(
            output=mock_kubectl_output,
            output_flags=default_rollout_output_flags,
            summary_prompt_func=rollout_general_prompt,
        )


@pytest.mark.asyncio
async def test_run_rollout_resume(default_rollout_output_flags: OutputFlags) -> None:
    """Test normal execution of rollout resume command via run_rollout_command."""
    mock_kubectl_output = Success(data="deployment.apps/nginx resumed")
    resource_type_or_name = "deployment/nginx"
    args_tuple = ()
    subcommand = "resume"
    expected_kubectl_cmd_list = [
        "rollout",
        subcommand,
        resource_type_or_name,
        *args_tuple,
    ]
    expected_final_result = Success(
        message=(
            f"Completed 'rollout' subcommand: {subcommand} for "
            f"resource: {resource_type_or_name}"
        )
    )

    async def mock_to_thread_side_effect(
        func: Callable, *args_to_func: Any, **kwargs_to_func: Any
    ) -> Result | None:
        if func is run_kubectl:
            assert args_to_func[0] == expected_kubectl_cmd_list
            return mock_kubectl_output
        # handle_command_output is no longer called via to_thread
        raise AssertionError(
            f"asyncio.to_thread called with unexpected function: {func}"
        )

    with (
        patch(
            "vibectl.subcommands.rollout_cmd.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=mock_to_thread_side_effect,
        ) as mock_async_to_thread,
        patch(
            "vibectl.subcommands.rollout_cmd.handle_command_output",
            new_callable=AsyncMock,
            return_value=Success(message="Mocked handler output"),
        ) as mock_handle_output_direct,
        patch(
            "vibectl.subcommands.rollout_cmd.configure_output_flags",
            return_value=default_rollout_output_flags,
        ),
        patch("vibectl.subcommands.rollout_cmd.configure_memory_flags"),
    ):
        result = await run_rollout_command(
            subcommand="resume",
            resource="deployment/nginx",
            args=(),
            show_raw_output=default_rollout_output_flags.show_raw_output,
            show_vibe=default_rollout_output_flags.show_vibe,
            model=default_rollout_output_flags.model_name,
            show_kubectl=default_rollout_output_flags.show_kubectl,
            freeze_memory=False,
            unfreeze_memory=False,
            show_streaming=True,
        )
        assert mock_async_to_thread.call_count == 1  # Only run_kubectl
        assert result == expected_final_result
        mock_handle_output_direct.assert_called_once_with(
            output=mock_kubectl_output,
            output_flags=default_rollout_output_flags,
            summary_prompt_func=rollout_general_prompt,
        )


@pytest.mark.asyncio
async def test_run_rollout_kubectl_error_propagates(
    default_rollout_output_flags: OutputFlags,
) -> None:
    """Test error handling when run_kubectl (first threaded call) returns an Error."""
    error_exception = ValueError("Simulated kubectl error")
    mock_kubectl_error_result = Error(
        error="kubectl command failed", exception=error_exception
    )

    resource_type_or_name = "deployment/error-prone"
    args_tuple = ()
    subcommand = "status"  # Using status for this generic error test
    expected_kubectl_cmd_list = [
        "rollout",
        subcommand,
        resource_type_or_name,
        *args_tuple,
    ]

    async def mock_to_thread_side_effect(
        func: Callable, *args_to_func: Any, **kwargs_to_func: Any
    ) -> Result:
        if func is run_kubectl:
            assert args_to_func[0] == expected_kubectl_cmd_list
            return mock_kubectl_error_result
        # handle_command_output should not be called if run_kubectl returns
        # an Error that is returned by run_rollout_command
        raise AssertionError(
            f"asyncio.to_thread called with unexpected function: {func}"
        )

    with (
        patch(
            "vibectl.subcommands.rollout_cmd.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=mock_to_thread_side_effect,
        ) as mock_async_to_thread,
        patch(
            "vibectl.subcommands.rollout_cmd.handle_command_output",
            new_callable=AsyncMock,
            return_value=Success(message="Mocked handler output"),
        ),
        patch(
            "vibectl.subcommands.rollout_cmd.configure_output_flags",
            return_value=default_rollout_output_flags,
        ),
        patch("vibectl.subcommands.rollout_cmd.configure_memory_flags"),
    ):
        result = await run_rollout_command(
            subcommand="status",
            resource="deployment/error-prone",
            args=(),
            show_raw_output=default_rollout_output_flags.show_raw_output,
            show_vibe=default_rollout_output_flags.show_vibe,
            model=default_rollout_output_flags.model_name,
            show_kubectl=default_rollout_output_flags.show_kubectl,
            freeze_memory=False,
            unfreeze_memory=False,
            show_streaming=True,
        )

        assert mock_async_to_thread.call_count == 1  # Only run_kubectl
        assert result == mock_kubectl_error_result
        assert isinstance(result, Error)
        assert result.error == "kubectl command failed"
        assert result.exception == error_exception


@pytest.mark.asyncio
async def test_run_rollout_handle_command_output_error(
    default_rollout_output_flags: OutputFlags,
) -> None:
    """Test error handling when handle_command_output itself raises or Errors."""
    mock_kubectl_success = Success(data="kubectl success data")
    error_exception_in_handler = ValueError(
        "Simulated error from handle_command_output"
    )
    mock_handler_error_result = Error(
        error="Exception in handle_command_output", exception=error_exception_in_handler
    )

    resource_type_or_name = "deployment/handler-error"
    args_tuple = ()
    subcommand = "status"  # Using status for this test
    expected_kubectl_cmd_list = [
        "rollout",
        subcommand,
        resource_type_or_name,
        *args_tuple,
    ]

    async def mock_to_thread_side_effect(
        func: Callable, *args_to_func: Any, **kwargs_to_func: Any
    ) -> Result | None:
        if func is run_kubectl:
            assert args_to_func[0] == expected_kubectl_cmd_list
            return mock_kubectl_success
        # asyncio.to_thread should only be called for run_kubectl in this test case,
        # as handle_command_output is patched directly to raise an error.
        raise AssertionError(
            f"asyncio.to_thread called with unexpected function: {func}"
        )

    with (
        patch(
            "vibectl.subcommands.rollout_cmd.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=mock_to_thread_side_effect,
        ) as mock_async_to_thread,
        patch(
            "vibectl.subcommands.rollout_cmd.handle_command_output",
            new_callable=AsyncMock,
            side_effect=error_exception_in_handler,
        ) as mock_handle_output_direct,
        patch(
            "vibectl.subcommands.rollout_cmd.configure_output_flags",
            return_value=default_rollout_output_flags,
        ),
        patch("vibectl.subcommands.rollout_cmd.configure_memory_flags"),
    ):
        result = await run_rollout_command(
            subcommand="status",
            resource="deployment/handler-error",
            args=(),
            show_raw_output=default_rollout_output_flags.show_raw_output,
            show_vibe=default_rollout_output_flags.show_vibe,
            model=default_rollout_output_flags.model_name,
            show_kubectl=default_rollout_output_flags.show_kubectl,
            freeze_memory=False,
            unfreeze_memory=False,
            show_streaming=True,
        )

        assert mock_async_to_thread.call_count == 1
        assert result == mock_handler_error_result
        assert isinstance(result, Error)
        assert result.error == "Exception in handle_command_output"
        assert result.exception == error_exception_in_handler
        mock_handle_output_direct.assert_called_once_with(
            output=mock_kubectl_success,
            output_flags=default_rollout_output_flags,
            summary_prompt_func=rollout_status_prompt,
        )


@pytest.mark.asyncio
async def test_run_rollout_command_handles_run_kubectl_returning_string(
    default_rollout_output_flags: OutputFlags,
) -> None:
    """Test run_rollout_command handles incorrect string return from run_kubectl."""
    rollout_subcommand = "status"
    resource_type_or_name = "deployment/string-returner"
    args_tuple = ()
    expected_kubectl_cmd_list = [
        "rollout",
        rollout_subcommand,
        resource_type_or_name,
        *args_tuple,
    ]

    raw_string_output_from_kubectl = "This is a raw string, not a Result object"

    async def mock_to_thread_side_effect(
        func_to_run_in_thread: Callable, *args_for_func: Any, **kwargs_for_func: Any
    ) -> Any:
        if func_to_run_in_thread is run_kubectl:
            assert args_for_func[0] == expected_kubectl_cmd_list
            return raw_string_output_from_kubectl  # Incorrect return type
        # handle_command_output should not be reached if run_kubectl returns a string,
        # as run_rollout_command should error out before that.
        raise AssertionError(
            "asyncio.to_thread called with unexpected function: "
            f"{func_to_run_in_thread}"
        )

    with (
        patch(
            "vibectl.subcommands.rollout_cmd.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=mock_to_thread_side_effect,
        ) as mock_async_to_thread,
        patch(
            "vibectl.subcommands.rollout_cmd.handle_command_output",
            new_callable=AsyncMock,
            # It should receive a Success object, even if run_kubectl returned str
            # This tests the internal adaptation in run_rollout_command.
            # For this specific test, we don't care about its return, just
            # that it's called.
            return_value=Success(message="Mocked output from handler"),
        ),
        patch(
            "vibectl.subcommands.rollout_cmd.configure_output_flags",
            return_value=default_rollout_output_flags,
        ),
        patch(
            "vibectl.subcommands.rollout_cmd.configure_memory_flags"
        ) as mock_configure_memory,
    ):
        result = await run_rollout_command(
            subcommand=rollout_subcommand,
            resource=resource_type_or_name,
            args=args_tuple,
            show_raw_output=default_rollout_output_flags.show_raw_output,
            show_vibe=default_rollout_output_flags.show_vibe,
            model=default_rollout_output_flags.model_name,
            show_kubectl=default_rollout_output_flags.show_kubectl,
            freeze_memory=False,
            unfreeze_memory=False,
            show_streaming=True,
        )

        assert isinstance(result, Error)
        assert result.error == "Exception running kubectl"
        assert isinstance(
            result.exception, AttributeError
        )  # Because of kubectl_result.data access
        mock_async_to_thread.assert_called_once()  # Only run_kubectl mock should be hit

        mock_configure_memory.assert_called_once()
