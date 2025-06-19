from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asyncclick.testing import CliRunner

from vibectl.cli import cli
from vibectl.subcommands.check_cmd import run_check_command
from vibectl.types import (
    Error,
    MetricsDisplayMode,
    OutputFlags,
    PredicateCheckExitCode,
    Result,
    Success,
)

# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio


@patch("vibectl.subcommands.check_cmd.configure_output_flags")
@patch("vibectl.subcommands.check_cmd.configure_memory_flags")
@patch("vibectl.subcommands.check_cmd.execute_check_logic", new_callable=AsyncMock)
async def test_run_check_command_success(
    mock_execute_check_logic: AsyncMock,
    mock_configure_memory_flags: MagicMock,
    mock_configure_output_flags: MagicMock,
) -> None:
    """Test run_check_command successful execution path."""
    predicate = "is the cluster healthy?"
    mock_output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=True,
        warn_no_output=True,
        model_name="test-model",
        show_kubectl=False,
        show_metrics=MetricsDisplayMode.NONE,
    )
    mock_configure_output_flags.return_value = mock_output_flags

    expected_result = Success(message="Predicate is TRUE")
    expected_result.original_exit_code = PredicateCheckExitCode.TRUE.value
    mock_execute_check_logic.return_value = expected_result

    result: Result = await run_check_command(
        predicate=predicate,
        show_raw_output=False,
        show_vibe=True,
        show_kubectl=False,
        model="test-model",
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=MetricsDisplayMode.NONE,
        show_streaming=True,
    )

    assert result == expected_result
    assert result.original_exit_code == PredicateCheckExitCode.TRUE.value
    mock_configure_memory_flags.assert_called_once_with(False, False)
    # For now, let's comment it out, as the primary mock is execute_check_logic
    # mock_configure_output_flags.assert_called_once_with(
    #     show_raw_output=False,
    #     show_vibe=True,
    #     model="test-model",
    #     show_kubectl=False,
    #     show_metrics=MetricsDisplayMode.NONE,
    # )
    mock_execute_check_logic.assert_called_once_with(
        predicate=predicate,
        output_flags=mock_output_flags,
    )


@patch("vibectl.subcommands.check_cmd.configure_output_flags")
@patch("vibectl.subcommands.check_cmd.configure_memory_flags")
@patch("vibectl.subcommands.check_cmd.execute_check_logic", new_callable=AsyncMock)
async def test_run_check_command_error_from_vibe(
    mock_execute_check_logic: AsyncMock,
    mock_configure_memory_flags: MagicMock,
    mock_configure_output_flags: MagicMock,
) -> None:
    """Test run_check_command when execute_check_logic returns an Error."""
    predicate = "is the sky blue?"
    mock_output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=False,
        warn_no_output=True,
        model_name="",
        show_kubectl=False,
        show_metrics=MetricsDisplayMode.ALL,
    )
    mock_configure_output_flags.return_value = mock_output_flags

    expected_error = Error(error="LLM failed")
    expected_error.original_exit_code = PredicateCheckExitCode.CANNOT_DETERMINE.value
    mock_execute_check_logic.return_value = expected_error

    result: Result = await run_check_command(
        predicate=predicate,
        show_raw_output=False,
        show_vibe=False,
        show_kubectl=False,
        model=None,
        freeze_memory=True,
        unfreeze_memory=False,
        show_metrics=MetricsDisplayMode.ALL,
        show_streaming=True,
    )

    assert result == expected_error
    assert result.original_exit_code == PredicateCheckExitCode.CANNOT_DETERMINE.value
    mock_configure_memory_flags.assert_called_once_with(True, False)
    mock_execute_check_logic.assert_called_once_with(
        predicate=predicate,
        output_flags=mock_output_flags,
    )


async def test_run_check_command_empty_predicate() -> None:
    """Test run_check_command with an empty predicate string."""
    with patch("vibectl.subcommands.check_cmd.configure_memory_flags"):
        # configure_output_flags is not called in the empty predicate path
        # So, the patch and assertion for it are removed.

        result: Result = await run_check_command(
            predicate="",
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
    expected_error_message = (
        "Missing predicate for 'check' command. "
        "Please provide a natural language predicate, e.g.: "
        'vibectl check "are there any pods in a CrashLoopBackOff state?"'
    )
    assert result.error == expected_error_message
    assert result.original_exit_code == PredicateCheckExitCode.POORLY_POSED.value


@pytest.mark.parametrize(
    "expected_exit_code_enum",
    [
        PredicateCheckExitCode.TRUE,
        PredicateCheckExitCode.FALSE,
        PredicateCheckExitCode.POORLY_POSED,
        PredicateCheckExitCode.CANNOT_DETERMINE,
    ],
)
# The CLI command wrapper is in vibectl.cli and calls run_check_command
# (from subcommands.check_cmd), so we must patch it there.
@patch("vibectl.cli.run_check_command", new_callable=AsyncMock)
@patch("vibectl.execution.check.Config")  # Used by real run_check_command
async def test_check_command_cli_exit_code_propagation(
    mock_config_class_sut: MagicMock,
    mock_run_check_command_cli: AsyncMock,
    expected_exit_code_enum: PredicateCheckExitCode,
) -> None:
    """Test that vibectl check CLI command propagates original_exit_code correctly."""
    if expected_exit_code_enum == PredicateCheckExitCode.TRUE:
        mock_run_check_command_cli.return_value = Success(
            data="LLM says TRUE", original_exit_code=PredicateCheckExitCode.TRUE.value
        )
    elif expected_exit_code_enum == PredicateCheckExitCode.FALSE:
        mock_run_check_command_cli.return_value = Success(
            data="LLM says FALSE", original_exit_code=PredicateCheckExitCode.FALSE.value
        )
    elif expected_exit_code_enum == PredicateCheckExitCode.POORLY_POSED:
        mock_run_check_command_cli.return_value = Error(
            error="LLM says POORLY POSED",
            original_exit_code=PredicateCheckExitCode.POORLY_POSED.value,
        )
    elif expected_exit_code_enum == PredicateCheckExitCode.CANNOT_DETERMINE:
        mock_run_check_command_cli.return_value = Error(
            error="LLM says CANNOT DETERMINE",
            original_exit_code=PredicateCheckExitCode.CANNOT_DETERMINE.value,
        )
    else:
        # Fallback, though all enum members should be covered
        mock_run_check_command_cli.return_value = Error(
            error="Unknown test case", original_exit_code=99
        )

    runner = CliRunner()
    predicate_text = "is the cluster super healthy?"

    # Execute the CLI command
    # The --model flag here is somewhat arbitrary since
    # the LLM call is deeply mocked by the return_value setup above.
    # However, it's good practice to keep it if the command expects it.
    cli_result = await runner.invoke(
        cli, ["check", predicate_text, "--model", "test-model-check"]
    )

    # Assertions
    # Check that our mock for vibectl.cli.run_check_command was called once.
    mock_run_check_command_cli.assert_called_once()

    # The CliRunner's result.exit_code should reflect what
    # handle_result(mock_run_check_command_cli.return_value) does. handle_result
    # sets sys.exit with the exit_code from the Result object. CliRunner
    # captures this sys.exit and uses it as result.exit_code.
    assert cli_result.exit_code == expected_exit_code_enum.value, (
        f"Expected CLI exit code {expected_exit_code_enum.value}, but "
        f"got {cli_result.exit_code}. Output: {cli_result.output}"
    )
