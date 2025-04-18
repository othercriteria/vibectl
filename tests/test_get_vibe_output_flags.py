from unittest.mock import Mock, patch

from click.testing import CliRunner

from vibectl.cli import cli

# These tests require the cli_test_mocks and mock_config fixtures.
# They should be available via conftest.py


def test_get_vibe_basic(
    cli_runner: CliRunner,
    mock_config: Mock,
    cli_test_mocks: tuple[Mock, Mock, Mock, Mock],
) -> None:
    """Test basic get vibe command."""
    mock_run_kubectl, mock_handle_output, mock_handle_vibe_cli, mock_handle_vibe_get = (
        cli_test_mocks
    )
    mock_configure_flags = Mock()
    from vibectl.command_handler import OutputFlags

    mock_configure_flags.return_value = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="model-xyz-1.2.3",
    )
    with patch(
        "vibectl.subcommands.get_cmd.configure_output_flags", mock_configure_flags
    ):
        result = cli_runner.invoke(cli, ["get", "vibe", "pods"], catch_exceptions=False)
    assert result.exit_code == 0
    # Assert on the get_cmd mock
    mock_handle_vibe_get.assert_called_once()
    args, kwargs = mock_handle_vibe_get.call_args
    assert kwargs["request"] == "pods"
    assert kwargs["command"] == "get"
    assert isinstance(kwargs["plan_prompt"], str)
    assert callable(kwargs["summary_prompt_func"])
    assert isinstance(kwargs["output_flags"], OutputFlags)
    assert kwargs["output_flags"].show_raw is False
    assert kwargs["output_flags"].show_vibe is True
    assert kwargs["output_flags"].model_name == "model-xyz-1.2.3"
    mock_run_kubectl.assert_not_called()
    mock_handle_output.assert_not_called()


def test_get_vibe_with_output_flags(
    cli_runner: CliRunner,
    mock_config: Mock,
    cli_test_mocks: tuple[Mock, Mock, Mock, Mock],
) -> None:
    """Test get vibe command with output flags."""
    mock_run_kubectl, mock_handle_output, mock_handle_vibe_cli, mock_handle_vibe_get = (
        cli_test_mocks
    )
    mock_configure_flags = Mock()
    from vibectl.command_handler import OutputFlags

    mock_configure_flags.return_value = OutputFlags(
        show_raw=True,
        show_vibe=False,
        warn_no_output=False,
        model_name="model-xyz-1.2.3",
    )
    with patch(
        "vibectl.subcommands.get_cmd.configure_output_flags", mock_configure_flags
    ):
        result = cli_runner.invoke(
            cli, ["get", "vibe", "pods", "--raw", "--no-vibe"], catch_exceptions=False
        )
    assert result.exit_code == 0
    mock_handle_vibe_get.assert_called_once()
    args, kwargs = mock_handle_vibe_get.call_args
    assert kwargs["request"] == "pods --raw --no-vibe"
    assert kwargs["command"] == "get"
    assert isinstance(kwargs["plan_prompt"], str)
    assert callable(kwargs["summary_prompt_func"])
    assert isinstance(kwargs["output_flags"], OutputFlags)
    assert kwargs["output_flags"].show_raw is True
    assert kwargs["output_flags"].show_vibe is False
    assert kwargs["output_flags"].model_name == "model-xyz-1.2.3"
    mock_run_kubectl.assert_not_called()
    mock_handle_output.assert_not_called()


