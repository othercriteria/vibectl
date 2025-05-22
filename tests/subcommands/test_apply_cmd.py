from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from vibectl.config import Config
from vibectl.prompt import PLAN_APPLY_PROMPT, apply_output_prompt
from vibectl.subcommands.apply_cmd import run_apply_command
from vibectl.types import Error, OutputFlags, Success


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
    mock_output_flags.show_raw = False
    mock_output_flags.show_vibe = True
    mock_output_flags.show_kubectl = False
    mock_output_flags.model_name = "test-model"
    mock_output_flags.warn_no_output = False
    mock_output_flags.show_metrics = False
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
        show_metrics=False,
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
        show_metrics=False,
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
    mock_output_flags.show_raw = False
    mock_output_flags.show_vibe = False
    mock_output_flags.show_kubectl = False
    mock_output_flags.model_name = None
    mock_output_flags.warn_no_output = False
    mock_output_flags.show_metrics = False
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
        show_metrics=False,
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
        show_metrics=False,
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
    mock_output_flags.show_raw = False
    mock_output_flags.show_vibe = True
    mock_output_flags.show_kubectl = False
    mock_output_flags.model_name = "test-model"
    mock_output_flags.warn_no_output = False
    mock_output_flags.show_metrics = False
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
        show_metrics=False,
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
        show_metrics=False,
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
    """Test run_apply_command with 'vibe' but no request args."""
    mock_output_flags = MagicMock(spec=OutputFlags)
    mock_output_flags.show_raw = False
    mock_output_flags.show_vibe = True
    mock_output_flags.show_kubectl = False
    mock_output_flags.model_name = "test-model"
    mock_output_flags.warn_no_output = False
    mock_output_flags.show_metrics = False
    mock_configure_output_flags.return_value = mock_output_flags

    result = await run_apply_command(
        args=("vibe",),
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

    mock_adapter_instance_for_apply_cmd = MagicMock()
    mock_adapter_instance_for_apply_cmd.get_model.return_value = MagicMock()
    mock_get_model_adapter_apply_cmd.return_value = mock_adapter_instance_for_apply_cmd

    mock_adapter_instance_ch = MagicMock()
    mock_adapter_instance_ch.get_model.return_value = MagicMock()
    mock_get_model_adapter_ch.return_value = mock_adapter_instance_ch

    mock_output_flags = MagicMock(spec=OutputFlags)
    mock_output_flags.show_raw = False
    mock_output_flags.show_vibe = True
    mock_output_flags.show_kubectl = False
    mock_output_flags.model_name = "default-test-model"
    mock_output_flags.warn_no_output = False
    mock_output_flags.show_metrics = False
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

    mock_adapter_instance_for_apply_cmd = MagicMock()
    mock_adapter_instance_for_apply_cmd.get_model.return_value = MagicMock()
    mock_get_model_adapter_apply_cmd.return_value = mock_adapter_instance_for_apply_cmd

    mock_adapter_instance_ch = MagicMock()
    mock_adapter_instance_ch.get_model.return_value = MagicMock()
    mock_get_model_adapter_ch.return_value = mock_adapter_instance_ch

    mock_output_flags = MagicMock(spec=OutputFlags)
    mock_output_flags.show_raw = False
    mock_output_flags.show_vibe = True
    mock_output_flags.show_kubectl = False
    mock_output_flags.model_name = "default-test-model"
    mock_output_flags.warn_no_output = False
    mock_output_flags.show_metrics = False
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
    assert mock_logger.info.call_count == 3

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
) -> None:
    """Test intelligent apply vibe mode fails early on LLM empty scope response."""
    mock_config_instance = MagicMock(spec=Config)
    mock_config_instance.get_typed.side_effect = (
        lambda key, default: True if key == "intelligent_apply" else default
    )
    mock_config_cls.return_value = mock_config_instance

    mock_output_flags = MagicMock(spec=OutputFlags)
    mock_output_flags.show_raw = False
    mock_output_flags.show_vibe = True
    mock_output_flags.show_kubectl = False
    mock_output_flags.model_name = "test-intelligent-model"
    mock_output_flags.warn_no_output = False
    mock_output_flags.show_metrics = False
    mock_configure_output_flags.return_value = mock_output_flags

    mock_model_adapter_instance = MagicMock()
    mock_get_model_adapter.return_value = mock_model_adapter_instance

    mock_model_adapter_instance.execute_and_log_metrics.return_value = (
        None,
        {"tokens_in": 10, "tokens_out": 0, "latency_ms": 100.0},
    )

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
    assert (
        result.error == "An unexpected error occurred in intelligent apply workflow. "
        "object tuple can't be used in 'await' expression"
    )
    assert result.metrics is None

    mock_logger.info.assert_any_call(
        f"Invoking 'apply' subcommand with args: {args_tuple}"
    )
    mock_logger.info.assert_any_call(f"Planning how to: {request_str}")
    mock_logger.info.assert_any_call("Starting intelligent apply workflow...")
    mock_logger.error.assert_any_call(
        "An unexpected error occurred in intelligent apply workflow: "
        "object tuple can't be used in 'await' expression",
        exc_info=True,
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

    mock_get_model_adapter.assert_called_once_with(config=mock_config_instance)

    mock_model_adapter_instance.execute_and_log_metrics.assert_called_once()
    call_args_elam = (
        mock_model_adapter_instance.execute_and_log_metrics.call_args.kwargs
    )
    assert call_args_elam["response_model"].__name__ == "ApplyFileScopeResponse"
