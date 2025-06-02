"""Tests for command_handler.py utility functions.

This module tests the utility functions and helper methods in command_handler.py
that are currently not covered by existing tests.
"""

from unittest.mock import Mock, patch

from vibectl.command_handler import (
    _check_output_visibility,
    _create_display_command,
    _display_kubectl_command,
    _display_raw_output,
    _handle_empty_output,
    _handle_standard_command_error,
    _quote_args,
    configure_output_flags,
    create_api_error,
)
from vibectl.types import (
    Error,
    LLMMetrics,
    MetricsDisplayMode,
    OutputFlags,
    Success,
)


class TestQuoteArgs:
    """Test cases for _quote_args function."""

    def test_no_quotes_needed(self) -> None:
        """Test _quote_args with simple arguments that don't need quoting."""
        args = ["get", "pods", "-n", "default"]
        result = _quote_args(args)
        assert result == ["get", "pods", "-n", "default"]

    def test_with_spaces(self) -> None:
        """Test _quote_args with arguments containing spaces."""
        args = ["get", "pods", "-l", "app=my app"]
        result = _quote_args(args)
        assert result == ["get", "pods", "-l", '"app=my app"']

    def test_with_special_characters(self) -> None:
        """Test _quote_args with special characters."""
        args = ["exec", "pod", "--", "echo", "hello < world > test | grep test"]
        result = _quote_args(args)
        expected = ["exec", "pod", "--", "echo", '"hello < world > test | grep test"']
        assert result == expected

    def test_mixed_arguments(self) -> None:
        """Test _quote_args with mix of quoted and unquoted arguments."""
        args = ["exec", "-it", "pod-name", "--", "echo", "hello world", ">", "file"]
        result = _quote_args(args)
        expected = [
            "exec",
            "-it",
            "pod-name",
            "--",
            "echo",
            '"hello world"',
            '">"',
            "file",
        ]
        assert result == expected

    def test_empty_list(self) -> None:
        """Test _quote_args with empty list."""
        args: list[str] = []
        result = _quote_args(args)
        assert result == []

    def test_pipe_character(self) -> None:
        """Test _quote_args with pipe character."""
        args = ["exec", "pod", "--", "ps", "aux", "|", "grep", "nginx"]
        result = _quote_args(args)
        expected = ["exec", "pod", "--", "ps", "aux", '"|"', "grep", "nginx"]
        assert result == expected


class TestCreateDisplayCommand:
    """Test cases for _create_display_command function."""

    def test_basic_command(self) -> None:
        """Test _create_display_command with basic arguments."""
        result = _create_display_command("get", ["pods", "-n", "default"], False)
        assert result == "kubectl get pods -n default"

    def test_with_yaml_indicator(self) -> None:
        """Test _create_display_command with YAML content indicator."""
        result = _create_display_command("apply", ["-f", "-"], True)
        assert result == "kubectl apply -f - (with YAML content)"

    def test_with_spaces_in_args(self) -> None:
        """Test _create_display_command with spaces in arguments."""
        result = _create_display_command("get", ["pods", "-l", "app=my app"], False)
        assert result == 'kubectl get pods -l "app=my app"'

    def test_with_special_characters(self) -> None:
        """Test _create_display_command with special characters."""
        result = _create_display_command(
            "exec", ["pod", "--", "echo", "hello > world"], False
        )
        assert result == 'kubectl exec pod -- echo "hello > world"'

    def test_empty_args(self) -> None:
        """Test _create_display_command with empty args."""
        result = _create_display_command("version", [], False)
        assert result == "kubectl version"


class TestHandleEmptyOutput:
    """Test cases for _handle_empty_output function."""

    @patch("vibectl.command_handler.console_manager")
    @patch("vibectl.command_handler.logger")
    def test_handle_empty_output(self, mock_logger: Mock, mock_console: Mock) -> None:
        """Test _handle_empty_output function."""
        result = _handle_empty_output("get", "pods", ("--all-namespaces",))

        # Check the result is a Success object
        assert isinstance(result, Success)
        assert result.message == "Command returned no output"

        # Verify logging and console output
        mock_logger.info.assert_called_once_with(
            "No output from command: get pods --all-namespaces"
        )
        mock_console.print_processing.assert_called_once_with(
            "Command returned no output"
        )

    @patch("vibectl.command_handler.console_manager")
    @patch("vibectl.command_handler.logger")
    def test_handle_empty_output_no_args(
        self, mock_logger: Mock, mock_console: Mock
    ) -> None:
        """Test _handle_empty_output with no additional args."""
        result = _handle_empty_output("get", "pods", ())

        assert isinstance(result, Success)
        assert result.message == "Command returned no output"
        mock_logger.info.assert_called_once_with("No output from command: get pods ")


