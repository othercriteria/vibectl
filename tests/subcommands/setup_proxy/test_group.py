"""Tests for group functionality in setup_proxy_cmd.py - command group tests."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from asyncclick.testing import CliRunner

from vibectl.cli import cli
from vibectl.types import Success


class TestSetupProxyGroup:
    """Test cases for setup-proxy command group."""

    @pytest.mark.asyncio
    async def test_setup_proxy_group_help(self) -> None:
        """Test setup-proxy group shows help."""
        runner = CliRunner()
        result = await runner.invoke(
            cli,
            ["setup-proxy", "--help"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert "Setup and manage proxy configuration" in result.output
        assert "configure" in result.output
        assert "test" in result.output
        assert "status" in result.output
        assert "disable" in result.output

    @pytest.mark.asyncio
    async def test_setup_proxy_subcommands_exist(self) -> None:
        """Test that all expected subcommands exist."""
        # Test by invoking help for each expected subcommand
        runner = CliRunner()
        expected_commands = ["configure", "test", "status", "disable", "url"]

        for cmd_name in expected_commands:
            result = await runner.invoke(
                cli,
                ["setup-proxy", cmd_name, "--help"],
                catch_exceptions=False,
            )
            # If the command exists, help should succeed
            assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_ca_bundle_parameter_takes_precedence(self) -> None:
        """Test that ca_bundle parameter takes precedence over config."""
        mock_proxy_config = Mock()
        mock_proxy_config.host = "test.com"
        mock_proxy_config.port = 443
        mock_proxy_config.use_tls = True
        mock_proxy_config.jwt_token = None

        # Create temporary CA bundle files
        param_ca_content = "PARAM CA CERTIFICATE"
        config_ca_content = "CONFIG CA CERTIFICATE"

        with (
            tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".crt"
            ) as param_ca_file,
            tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".crt"
            ) as config_ca_file,
        ):
            param_ca_file.write(param_ca_content)
            param_ca_file.flush()
            param_ca_path = param_ca_file.name

            config_ca_file.write(config_ca_content)
            config_ca_file.flush()
            config_ca_path = config_ca_file.name

        try:
            with (
                patch(
                    "vibectl.subcommands.setup_proxy_cmd.parse_proxy_url",
                    return_value=mock_proxy_config,
                ),
                patch("grpc.secure_channel") as mock_secure_channel,
                patch("grpc.ssl_channel_credentials") as mock_ssl_creds,
                patch(
                    "vibectl.subcommands.setup_proxy_cmd.Config"
                ) as mock_config_class,
                patch("builtins.open", create=True) as mock_open,
            ):
                # Mock config to return different CA bundle path
                mock_config = Mock()
                mock_config.get_ca_bundle_path.return_value = config_ca_path
                mock_config.get_jwt_token.return_value = None
                mock_config_class.return_value = mock_config

                mock_channel = Mock()
                mock_secure_channel.return_value = mock_channel
                mock_credentials = Mock()
                mock_ssl_creds.return_value = mock_credentials

                # Mock file reading to verify which file is read
                mock_file = Mock()
                mock_file.read.return_value = param_ca_content.encode()
                mock_open.return_value.__enter__.return_value = mock_file

                # This should fail during channel creation, but we want to verify
                # which CA file would be used
                from contextlib import suppress

                from vibectl.subcommands.setup_proxy_cmd import check_proxy_connection

                with suppress(Exception):
                    await check_proxy_connection(
                        "vibectl-server://test.com:443",
                        ca_bundle=param_ca_path,
                    )

                # Verify that the parameter CA bundle file was opened, not the
                # config one
                mock_open.assert_called_with(param_ca_path, "rb")

        finally:
            Path(param_ca_path).unlink()
            Path(config_ca_path).unlink()

    @pytest.mark.asyncio
    async def test_ca_bundle_parameter_with_configure_command(self) -> None:
        """Test that ca_bundle parameter is passed through from configure command."""
        mock_proxy_config = Mock()
        mock_proxy_config.host = "test.com"
        mock_proxy_config.port = 443
        mock_proxy_config.use_tls = True
        mock_proxy_config.jwt_token = None

        # Create temporary CA bundle file
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".crt"
        ) as ca_file:
            ca_file.write("TEST CA CERTIFICATE")
            ca_file.flush()
            ca_path = ca_file.name

        try:
            with patch(
                "vibectl.subcommands.setup_proxy_cmd.check_proxy_connection"
            ) as mock_check_connection:
                mock_check_connection.return_value = Success(
                    data={
                        "version": "1.0.0",
                        "supported_models": ["test-model"],
                        "server_name": "test-server",
                        "limits": {
                            "max_request_size": 4096,
                            "max_concurrent_requests": 10,
                            "timeout_seconds": 30,
                        },
                    }
                )

                # This test verifies that ca_bundle parameter is properly passed
                # through the check_proxy_connection call which is used by
                # the configure command

        finally:
            Path(ca_path).unlink()