def test_get_vibe_with_model_flag(
    cli_runner: CliRunner,
    mock_config: Mock,
    cli_test_mocks: tuple[Mock, Mock, Mock, Mock],
) -> None:
    """Test get vibe command with model flag."""
    mock_run_kubectl, mock_handle_output, mock_handle_vibe_cli, mock_handle_vibe_get = (
        cli_test_mocks
    )
    mock_configure_flags = Mock()
    from vibectl.command_handler import OutputFlags

    mock_configure_flags.return_value = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",  # This is set by the test
    )
    with patch(
        "vibectl.subcommands.get_cmd.configure_output_flags", mock_configure_flags
    ):
        result = cli_runner.invoke(
            cli,
            ["get", "vibe", "pods", "--model", "test-model"],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    mock_handle_vibe_get.assert_called_once()
    args, kwargs = mock_handle_vibe_get.call_args
    assert kwargs["request"] == "pods"
    assert kwargs["command"] == "get"
    assert isinstance(kwargs["plan_prompt"], str)
    assert callable(kwargs["summary_prompt_func"])
    assert isinstance(kwargs["output_flags"], OutputFlags)
    assert kwargs["output_flags"].model_name == "test-model"
    mock_run_kubectl.assert_not_called()
    mock_handle_output.assert_not_called()


def test_get_vibe_with_no_output_flags(
    cli_runner: CliRunner,
    mock_config: Mock,
    cli_test_mocks: tuple[Mock, Mock, Mock, Mock],
) -> None:
    """Test get vibe command with no output flags."""
    mock_run_kubectl, mock_handle_output, mock_handle_vibe_cli, mock_handle_vibe_get = (
        cli_test_mocks
    )
    mock_configure_flags = Mock()
    from vibectl.command_handler import OutputFlags

    mock_configure_flags.return_value = OutputFlags(
        show_raw=False,
        show_vibe=False,
        warn_no_output=False,
        model_name="model-xyz-1.2.3",
    )
    with patch(
        "vibectl.subcommands.get_cmd.configure_output_flags", mock_configure_flags
    ):
        result = cli_runner.invoke(
            cli,
            ["get", "vibe", "pods", "--no-raw", "--no-vibe"],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    mock_handle_vibe_get.assert_called_once()
    args, kwargs = mock_handle_vibe_get.call_args
    assert kwargs["request"] == "pods --no-raw --no-vibe"
    assert kwargs["command"] == "get"
    assert isinstance(kwargs["plan_prompt"], str)
    assert callable(kwargs["summary_prompt_func"])
    assert isinstance(kwargs["output_flags"], OutputFlags)
    assert kwargs["output_flags"].show_raw is False
    assert kwargs["output_flags"].show_vibe is False
    mock_run_kubectl.assert_not_called()
    mock_handle_output.assert_not_called()


def test_get_vibe_with_env_flags(
    cli_runner: CliRunner,
    mock_config: Mock,
    cli_test_mocks: tuple[Mock, Mock, Mock, Mock],
) -> None:
    """Test get vibe command with environment flags."""
    mock_run_kubectl, mock_handle_output, mock_handle_vibe_cli, mock_handle_vibe_get = (
        cli_test_mocks
    )
    mock_configure_flags = Mock()
    from vibectl.command_handler import OutputFlags

    mock_configure_flags.return_value = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="model-xyz-1.2.3",
    )
    with patch(
        "vibectl.subcommands.get_cmd.configure_output_flags", mock_configure_flags
    ):
        result = cli_runner.invoke(cli, ["get", "vibe", "pods"], catch_exceptions=False)
    assert result.exit_code == 0
    mock_handle_vibe_get.assert_called_once()
    args, kwargs = mock_handle_vibe_get.call_args
    assert kwargs["request"] == "pods"
    assert kwargs["command"] == "get"
    assert isinstance(kwargs["plan_prompt"], str)
    assert callable(kwargs["summary_prompt_func"])
    assert isinstance(kwargs["output_flags"], OutputFlags)
    assert kwargs["output_flags"].show_raw is False
    assert kwargs["output_flags"].show_vibe is True
    mock_run_kubectl.assert_not_called()
    mock_handle_output.assert_not_called()


def test_get_vibe_with_default_flags(
    cli_runner: CliRunner,
    mock_config: Mock,
    cli_test_mocks: tuple[Mock, Mock, Mock, Mock],
) -> None:
    """Test get vibe command with default flags."""
    mock_run_kubectl, mock_handle_output, mock_handle_vibe_cli, mock_handle_vibe_get = (
        cli_test_mocks
    )
    mock_configure_flags = Mock()
    from vibectl.command_handler import OutputFlags

    mock_configure_flags.return_value = OutputFlags(
        show_raw=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="model-xyz-1.2.3",
    )
    with patch(
        "vibectl.subcommands.get_cmd.configure_output_flags", mock_configure_flags
    ):
        result = cli_runner.invoke(cli, ["get", "vibe", "pods"], catch_exceptions=False)
    assert result.exit_code == 0
    # Assert on the get_cmd mock
    mock_handle_vibe_get.assert_called_once()
    args, kwargs = mock_handle_vibe_get.call_args
    assert kwargs["request"] == "pods"
    assert kwargs["command"] == "get"
    assert isinstance(kwargs["plan_prompt"], str)
    assert callable(kwargs["summary_prompt_func"])
    assert isinstance(kwargs["output_flags"], OutputFlags)
    assert kwargs["output_flags"].show_raw is False
    assert kwargs["output_flags"].show_vibe is True
    mock_run_kubectl.assert_not_called()
    mock_handle_output.assert_not_called()
