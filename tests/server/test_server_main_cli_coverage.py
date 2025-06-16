"""
Tests for CLI coverage gaps in vibectl.server.main module.

This module focuses on specific CLI functionality that's missing coverage,
particularly around error handling, result processing, and CLI command execution paths.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from vibectl.server.main import (
    cli,
    handle_result,
    parse_duration,
)
from vibectl.types import Error, Success


class TestHandleResultFunction:
    """Test handle_result function with various result types and exit scenarios."""

    def test_handle_result_success_with_original_exit_code(self) -> None:
        """Test handle_result with Success that has original_exit_code."""
        success_result = Success(message="Test success")
        success_result.original_exit_code = 42

        with pytest.raises(SystemExit) as exc_info:
            handle_result(success_result, exit_on_error=True)

        assert exc_info.value.code == 42

    def test_handle_result_error_with_original_exit_code(self) -> None:
        """Test handle_result with Error that has original_exit_code."""
        error_result = Error(error="Test error")
        error_result.original_exit_code = 5

        with pytest.raises(SystemExit) as exc_info:
            handle_result(error_result, exit_on_error=True)

        assert exc_info.value.code == 5

    def test_handle_result_error_with_recovery_suggestions(self) -> None:
        """Test handle_result with Error that has recovery suggestions."""
        error_result = Error(error="Test error")
        error_result.recovery_suggestions = "Try using --force flag"

        with patch("vibectl.server.main.console_manager") as mock_console:
            with pytest.raises(SystemExit):
                handle_result(error_result, exit_on_error=True)

            mock_console.print_error.assert_called_once_with("Test error")
            mock_console.print_note.assert_called_once_with("Try using --force flag")

    def test_handle_result_error_with_exception(self) -> None:
        """Test handle_result with Error that has an exception."""
        test_exception = ValueError("Test exception")
        error_result = Error(error="Test error", exception=test_exception)

        with patch("vibectl.server.main.handle_exception") as mock_handle_exc:
            with pytest.raises(SystemExit):
                handle_result(error_result, exit_on_error=True)

            mock_handle_exc.assert_called_once_with(test_exception)

    def test_handle_result_no_exit_on_error(self) -> None:
        """Test handle_result with exit_on_error=False."""
        error_result = Error(error="Test error")

        # Should not raise SystemExit when exit_on_error=False
        handle_result(error_result, exit_on_error=False)


class TestParseDurationErrorPaths:
    """Test parse_duration function error handling paths."""

    def test_parse_duration_value_error(self) -> None:
        """Test parse_duration with ValueError from parse_duration_to_days."""
        with patch("vibectl.server.main.parse_duration_to_days") as mock_parse:
            mock_parse.side_effect = ValueError("Invalid duration format")

            result = parse_duration("invalid_duration")

            assert isinstance(result, Error)
            assert "Invalid duration format" in result.error

    def test_parse_duration_general_exception(self) -> None:
        """Test parse_duration with general exception from parse_duration_to_days."""
        with patch("vibectl.server.main.parse_duration_to_days") as mock_parse:
            mock_parse.side_effect = RuntimeError("Unexpected error")

            result = parse_duration("30d")

            assert isinstance(result, Error)
            assert "Failed to parse duration: Unexpected error" in result.error
            assert result.exception is not None


class TestCLIGroupNoSubcommand:
    """Test CLI group behavior when no subcommand is invoked."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_cli_group_no_subcommand_with_context(self) -> None:
        """Test CLI group when invoked without subcommand shows help message."""
        result = self.runner.invoke(cli, [])

        assert result.exit_code == 0
        assert "vibectl-server: gRPC LLM proxy server" in result.output
        assert "Use --help to see available commands" in result.output


