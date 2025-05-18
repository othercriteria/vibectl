from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from vibectl.cli import cli
from vibectl.command_handler import OutputFlags
from vibectl.model_adapter import LLMModelAdapter
from vibectl.schema import ActionType, LLMPlannerResponse, CommandAction, FeedbackAction, ErrorAction
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
@patch("vibectl.memory.get_model_adapter")
@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.memory.get_memory")
@patch("vibectl.command_handler.configure_output_flags")
@pytest.mark.asyncio
async def test_vibe_command_with_request(
    mock_configure_flags: Mock,
    mock_vibe_cmd_get_memory: Mock,
    mock_ch_get_model_adapter: Mock,
    mock_mem_get_memory: Mock,
    mock_run_kubectl: Mock,
    default_output_flags: OutputFlags,
) -> None:
    """Test the main vibe command with a request and OutputFlags."""
    mock_configure_flags.return_value = default_output_flags
    mock_vibe_cmd_get_memory.return_value = ""

    # 1. Mock get_model_adapter factory to return our mock adapter instance
    mock_adapter_instance = MagicMock(spec=LLMModelAdapter)
    mock_ch_get_model_adapter.return_value = mock_adapter_instance
    mock_mem_get_memory.return_value = mock_adapter_instance

    # 2. The adapter's get_model method will be called to get a model object.
    #    This model object is passed to adapter.execute(), but our mocked execute
    #    won't use it. We just need get_model() to not fail.
    mock_adapter_instance.get_model.return_value = MagicMock()

    # Mock the execute_and_log_metrics method which is called by _get_llm_plan,
    # update_memory, and _get_llm_summary
    mock_adapter_instance.execute_and_log_metrics.side_effect = [
        (
            LLMPlannerResponse(action=CommandAction(
                action_type=ActionType.COMMAND,
                commands=["create", "deployment", "nginx", "--image=nginx"],
            )).model_dump_json(),
            None,
        ),  # 1. For _get_llm_plan call
        ("Memory updated after execution.", None),  # 2. For first update_memory call
        ("Deployment created successfully.", None),  # 3. For _get_llm_summary call
        ("Memory updated after summary.", None),  # 4. For second update_memory call
    ]

    mock_run_kubectl.return_value = Success(data="deployment created")

    cmd_obj = cli.commands["vibe"]
    with pytest.raises(SystemExit) as exc_info:
        # Add --yes to bypass potential confirmation prompts
        await cmd_obj.main(["Create a deployment", "--show-raw-output", "--yes"])

    assert exc_info.value.code == 0
    mock_run_kubectl.assert_called_once()
    assert mock_ch_get_model_adapter.call_count >= 1
    assert (
        mock_mem_get_memory.call_count >= 1
    )  # Ensure memory module's adapter was also called if memory updates happened
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
    )


@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.memory.get_model_adapter")
@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.memory.get_memory")
@patch("vibectl.command_handler.configure_output_flags")
@pytest.mark.asyncio
async def test_vibe_command_with_yes_flag(
    mock_configure_flags: Mock,
    mock_vibe_cmd_get_memory: Mock,
    mock_ch_get_model_adapter: Mock,
    mock_mem_get_memory: Mock,
    mock_run_kubectl: Mock,
    default_output_flags: OutputFlags,
) -> None:
    """Test the main vibe command with the yes flag, mocking network calls."""
    mock_configure_flags.return_value = default_output_flags
    mock_vibe_cmd_get_memory.return_value = ""

    # 1. Mock get_model_adapter factory
    mock_adapter_instance = MagicMock(spec=LLMModelAdapter)
    mock_ch_get_model_adapter.return_value = mock_adapter_instance
    mock_mem_get_memory.return_value = mock_adapter_instance

    # 2. Mock adapter's get_model
    mock_adapter_instance.get_model.return_value = MagicMock()

    # 3. Mock adapter's execute_and_log_metrics method for sequential plan and feedback
    plan_json = LLMPlannerResponse(action=CommandAction(
        action_type=ActionType.COMMAND,
        commands=["create", "deployment", "my-deploy", "--image=nginx"],
    )).model_dump_json()
    mock_adapter_instance.execute_and_log_metrics.side_effect = [
        (plan_json, None),  # For _get_llm_plan
        (
            LLMPlannerResponse(action=FeedbackAction( 
                action_type=ActionType.FEEDBACK,
                message="kubectl failed",
            )).model_dump_json(),
            None,
        ),  # For recovery
        ("Memory updated after initial plan.", None),  # For first update_memory
        ("Memory updated after recovery feedback.", None),  # For second update_memory
    ]

    # 4. Mock run_kubectl to simulate failure
    mock_run_kubectl.return_value = Error(error="kubectl create failed")

    # Let the actual handle_vibe_request run, relying on inner mocks

    cmd_obj = cli.commands["vibe"]
    with pytest.raises(SystemExit) as exc_info:
        # Run with --yes
        await cmd_obj.main(["Create a deployment", "--yes", "--show-raw-output"])

    # We expect it to fail because kubectl failed, even with --yes
    assert exc_info.value.code != 0

    # Verify mocks were called
    assert mock_ch_get_model_adapter.call_count >= 1
    assert mock_mem_get_memory.call_count >= 1
    assert mock_adapter_instance.get_model.call_count >= 1
    assert (
        mock_adapter_instance.execute_and_log_metrics.call_count >= 2
    )  # Plan + recovery feedback
    mock_run_kubectl.assert_called_once()


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

    result = await run_vibe_command("", None, None, None, None, exit_on_error=False)
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

    result = await run_vibe_command("do something", None, None, None, None)
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
            "do something", None, None, None, None, exit_on_error=True
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
        "do something", None, None, None, None, exit_on_error=False
    )
    assert isinstance(result, Error)
    assert "LLM parse error" in result.error
    assert result.halt_auto_loop is False  # Check if marked as recoverable
    mock_logger.warning.assert_called_once()
    mock_handle_vibe.assert_called_once()


