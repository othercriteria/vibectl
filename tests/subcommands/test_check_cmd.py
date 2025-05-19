import json
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

# For CliRunner tests
# from click.testing import CliRunner # Old import
from asyncclick.testing import CliRunner  # Use CliRunner from asyncclick

from vibectl.cli import cli  # Assuming main cli object is here
from vibectl.subcommands.check_cmd import run_check_command
from vibectl.types import Error, OutputFlags, Result, Success

# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio


@patch("vibectl.subcommands.check_cmd.configure_output_flags")
@patch("vibectl.subcommands.check_cmd.configure_memory_flags")
@patch("vibectl.subcommands.check_cmd.handle_vibe_request", new_callable=AsyncMock)
async def test_run_check_command_success(
    mock_handle_vibe_request: AsyncMock,
    mock_configure_memory_flags: MagicMock,
    mock_configure_output_flags: MagicMock,
) -> None:
    """Test run_check_command successful execution path."""
    predicate = "is the cluster healthy?"
    mock_output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,
        model_name="test-model",
        show_kubectl=False,
        show_metrics=False,
    )
    mock_configure_output_flags.return_value = mock_output_flags

    expected_result = Success(message="Predicate is TRUE")
    expected_result.original_exit_code = 0
    mock_handle_vibe_request.return_value = expected_result

    result: Result = await run_check_command(
        predicate=predicate,
        show_raw_output=False,
        show_vibe=True,
        show_kubectl=False,
        model="test-model",
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=False,
    )

    assert result == expected_result
    assert result.original_exit_code == 0
    mock_configure_memory_flags.assert_called_once_with(False, False)
    mock_configure_output_flags.assert_called_once_with(
        show_raw_output=False,
        show_vibe=True,
        model="test-model",
        show_kubectl=False,
        show_metrics=False,
    )
    mock_handle_vibe_request.assert_called_once()
    _args, kwargs = mock_handle_vibe_request.call_args
    assert kwargs["request"] == predicate
    assert kwargs["command"] == "check"
    assert kwargs["output_flags"] == mock_output_flags
    assert kwargs["yes"] is True
    assert callable(kwargs["plan_prompt_func"])
    assert callable(kwargs["summary_prompt_func"])


@patch("vibectl.subcommands.check_cmd.configure_output_flags")
@patch("vibectl.subcommands.check_cmd.configure_memory_flags")
@patch("vibectl.subcommands.check_cmd.handle_vibe_request", new_callable=AsyncMock)
async def test_run_check_command_error_from_vibe(
    mock_handle_vibe_request: AsyncMock,
    mock_configure_memory_flags: MagicMock,
    mock_configure_output_flags: MagicMock,
) -> None:
    """Test run_check_command when handle_vibe_request returns an Error."""
    predicate = "is the sky blue?"
    mock_output_flags = OutputFlags(
        show_raw=False,
        show_vibe=False,
        warn_no_output=True,
        model_name="",
        show_kubectl=False,
        show_metrics=True,
    )
    mock_configure_output_flags.return_value = mock_output_flags

    expected_error = Error(error="LLM failed")
    expected_error.original_exit_code = 3
    mock_handle_vibe_request.return_value = expected_error

    result: Result = await run_check_command(
        predicate=predicate,
        show_raw_output=False,
        show_vibe=False,
        show_kubectl=False,
        model=None,
        freeze_memory=True,
        unfreeze_memory=False,
        show_metrics=True,
    )

    assert result == expected_error
    assert result.original_exit_code == 3
    mock_configure_memory_flags.assert_called_once_with(True, False)
    mock_handle_vibe_request.assert_called_once_with(
        request=predicate,
        command="check",
        plan_prompt_func=ANY,
        summary_prompt_func=ANY,
        output_flags=mock_output_flags,
        yes=True,
    )


