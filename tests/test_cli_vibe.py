from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from vibectl.cli import cli
from vibectl.command_handler import OutputFlags
from vibectl.schema import ActionType, LLMCommandResponse
from vibectl.subcommands.vibe_cmd import run_vibe_command
from vibectl.types import Error, Success


# Local fixtures specifically for these tests
@pytest.fixture
def mock_handle_vibe_request() -> Generator[Mock, None, None]:
    """Mock the handle_vibe_request function in vibe_cmd for CLI tests."""
    with patch("vibectl.subcommands.vibe_cmd.handle_vibe_request") as mock:
        mock.return_value = Success(message="Success")
        yield mock


@pytest.fixture
def mock_get_memory() -> Generator[Mock, None, None]:
    """Mock the get_memory function in vibe_cmd for CLI tests."""
    with patch("vibectl.subcommands.vibe_cmd.get_memory") as mock:
        mock.return_value = "Memory context"
        yield mock


@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.model_adapter.LLMModelAdapter.execute")
@patch("vibectl.subcommands.vibe_cmd.get_memory")
@patch("vibectl.command_handler.configure_output_flags")
@pytest.mark.asyncio
async def test_vibe_command_with_request(
    mock_configure_flags: Mock,
    mock_get_memory: Mock,
    mock_llm_execute: Mock,
    mock_run_kubectl: Mock,
    standard_output_flags: OutputFlags,
) -> None:
    """Test the main vibe command with a request and OutputFlags."""
    mock_configure_flags.return_value = standard_output_flags
    mock_get_memory.return_value = ""
    mock_llm_execute.side_effect = [
        LLMCommandResponse(
            action_type=ActionType.COMMAND,
            commands=["create", "deployment", "nginx", "--image=nginx"],
            explanation="ok",
        ).model_dump_json(),
        "Memory updated after execution.",
        "Deployment created successfully.",
        "Memory updated after summary.",
    ]
    mock_run_kubectl.return_value = Success(data="deployment created")

    cmd_obj = cli.commands["vibe"]
    with pytest.raises(SystemExit) as exc_info:
        # Add --yes to bypass potential confirmation prompts
        await cmd_obj.main(["Create a deployment", "--show-raw-output", "--yes"])

    assert exc_info.value.code == 0
    assert mock_llm_execute.call_count >= 1
    mock_run_kubectl.assert_called_once()


@patch("vibectl.subcommands.vibe_cmd.get_memory")
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
    )

    assert isinstance(result, Success)  # Can now assert Success
    mock_handle_vibe_request.assert_called_once()
    args, kwargs = mock_handle_vibe_request.call_args
    assert kwargs["request"] == ""  # Should be empty string
    # Check flags passed to handle_vibe_request were configured correctly
    mock_configure_flags.assert_called_once_with(
        show_raw_output=True, show_vibe=None, model=None, show_kubectl=None
    )


@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.model_adapter.LLMModelAdapter.execute")
@patch("vibectl.subcommands.vibe_cmd.get_memory")
@patch("vibectl.command_handler.configure_output_flags")
@pytest.mark.asyncio
async def test_vibe_command_with_yes_flag(
    mock_configure_flags: Mock,
    mock_get_memory: Mock,
    mock_llm_execute: Mock,
    mock_run_kubectl: Mock,
    standard_output_flags: OutputFlags,
) -> None:
    """Test the main vibe command with the yes flag, mocking network calls."""
    mock_configure_flags.return_value = standard_output_flags
    mock_get_memory.return_value = ""

    # 1. Mock initial LLM plan to return a command (ensure it's valid)
    plan_json = LLMCommandResponse(
        action_type=ActionType.COMMAND,
        commands=["create", "deployment", "my-deploy", "--image=nginx"],
        explanation="Create deploy",
    ).model_dump_json()
    # Mock LLM execute to return the plan first, then maybe feedback for recovery
    mock_llm_execute.side_effect = [
        plan_json,  # First call
        '{"action_type": "FEEDBACK", "explanation": "kubectl failed"}',  # Second call
    ]

    # 2. Mock run_kubectl to simulate failure
    mock_run_kubectl.return_value = Error(error="kubectl create failed")

    # Let the actual handle_vibe_request run, relying on inner mocks

    cmd_obj = cli.commands["vibe"]
    with pytest.raises(SystemExit) as exc_info:
        # Run with --yes
        await cmd_obj.main(["Create a deployment", "--yes", "--show-raw-output"])

    # We expect it to fail because kubectl failed, even with --yes
    assert exc_info.value.code != 0

    # Verify mocks were called
    assert mock_llm_execute.call_count >= 1  # At least the planning call
    mock_run_kubectl.assert_called_once()  # Kubectl should have been attempted
    # mock_handle_vibe_request.assert_called_once() # This outer mock is less useful now