@patch("vibectl.memory.get_model_adapter")
@patch("vibectl.command_handler.get_model_adapter")
@pytest.mark.asyncio
async def test_handle_vibe_with_unknown_model(
    mock_ch_get_model_adapter: Mock,
    mock_mem_get_memory: Mock,
) -> None:
    """Test that the vibe command properly reports errors for unknown model names."""
    # 1. Mock adapter instance for command_handler path
    mock_ch_adapter_instance = MagicMock(spec=LLMModelAdapter)
    mock_ch_get_model_adapter.return_value = mock_ch_adapter_instance
    # Configure get_model on this instance to raise the error
    mock_ch_adapter_instance.get_model.side_effect = ValueError(
        "Unknown model: invalid-model-name"
    )

    # 2. Mock adapter instance for memory.update_memory path
    mock_mem_adapter_instance = MagicMock(spec=LLMModelAdapter)
    mock_mem_get_memory.return_value = mock_mem_adapter_instance
    # update_memory calls get_model then execute. Mock them.
    mock_mem_model_obj = MagicMock()
    mock_mem_adapter_instance.get_model.return_value = mock_mem_model_obj
    mock_mem_adapter_instance.execute_and_log_metrics.return_value = (
        "Memory updated during error handling."
    )

    # Call the CLI command entry point directly
    cmd_obj = cli.commands["vibe"]
    # Expect SystemExit(1) because the ValueError is caught and handled by cli.main
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["show me pods", "--model", "invalid-model-name"])

    # Verify exit code is 1
    assert exc_info.value.code == 1
    # Verify get_model_adapter was called to get the adapter (for command_handler)
    mock_ch_get_model_adapter.assert_called_once()
    # Verify get_model was called on the adapter instance (for command_handler)
    mock_ch_adapter_instance.get_model.assert_called_once_with("invalid-model-name")

    # Verify that update_memory (via memory.get_model_adapter) was also called
    mock_mem_get_memory.assert_called_once()
    mock_mem_adapter_instance.get_model.assert_called_once()  # Called by update_memory
    # Assert execute_and_log_metrics was called, as update_memory now uses that
    mock_mem_adapter_instance.execute_and_log_metrics.assert_called_once()