async def test_run_check_command_empty_predicate() -> None:
    """Test run_check_command with an empty predicate string."""
    with (
        patch(
            "vibectl.subcommands.check_cmd.configure_memory_flags"
        ) as mock_cfg_mem_flags,
        patch(
            "vibectl.subcommands.check_cmd.configure_output_flags"
        ) as mock_cfg_out_flags,
    ):
        mock_cfg_out_flags.return_value = OutputFlags(
            show_raw=False,
            show_vibe=False,
            warn_no_output=True,
            model_name="",
            show_kubectl=False,
            show_metrics=False,
        )

        result: Result = await run_check_command(
            predicate="",
            show_raw_output=False,
            show_vibe=False,
            show_kubectl=False,
            model=None,
            freeze_memory=False,
            unfreeze_memory=False,
            show_metrics=False,
        )

    assert isinstance(result, Error)
    expected_error_message = (
        "Missing predicate for 'check' command. "
        "Please provide a natural language predicate, e.g.: "
        'vibectl check "are there any pods in a CrashLoopBackOff state?"'
    )
    assert result.error == expected_error_message
    assert result.original_exit_code == 2
    mock_cfg_mem_flags.assert_called_once()
    mock_cfg_out_flags.assert_called_once()


# To make this file runnable, we might need PLAN_CHECK_PROMPT definition if
# not mocked out
# For now, assuming the lambda in check_cmd.py for plan_prompt_func is sufficient
# for it to be callable.
# If PLAN_CHECK_PROMPT is imported and used by the lambda in a way that requires
# its value during test collection or execution (outside the mocked
# handle_vibe_request), it might need to be mocked or defined.
# However, handle_vibe_request is fully mocked, so its internal use of the lambda's
# return value (PLAN_CHECK_PROMPT) shouldn't be an issue.


@pytest.mark.parametrize(
    "expected_exit_code",
    [
        0,  # Predicate TRUE
        1,  # Predicate FALSE
        2,  # Predicate poorly posed (though usually caught before vibe_request)
        3,  # Cannot determine
    ],
)
# Patch targets should be where the names are looked up by the code under test.
# For functions imported directly via 'from module import func', patch them in
# the module where 'func' is defined.
@patch("vibectl.execution.check.configure_output_flags")
@patch("vibectl.execution.check.configure_memory_flags")
@patch("vibectl.execution.check.get_model_adapter")
@patch("sys.exit")  # Add patch for sys.exit
async def test_check_command_cli_exit_code_propagation(
    mock_sys_exit: MagicMock,  # Mock for sys.exit (innermost patch)
    mock_get_model_adapter_func: MagicMock,
    mock_configure_memory_flags: MagicMock,
    mock_configure_output_flags: MagicMock,
    expected_exit_code: int,
) -> None:
    """Test that vibectl check CLI command propagates original_exit_code correctly."""
    runner = CliRunner()
    predicate_text = "is the cluster super healthy?"

    # Setup mock for the get_model_adapter function
    mock_adapter_instance = MagicMock()
    mock_get_model_adapter_func.return_value = mock_adapter_instance

    # Setup mock for the get_model method on the mock_adapter_instance
    mock_dummy_llm_model = MagicMock()
    mock_adapter_instance.get_model.return_value = mock_dummy_llm_model

    action_dict = {
        "action_type": "DONE",
        "exit_code": expected_exit_code,
        "message": f"Predicate evaluation complete with code {expected_exit_code}",
    }

    llm_response_dict = {"action": action_dict}
    mock_llm_response_text = json.dumps(llm_response_dict)
    mock_metrics = MagicMock()  # Mock for LLMMetrics
    mock_adapter_instance.execute_and_log_metrics.return_value = (
        mock_llm_response_text,
        mock_metrics,
    )

    # Setup mock for configure_output_flags
    mock_specific_output_flags = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=True,
        model_name="test-cli-model",
        show_kubectl=False,
        show_metrics=False,
    )
    mock_configure_output_flags.return_value = mock_specific_output_flags

    # Invoke with minimal args, relying on Click defaults for flags not explicitly set,
    # which then get processed by the (now mocked) configure_output_flags
    if not isinstance(cli, MagicMock) and hasattr(cli, "commands"):
        command_to_invoke = cli.commands["check"]
    else:  # Fallback or if cli is already a Command or mocked differently
        command_to_invoke = cli

    # For asyncclick.testing.CliRunner, invoke might be an async method
    await runner.invoke(
        command_to_invoke, [predicate_text, "--model", "test-cli-model"]
    )

    mock_sys_exit.assert_called_once_with(expected_exit_code)

    # configure_memory_flags is called by run_check_command
    mock_configure_memory_flags.assert_called_once()
    # configure_output_flags is also called by run_check_command
    mock_configure_output_flags.assert_called_once()