class TestHandleStandardCommandError:
    """Test cases for _handle_standard_command_error function."""

    @patch("vibectl.command_handler.logger")
    def test_handle_standard_command_error(self, mock_logger: Mock) -> None:
        """Test _handle_standard_command_error function."""
        test_exception = ValueError("Test error")
        result = _handle_standard_command_error(
            "get", "pods", ("mypod",), test_exception
        )

        # Check the result is an Error object
        assert isinstance(result, Error)
        assert result.error == "Unexpected error: Test error"
        assert result.exception == test_exception

        # Verify error logging
        mock_logger.error.assert_called_once_with(
            "Unexpected error handling standard command: get pods mypod: Test error",
            exc_info=True,
        )

    @patch("vibectl.command_handler.logger")
    def test_handle_standard_command_error_no_args(self, mock_logger: Mock) -> None:
        """Test _handle_standard_command_error with no additional args."""
        test_exception = RuntimeError("Runtime error")
        result = _handle_standard_command_error("delete", "pod", (), test_exception)

        assert isinstance(result, Error)
        assert result.error == "Unexpected error: Runtime error"
        assert result.exception == test_exception


class TestCreateApiError:
    """Test cases for create_api_error function."""

    def test_create_api_error_basic(self) -> None:
        """Test create_api_error with basic error message."""
        result = create_api_error("API overloaded")

        assert isinstance(result, Error)
        assert result.error == "API overloaded"
        assert result.exception is None
        assert result.halt_auto_loop is False  # Key feature for auto mode
        assert result.metrics is None

    def test_create_api_error_with_exception(self) -> None:
        """Test create_api_error with exception."""
        test_exception = TimeoutError("Request timeout")
        result = create_api_error("API timeout", exception=test_exception)

        assert isinstance(result, Error)
        assert result.error == "API timeout"
        assert result.exception == test_exception
        assert result.halt_auto_loop is False

    def test_create_api_error_with_metrics(self) -> None:
        """Test create_api_error with metrics."""
        test_metrics = LLMMetrics(
            token_input=100,
            token_output=50,
            latency_ms=1500,
            total_processing_duration_ms=2000,
        )
        result = create_api_error("API error", metrics=test_metrics)

        assert isinstance(result, Error)
        assert result.error == "API error"
        assert result.metrics == test_metrics
        assert result.halt_auto_loop is False

    def test_create_api_error_all_params(self) -> None:
        """Test create_api_error with all parameters."""
        test_exception = ConnectionError("Connection failed")
        test_metrics = LLMMetrics(
            token_input=200,
            token_output=100,
            latency_ms=3000,
            total_processing_duration_ms=4000,
        )
        result = create_api_error(
            "Complete API failure", exception=test_exception, metrics=test_metrics
        )

        assert isinstance(result, Error)
        assert result.error == "Complete API failure"
        assert result.exception == test_exception
        assert result.metrics == test_metrics
        assert result.halt_auto_loop is False


class TestConfigureOutputFlags:
    """Test cases for configure_output_flags function."""

    def test_configure_output_flags_defaults(self) -> None:
        """Test configure_output_flags with no parameters (all defaults)."""
        result = configure_output_flags()

        assert isinstance(result, OutputFlags)
        # The actual defaults come from OutputFlags.from_args() so we
        # just verify it's created

    def test_configure_output_flags_all_params(self) -> None:
        """Test configure_output_flags with all parameters specified."""
        result = configure_output_flags(
            show_raw_output=True,
            show_vibe=False,
            model="test-model",
            show_kubectl=True,
            show_metrics=MetricsDisplayMode.ALL,
            show_streaming=False,
        )

        assert isinstance(result, OutputFlags)
        assert result.show_raw_output is True
        assert result.show_vibe is False
        assert result.model_name == "test-model"
        assert result.show_kubectl is True
        assert result.show_metrics == MetricsDisplayMode.ALL
        assert result.show_streaming is False

    def test_configure_output_flags_partial(self) -> None:
        """Test configure_output_flags with some parameters specified."""
        result = configure_output_flags(
            show_vibe=True,
            model="gpt-4",
            show_metrics=MetricsDisplayMode.NONE,
        )

        assert isinstance(result, OutputFlags)
        assert result.show_vibe is True
        assert result.model_name == "gpt-4"
        assert result.show_metrics == MetricsDisplayMode.NONE