@patch("vibectl.k8s_utils.subprocess.Popen")  # Mock Popen in k8s_utils
@patch("vibectl.command_handler.Config")  # Mock Config in command_handler
@patch("vibectl.memory.get_model_adapter")
@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.memory.get_memory")
@patch("vibectl.command_handler.configure_output_flags")
@pytest.mark.asyncio
async def test_vibe_command_with_yaml_input(
    mock_configure_flags: Mock,
    mock_vibe_cmd_get_memory: Mock,
    mock_ch_get_model_adapter: Mock,
    mock_mem_get_memory: Mock,
    mock_ch_config: Mock,  # New mock for command_handler.Config
    mock_k8s_popen: Mock,  # New mock for k8s_utils.subprocess.Popen
    default_output_flags: OutputFlags,
) -> None:
    """Test vibe command when LLM plan includes YAML content and kubeconfig handling."""
    mock_configure_flags.return_value = default_output_flags
    mock_vibe_cmd_get_memory.return_value = ""

    # --- Mock LLM and Memory Adapters ---
    mock_adapter_instance = MagicMock(spec=LLMModelAdapter)
    mock_ch_get_model_adapter.return_value = mock_adapter_instance
    mock_mem_get_memory.return_value = mock_adapter_instance
    mock_adapter_instance.get_model.return_value = MagicMock()

    yaml_content_str = "apiVersion: v1\\nkind: ConfigMap\\nmetadata:\\n  name: my-cm"
    plan_json = LLMPlannerResponse(action=CommandAction(
        action_type=ActionType.COMMAND,
        commands=["apply", "-f", "-"],
        yaml_manifest=yaml_content_str,
    )).model_dump_json()

    mock_adapter_instance.execute_and_log_metrics.side_effect = [
        (plan_json, None),
        ("Memory updated after execution.", None),
        ("ConfigMap applied.", None),
        ("Memory updated after summary.", None),
    ]

    # --- Mock Config used by command_handler._execute_command ---
    mock_config_instance_ch = mock_ch_config.return_value
    mock_kubeconfig_path = "/tmp/fake_kubeconfig_for_test.yaml"

    # Ensure this mock_get only returns the fake path for "kubeconfig" key
    def mock_config_get_side_effect(key: str, default: Any = None) -> Any:
        if key == "kubeconfig":
            return mock_kubeconfig_path
        if key == "kubectl_path":
            return "kubectl"  # Ensure kubectl_path returns a string
        return default

    mock_config_instance_ch.get.side_effect = mock_config_get_side_effect
    mock_config_instance_ch.get_typed.side_effect = (
        mock_config_get_side_effect  # Also mock get_typed
    )

    # --- Mock subprocess.Popen called by k8s_utils.run_kubectl_with_yaml ---
    mock_process = mock_k8s_popen.return_value
    mock_process.communicate.return_value = (b"configmap/my-cm created", b"")
    mock_process.returncode = 0

    # --- Execute Command ---
    cmd_obj = cli.commands["vibe"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["Apply a configmap", "--yes"])

    # --- Assertions ---
    assert exc_info.value.code == 0  # Crucial: command should appear to succeed

    # Assert Popen was called correctly by run_kubectl_with_yaml
    mock_k8s_popen.assert_called_once()
    popen_args, popen_kwargs = mock_k8s_popen.call_args
    actual_popen_cmd_list = popen_args[0]  # This is the list of command and args

    # Verify --kubeconfig flag is present in the command list passed to Popen
    assert "--kubeconfig" in actual_popen_cmd_list
    kubeconfig_flag_index = actual_popen_cmd_list.index("--kubeconfig")
    assert kubeconfig_flag_index + 1 < len(actual_popen_cmd_list)
    assert actual_popen_cmd_list[kubeconfig_flag_index + 1] == mock_kubeconfig_path

    # Assert LLM/memory mocks
    assert mock_ch_get_model_adapter.call_count >= 1
    assert mock_mem_get_memory.call_count >= 1
    assert mock_adapter_instance.get_model.call_count >= 1
    assert mock_adapter_instance.execute_and_log_metrics.call_count >= 2
    # Assert Config.get was called for "kubeconfig"
    mock_config_instance_ch.get.assert_any_call("kubeconfig")


@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.memory.get_model_adapter")
@patch("vibectl.command_handler.get_model_adapter")
@patch("vibectl.memory.get_memory")
@patch("vibectl.command_handler.configure_output_flags")
@pytest.mark.asyncio
async def test_vibe_command_kubectl_failure_no_recovery_plan(
    mock_configure_flags: Mock,
    mock_vibe_cmd_get_memory: Mock,
    mock_ch_get_model_adapter: Mock,
    mock_mem_get_memory: Mock,
    mock_run_kubectl: Mock,
    default_output_flags: OutputFlags,
) -> None:
    """Test vibe command when kubectl fails and LLM provides no recovery plan."""
    mock_configure_flags.return_value = default_output_flags
    mock_vibe_cmd_get_memory.return_value = ""

    mock_adapter_instance = MagicMock(spec=LLMModelAdapter)
    mock_ch_get_model_adapter.return_value = mock_adapter_instance
    mock_mem_get_memory.return_value = mock_adapter_instance

    mock_adapter_instance.get_model.return_value = MagicMock()

    plan_json = LLMPlannerResponse(action=CommandAction(
        action_type=ActionType.COMMAND,
        commands=["delete", "pod", "nonexistent-pod"],
    )).model_dump_json()

    mock_adapter_instance.execute_and_log_metrics.side_effect = [
        (
            LLMPlannerResponse(action=CommandAction(
                action_type=ActionType.COMMAND,
                commands=["delete", "pod", "nonexistent-pod"],
            )).model_dump_json(),
            None,
        ),  # For _get_llm_plan
        # For recovery attempt - this test expects no useful recovery plan,
        # so the LLM might return a simple feedback or an error indicating it cannot help.
        # Let's use FeedbackAction as an example of a non-command recovery.
        (
            LLMPlannerResponse(action=FeedbackAction( 
                action_type=ActionType.FEEDBACK,
                message="The pod was not found. Cannot suggest specific recovery without more info.",
            )).model_dump_json(),
            None,
        ),
        ("Memory updated after initial plan.", None),
        ("Memory updated after failed recovery attempt.", None),
    ]
    mock_run_kubectl.return_value = Error(error="pods 'nonexistent-pod' not found")

    cmd_obj = cli.commands["vibe"]
    with pytest.raises(SystemExit) as exc_info:
        await cmd_obj.main(["Delete a pod", "--yes"])

    # Should exit with error because kubectl failed and no recovery command was given
    assert exc_info.value.code != 0
    mock_run_kubectl.assert_called_once()
    # Should have called LLM for plan, then for feedback/recovery attempt
    assert mock_ch_get_model_adapter.call_count >= 1
    assert mock_mem_get_memory.call_count >= 1
    assert mock_adapter_instance.get_model.call_count >= 1
    assert (
        mock_adapter_instance.execute_and_log_metrics.call_count >= 2
    )  # Plan + recovery feedback