class TestGenerateTokenErrorPaths:
    """Test generate-token command error handling paths."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("vibectl.server.main.parse_duration")
    def test_generate_token_parse_duration_error(
        self, mock_parse_duration: Mock
    ) -> None:
        """Test generate-token when parse_duration fails."""
        mock_parse_duration.return_value = Error(error="Invalid duration")

        result = self.runner.invoke(cli, ["generate-token", "test-subject"])

        assert result.exit_code == 1
        assert "Error: Invalid duration" in result.output

    @patch("vibectl.server.main.parse_duration")
    @patch("vibectl.server.main._generate_jwt_token")
    def test_generate_token_jwt_generation_error(
        self, mock_generate_jwt: Mock, mock_parse_duration: Mock
    ) -> None:
        """Test generate-token when JWT generation fails."""
        mock_parse_duration.return_value = Success(data=30)
        mock_generate_jwt.return_value = Error(error="JWT generation failed")

        result = self.runner.invoke(cli, ["generate-token", "test-subject"])

        assert result.exit_code == 1
        assert "Error: JWT generation failed" in result.output

    @patch("vibectl.server.main.parse_duration")
    @patch("vibectl.server.main.load_config_with_generation")
    def test_generate_token_config_load_error(
        self, mock_load_config: Mock, mock_parse_duration: Mock
    ) -> None:
        """Test generate-token when config loading raises exception."""
        mock_parse_duration.return_value = Success(data=30)
        mock_load_config.side_effect = Exception("Config load failed")

        result = self.runner.invoke(cli, ["generate-token", "test-subject"])

        assert result.exit_code == 1
        assert "Error: Token generation failed: Config load failed" in result.output

    @patch("vibectl.server.main.parse_duration")
    @patch("vibectl.server.main.load_config_with_generation")
    @patch("vibectl.server.main.JWTAuthManager")
    def test_generate_token_output_file_write_error(
        self,
        mock_jwt_manager_class: Mock,
        mock_load_config: Mock,
        mock_parse_duration: Mock,
    ) -> None:
        """Test generate-token when output file write fails."""
        mock_parse_duration.return_value = Success(data=30)
        mock_config = Mock()
        mock_load_config.return_value = mock_config
        mock_jwt_manager = Mock()
        mock_jwt_manager_class.return_value = mock_jwt_manager
        mock_jwt_manager.generate_token.return_value = "test-token"

        # Use a path that will cause permission error
        result = self.runner.invoke(
            cli,
            ["generate-token", "test-subject", "--output", "/root/no-permission.txt"],
        )

        assert result.exit_code == 1
        assert "Error: Token generation failed:" in result.output


class TestInitConfigErrorPaths:
    """Test init-config command error handling paths."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("vibectl.server.main.ensure_config_dir")
    def test_init_config_ensure_dir_error(self, mock_ensure_dir: Mock) -> None:
        """Test init-config when ensure_config_dir fails."""
        mock_ensure_dir.side_effect = OSError("Permission denied")

        result = self.runner.invoke(cli, ["init-config"])

        assert result.exit_code == 1
        assert (
            "Error: Configuration initialization failed: Permission denied"
            in result.output
        )

    @patch("vibectl.server.main.ensure_config_dir")
    @patch("vibectl.server.main.create_default_server_config")
    @patch("pathlib.Path.exists")
    def test_init_config_create_default_error(
        self, mock_exists: Mock, mock_create_default: Mock, mock_ensure_dir: Mock
    ) -> None:
        """Test init-config when create_default_server_config fails."""
        config_dir = Path("/mock/config")
        mock_ensure_dir.return_value = config_dir
        mock_exists.return_value = False
        mock_create_default.return_value = Error(error="Failed to create config")

        result = self.runner.invoke(cli, ["init-config"])

        assert result.exit_code == 1
        assert "Error: Failed to create config" in result.output


class TestGenerateCertsErrorPaths:
    """Test generate-certs command error handling paths."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("vibectl.server.main._perform_certificate_generation")
    def test_generate_certs_certificate_generation_error(
        self, mock_perform_cert_gen: Mock
    ) -> None:
        """Test generate-certs when certificate generation fails."""
        mock_perform_cert_gen.return_value = Error(
            error="Certificate generation failed"
        )

        result = self.runner.invoke(cli, ["generate-certs"])

        assert result.exit_code == 1
        assert "Error: Certificate generation failed" in result.output

    @patch("vibectl.server.main.get_config_dir")
    @patch("pathlib.Path.exists")
    def test_generate_certs_files_exist_no_force(
        self, mock_exists: Mock, mock_get_config_dir: Mock
    ) -> None:
        """Test generate-certs when files exist and no force flag."""
        mock_get_config_dir.return_value = Path("/mock/config")
        mock_exists.return_value = True  # Files exist

        result = self.runner.invoke(cli, ["generate-certs"])

        assert result.exit_code == 1
        assert "Certificate files already exist" in result.output