class TestDisplayFunctions:
    """Test cases for display utility functions."""

    @patch("vibectl.command_handler.console_manager")
    def test_display_kubectl_command_no_show(self, mock_console: Mock) -> None:
        """Test _display_kubectl_command when show_kubectl is False."""
        output_flags = OutputFlags(
            model_name="test-model",
            show_raw_output=False,
            show_vibe=True,
            show_kubectl=False,
        )
        _display_kubectl_command(output_flags, "get pods")

        # Should not call console_manager when show_kubectl is False
        mock_console.print_processing.assert_not_called()

    @patch("vibectl.command_handler.console_manager")
    def test_display_kubectl_command_no_command(self, mock_console: Mock) -> None:
        """Test _display_kubectl_command when command is None."""
        output_flags = OutputFlags(
            model_name="test-model",
            show_raw_output=False,
            show_vibe=True,
            show_kubectl=True,
        )
        _display_kubectl_command(output_flags, None)

        # Should not call console_manager when command is None
        mock_console.print_processing.assert_not_called()

    @patch("vibectl.command_handler.console_manager")
    def test_display_kubectl_command_vibe_no_request(self, mock_console: Mock) -> None:
        """Test _display_kubectl_command with vibe command without request."""
        output_flags = OutputFlags(
            model_name="test-model",
            show_raw_output=False,
            show_vibe=True,
            show_kubectl=True,
        )
        _display_kubectl_command(output_flags, "vibe")

        mock_console.print_processing.assert_called_once_with(
            "Planning next steps based on memory context..."
        )

    @patch("vibectl.command_handler.console_manager")
    def test_display_kubectl_command_vibe_with_request(
        self, mock_console: Mock
    ) -> None:
        """Test _display_kubectl_command with vibe command with request."""
        output_flags = OutputFlags(
            model_name="test-model",
            show_raw_output=False,
            show_vibe=True,
            show_kubectl=True,
        )
        _display_kubectl_command(output_flags, "vibe create a deployment")

        mock_console.print_processing.assert_called_once_with(
            "Planning how to: create a deployment"
        )

    @patch("vibectl.command_handler.console_manager")
    def test_display_kubectl_command_vibe_empty_request(
        self, mock_console: Mock
    ) -> None:
        """Test _display_kubectl_command with vibe command with empty request."""
        output_flags = OutputFlags(
            model_name="test-model",
            show_raw_output=False,
            show_vibe=True,
            show_kubectl=True,
        )
        _display_kubectl_command(output_flags, "vibe   ")  # spaces only

        mock_console.print_processing.assert_called_once_with(
            "Planning next steps based on memory context..."
        )

    @patch("vibectl.command_handler.console_manager")
    @patch("vibectl.command_handler.logger")
    def test_check_output_visibility_warning(
        self, mock_logger: Mock, mock_console: Mock
    ) -> None:
        """Test _check_output_visibility when no output will be shown."""
        output_flags = OutputFlags(
            model_name="test-model",
            show_raw_output=False,
            show_vibe=False,
            warn_no_output=True,
        )
        _check_output_visibility(output_flags)

        mock_logger.warning.assert_called_once_with(
            "No output will be shown due to output flags."
        )
        mock_console.print_no_output_warning.assert_called_once()

    @patch("vibectl.command_handler.console_manager")
    @patch("vibectl.command_handler.logger")
    def test_check_output_visibility_no_warning_when_output_shown(
        self, mock_logger: Mock, mock_console: Mock
    ) -> None:
        """Test _check_output_visibility when output will be shown."""
        output_flags = OutputFlags(
            model_name="test-model",
            show_raw_output=True,  # At least one output will be shown
            show_vibe=False,
            warn_no_output=True,
        )
        _check_output_visibility(output_flags)

        # Should not warn when output will be shown
        mock_logger.warning.assert_not_called()
        mock_console.print_no_output_warning.assert_not_called()

    @patch("vibectl.command_handler.console_manager")
    @patch("vibectl.command_handler.logger")
    def test_check_output_visibility_no_warning_when_disabled(
        self, mock_logger: Mock, mock_console: Mock
    ) -> None:
        """Test _check_output_visibility when warning is disabled."""
        output_flags = OutputFlags(
            model_name="test-model",
            show_raw_output=False,
            show_vibe=False,
            warn_no_output=False,  # Warning disabled
        )
        _check_output_visibility(output_flags)

        # Should not warn when warning is disabled
        mock_logger.warning.assert_not_called()
        mock_console.print_no_output_warning.assert_not_called()

    @patch("vibectl.command_handler.console_manager")
    @patch("vibectl.command_handler.logger")
    def test_display_raw_output_enabled(
        self, mock_logger: Mock, mock_console: Mock
    ) -> None:
        """Test _display_raw_output when raw output is enabled."""
        output_flags = OutputFlags(
            model_name="test-model",
            show_raw_output=True,
            show_vibe=False,
        )
        _display_raw_output(output_flags, "test output")

        mock_logger.debug.assert_called_once_with("Showing raw output.")
        mock_console.print_raw.assert_called_once_with("test output")

    @patch("vibectl.command_handler.console_manager")
    @patch("vibectl.command_handler.logger")
    def test_display_raw_output_disabled(
        self, mock_logger: Mock, mock_console: Mock
    ) -> None:
        """Test _display_raw_output when raw output is disabled."""
        output_flags = OutputFlags(
            model_name="test-model",
            show_raw_output=False,
            show_vibe=False,
        )
        _display_raw_output(output_flags, "test output")

        # Should not display anything when raw output is disabled
        mock_logger.debug.assert_not_called()
        mock_console.print_raw.assert_not_called()