@patch("vibectl.subcommands.vibe_cmd.get_memory")
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
    )

    assert isinstance(result, Success)
    mock_handle_vibe.assert_called_once()
    mock_configure_flags.assert_called_once()  # Verify config was called
    args, kwargs = mock_handle_vibe.call_args
    assert kwargs["request"] == ""


@patch("vibectl.subcommands.vibe_cmd.get_memory")
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
    )

    assert isinstance(result, Success)
    mock_handle_vibe.assert_called_once()
    mock_configure_flags.assert_called_once()
    args, kwargs = mock_handle_vibe.call_args
    assert kwargs["request"] == ""
    assert kwargs["memory_context"] == memory_value


# Tests calling run_vibe_command directly should be async and await
@patch("vibectl.subcommands.vibe_cmd.get_memory")
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
    )

    # Verify results
    assert isinstance(result, Success)
    assert result.message == "Command executed successfully"
    mock_handle_vibe.assert_called_once()
    args, kwargs = mock_handle_vibe.call_args
    assert kwargs["request"] == request
    assert kwargs["memory_context"] == "Working in namespace 'test'"


@patch("vibectl.subcommands.vibe_cmd.logger")
@patch("vibectl.subcommands.vibe_cmd.get_memory")
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
        "do something", None, None, None, None, exit_on_error=False
    )
    assert isinstance(result, Error)
    assert "fail!" in result.error
    mock_logger.error.assert_called_once()
    mock_handle_vibe.assert_called_once()


# Removed redundant test - vibe_command_calls_logger_and_console


@patch("vibectl.subcommands.vibe_cmd.configure_memory_flags")
@patch("vibectl.subcommands.vibe_cmd.configure_output_flags")
@patch("vibectl.subcommands.vibe_cmd.logger")
@patch("vibectl.subcommands.vibe_cmd.get_memory")
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

    result = await run_vibe_command("", None, None, None, None, exit_on_error=False)
    assert isinstance(result, Success)
    mock_logger.info.assert_any_call("Invoking 'vibe' subcommand with request: ''")
    mock_logger.info.assert_any_call(
        "No request provided; using memory context for planning."
    )
    mock_handle_vibe.assert_called_once()


@patch("vibectl.subcommands.vibe_cmd.logger")
@patch("vibectl.subcommands.vibe_cmd.get_memory")
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

    result = await run_vibe_command("do something", None, None, None, None)
    assert isinstance(result, Success)
    mock_logger.info.assert_any_call(
        "Invoking 'vibe' subcommand with request: 'do something'"
    )
    mock_logger.info.assert_any_call("Planning how to: do something")
    mock_handle_vibe.assert_called_once()


@patch("vibectl.subcommands.vibe_cmd.logger")
@patch("vibectl.subcommands.vibe_cmd.get_memory")
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
            "do something", None, None, None, None, exit_on_error=True
        )
    mock_handle_vibe.assert_called_once()
    # Expect logger.error to be called twice due to re-raise
    assert mock_logger.error.call_count == 2


# Test for handling ValueError specifically (recoverable in auto mode)
@patch("vibectl.subcommands.vibe_cmd.logger")
@patch("vibectl.subcommands.vibe_cmd.get_memory")
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
        "do something", None, None, None, None, exit_on_error=False
    )
    assert isinstance(result, Error)
    assert "LLM parse error" in result.error
    assert result.halt_auto_loop is False  # Check if marked as recoverable
    mock_logger.warning.assert_called_once()
    mock_handle_vibe.assert_called_once()


@patch("vibectl.command_handler.get_model_adapter")
@pytest.mark.asyncio
async def test_handle_vibe_with_unknown_model(
    mock_get_model_adapter: Mock,
) -> None:
    """Test that the vibe command properly reports errors for unknown model names."""
    # Configure the mock adapter returned by the factory
    mock_adapter_instance = MagicMock()
    mock_get_model_adapter.return_value = mock_adapter_instance
    # Configure the get_model method on the mock adapter instance
    mock_adapter_instance.get_model.side_effect = ValueError(
        "Unknown model: invalid-model-name"
    )

    # Call the CLI command entry point directly
    cmd_obj = cli.commands["vibe"]
    # Expect SystemExit(1) because the ValueError is caught and handled by cli.main
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["show me pods", "--model", "invalid-model-name"])

    # Verify exit code is 1
    assert exc_info.value.code == 1
    # Verify get_model_adapter was called to get the adapter
    mock_get_model_adapter.assert_called_once()
    # Verify get_model was called on the adapter instance
    mock_adapter_instance.get_model.assert_called_once_with("invalid-model-name")


# Removed redundant/similar tests to simplify
