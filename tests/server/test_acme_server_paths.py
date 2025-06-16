"""
Tests for ACME server setup paths in vibectl.server.main.

This file specifically targets the uncovered ACME-related functions:
- _create_and_start_server_with_async_acme
- _async_acme_server_main
- Error handling in async ACME flows
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from vibectl.server.main import (
    _async_acme_server_main,
    _create_and_start_server_with_async_acme,
)
from vibectl.types import Error, Success


class TestACMEServerSetupPaths:
    """Test ACME server setup paths that are missing coverage."""

    def test_create_and_start_server_with_async_acme_no_event_loop(self) -> None:
        """Test ACME server creation when no event loop is running."""
        server_config = {
            "server": {
                "host": "localhost",
                "port": 443,
                "max_workers": 5,
                "log_level": "INFO",
            },
            "acme": {"enabled": True, "challenge": {"type": "http-01"}},
            "tls": {"enabled": True},
            "jwt": {"enabled": False},
        }

        with patch("vibectl.server.main.asyncio.run") as mock_run:
            mock_run.return_value = Success()

            result = _create_and_start_server_with_async_acme(server_config)

            assert isinstance(result, Success)
            mock_run.assert_called_once()

    def test_create_and_start_server_with_async_acme_existing_event_loop(self) -> None:
        """Test ACME server creation when event loop is already running."""
        server_config = {
            "server": {
                "host": "localhost",
                "port": 443,
                "max_workers": 5,
                "log_level": "INFO",
            },
            "acme": {"enabled": True, "challenge": {"type": "http-01"}},
            "tls": {"enabled": True},
            "jwt": {"enabled": False},
        }

        with (
            patch("asyncio.get_running_loop") as mock_get_loop,
            patch("threading.Thread") as mock_thread,
        ):
            # Simulate event loop running
            mock_get_loop.return_value = Mock()
            mock_thread_instance = Mock()
            mock_thread.return_value = mock_thread_instance

            # Mock the thread execution to set the result
            def mock_thread_target() -> None:
                # This simulates the run_async_server function
                pass

            mock_thread_instance.start = Mock()
            mock_thread_instance.join = Mock()

            with patch(
                "vibectl.server.main._async_acme_server_main"
            ) as mock_async_main:
                mock_async_main.return_value = Success()

                _create_and_start_server_with_async_acme(server_config)

                # Should use threading approach
                mock_thread.assert_called_once()
                mock_thread_instance.start.assert_called_once()
                mock_thread_instance.join.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_acme_server_main_http01_challenge(self) -> None:
        """Test async ACME server main with HTTP-01 challenge."""
        server_config = {
            "server": {
                "host": "localhost",
                "port": 443,
                "max_workers": 5,
                "log_level": "INFO",
            },
            "acme": {"enabled": True, "challenge": {"type": "http-01"}},
            "tls": {"enabled": True},
            "jwt": {"enabled": False},
            "http": {"host": "0.0.0.0", "port": 80},
        }

        with (
            patch("vibectl.server.main._update_logging_level_from_config"),
            patch(
                "vibectl.server.http_challenge_server.HTTPChallengeServer"
            ) as mock_challenge_server_class,
            patch(
                "vibectl.server.main._create_grpc_server_with_temp_certs"
            ) as mock_create_server,
            patch("vibectl.server.acme_manager.ACMEManager") as mock_acme_manager_class,
            patch("vibectl.server.main._signal_container_ready"),
        ):
            # Mock challenge server
            mock_challenge_server = AsyncMock()
            mock_challenge_server.start = AsyncMock()
            mock_challenge_server.wait_until_ready = AsyncMock(return_value=True)
            mock_challenge_server.stop = AsyncMock()
            mock_challenge_server_class.return_value = mock_challenge_server

            # Mock gRPC server
            mock_server = Mock()
            mock_server.start = Mock()
            mock_server.stop = Mock()
            mock_create_server.return_value = mock_server

            # Mock ACME manager
            mock_acme_manager = AsyncMock()
            mock_acme_manager.start = AsyncMock(return_value=Success())
            mock_acme_manager.stop = AsyncMock()
            mock_acme_manager_class.return_value = mock_acme_manager

            # Mock signal handling to avoid infinite wait
            with patch("signal.signal"), patch("asyncio.Event") as mock_event_class:
                mock_event = AsyncMock()
                mock_event.wait = AsyncMock(side_effect=KeyboardInterrupt())
                mock_event_class.return_value = mock_event

                result = await _async_acme_server_main(server_config)

                assert isinstance(result, Success)
                mock_challenge_server.start.assert_called_once()
                mock_challenge_server.wait_until_ready.assert_called_once()
                mock_server.start.assert_called_once()
                mock_acme_manager.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_acme_server_main_http01_challenge_server_failed(self) -> None:
        """Test async ACME server main when HTTP challenge server fails to start."""
        server_config = {
            "server": {
                "host": "localhost",
                "port": 443,
                "max_workers": 5,
                "log_level": "INFO",
            },
            "acme": {"enabled": True, "challenge": {"type": "http-01"}},
            "tls": {"enabled": True},
            "jwt": {"enabled": False},
            "http": {"host": "0.0.0.0", "port": 80},
        }

        with (
            patch("vibectl.server.main._update_logging_level_from_config"),
            patch(
                "vibectl.server.http_challenge_server.HTTPChallengeServer"
            ) as mock_challenge_server_class,
        ):
            # Mock challenge server that fails to be ready
            mock_challenge_server = AsyncMock()
            mock_challenge_server.start = AsyncMock()
            mock_challenge_server.wait_until_ready = AsyncMock(return_value=False)
            mock_challenge_server.stop = AsyncMock()
            mock_challenge_server_class.return_value = mock_challenge_server

            result = await _async_acme_server_main(server_config)

            assert isinstance(result, Error)
            assert "HTTP challenge server failed to start" in result.error

    @pytest.mark.asyncio
    async def test_async_acme_server_main_tls_alpn01_challenge(self) -> None:
        """Test async ACME server main with TLS-ALPN-01 challenge."""
        server_config = {
            "server": {
                "host": "localhost",
                "port": 443,
                "max_workers": 5,
                "log_level": "INFO",
            },
            "acme": {"enabled": True, "challenge": {"type": "tls-alpn-01"}},
            "tls": {
                "enabled": True,
                "cert_file": "/test/cert.pem",
                "key_file": "/test/key.pem",
            },
            "jwt": {"enabled": False},
        }

        with (
            patch("vibectl.server.main._update_logging_level_from_config"),
            patch(
                "vibectl.server.tls_alpn_challenge_server.TLSALPNChallengeServer"
            ) as mock_tls_challenge_class,
            patch(
                "vibectl.server.main._create_grpc_server_with_temp_certs"
            ) as mock_create_server,
            patch(
                "vibectl.server.alpn_multiplexer.create_alpn_multiplexer_for_acme"
            ) as mock_create_multiplexer,
            patch("vibectl.server.acme_manager.ACMEManager") as mock_acme_manager_class,
            patch("vibectl.server.main._signal_container_ready"),
        ):
            # Mock TLS-ALPN challenge server
            mock_tls_challenge_server = Mock()
            mock_tls_challenge_server.stop = AsyncMock()
            mock_tls_challenge_class.return_value = mock_tls_challenge_server

            # Mock gRPC server
            mock_server = Mock()
            mock_server.stop = Mock()
            mock_create_server.return_value = mock_server

            # Mock ALPN multiplexer
            mock_multiplexer = AsyncMock()
            mock_multiplexer.stop = AsyncMock()
            mock_create_multiplexer.return_value = mock_multiplexer

            # Mock ACME manager
            mock_acme_manager = AsyncMock()
            mock_acme_manager.start = AsyncMock(return_value=Success())
            mock_acme_manager.stop = AsyncMock()
            mock_acme_manager_class.return_value = mock_acme_manager

            # Mock infinite wait with interrupt
            with patch("asyncio.Event") as mock_event_class:
                mock_event = AsyncMock()
                mock_event.wait = AsyncMock(side_effect=KeyboardInterrupt())
                mock_event_class.return_value = mock_event

                result = await _async_acme_server_main(server_config)

                assert isinstance(result, Success)
                mock_create_multiplexer.assert_called_once()
                mock_acme_manager.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_acme_server_main_tls_alpn01_missing_certs(self) -> None:
        """Test async ACME server main with TLS-ALPN-01 but no certificate files."""
        server_config = {
            "server": {
                "host": "localhost",
                "port": 443,
                "max_workers": 5,
                "log_level": "INFO",
                "default_model": "test-model",
            },
            "acme": {"enabled": True, "challenge": {"type": "tls-alpn-01"}},
            "tls": {"enabled": True, "cert_file": None, "key_file": None},
            "jwt": {"enabled": False},
        }

        with (
            patch("vibectl.server.main._update_logging_level_from_config"),
            patch(
                "vibectl.server.tls_alpn_challenge_server.TLSALPNChallengeServer"
            ) as mock_tls_challenge_class,
            patch(
                "vibectl.server.main._create_grpc_server_with_temp_certs"
            ) as mock_create_server,
            patch(
                "vibectl.server.alpn_multiplexer.create_alpn_multiplexer_for_acme"
            ) as mock_create_multiplexer,
            patch("vibectl.server.acme_manager.ACMEManager") as mock_acme_manager_class,
            patch("vibectl.server.main._signal_container_ready"),
        ):
            # Mock TLS-ALPN challenge server
            mock_tls_challenge_server = Mock()
            mock_tls_challenge_server.stop = AsyncMock()
            mock_tls_challenge_class.return_value = mock_tls_challenge_server

            # Mock gRPC server
            mock_server = Mock()
            mock_server.stop = Mock()
            mock_create_server.return_value = mock_server

            # Mock ALPN multiplexer
            mock_multiplexer = AsyncMock()
            mock_multiplexer.stop = AsyncMock()
            mock_create_multiplexer.return_value = mock_multiplexer

            # Mock ACME manager
            mock_acme_manager = AsyncMock()
            mock_acme_manager.start = AsyncMock(return_value=Success())
            mock_acme_manager.stop = AsyncMock()
            mock_acme_manager_class.return_value = mock_acme_manager

            # Mock infinite wait with interrupt
            with patch("asyncio.Event") as mock_event_class:
                mock_event = AsyncMock()
                mock_event.wait = AsyncMock(side_effect=KeyboardInterrupt())
                mock_event_class.return_value = mock_event

                result = await _async_acme_server_main(server_config)

                # When cert files are None for TLS-ALPN-01, it should fail
                assert isinstance(result, Error)
                assert "TLS certificate files required for TLS-ALPN-01" in result.error

    @pytest.mark.asyncio
    async def test_async_acme_server_main_acme_manager_failed(self) -> None:
        """Test async ACME server main when ACME manager fails to start."""
        server_config = {
            "server": {
                "host": "localhost",
                "port": 443,
                "max_workers": 5,
                "log_level": "INFO",
            },
            "acme": {"enabled": True, "challenge": {"type": "http-01"}},
            "tls": {"enabled": True},
            "jwt": {"enabled": False},
            "http": {"host": "0.0.0.0", "port": 80},
        }

        with (
            patch("vibectl.server.main._update_logging_level_from_config"),
            patch(
                "vibectl.server.http_challenge_server.HTTPChallengeServer"
            ) as mock_challenge_server_class,
            patch(
                "vibectl.server.main._create_grpc_server_with_temp_certs"
            ) as mock_create_server,
            patch("vibectl.server.acme_manager.ACMEManager") as mock_acme_manager_class,
            patch("vibectl.server.main._signal_container_ready"),
        ):
            # Mock challenge server
            mock_challenge_server = AsyncMock()
            mock_challenge_server.start = AsyncMock()
            mock_challenge_server.wait_until_ready = AsyncMock(return_value=True)
            mock_challenge_server.stop = AsyncMock()
            mock_challenge_server_class.return_value = mock_challenge_server

            # Mock gRPC server
            mock_server = Mock()
            mock_server.start = Mock()
            mock_server.stop = Mock()
            mock_create_server.return_value = mock_server

            # Mock ACME manager that fails to start
            mock_acme_manager = AsyncMock()
            mock_acme_manager.start = AsyncMock(
                return_value=Error(error="ACME setup failed")
            )
            mock_acme_manager.stop = AsyncMock()
            mock_acme_manager_class.return_value = mock_acme_manager

            result = await _async_acme_server_main(server_config)

            assert isinstance(result, Error)
            # The function should return the ACME manager's error
            assert "ACME setup failed" in result.error

    @pytest.mark.asyncio
    async def test_async_acme_server_main_exception_handling(self) -> None:
        """Test async ACME server main with exception during setup."""
        server_config = {
            "server": {
                "host": "localhost",
                "port": 443,
                "max_workers": 5,
                "log_level": "INFO",
            },
            "acme": {"enabled": True, "challenge": {"type": "http-01"}},
            "tls": {"enabled": True},
            "jwt": {"enabled": False},
            "http": {"host": "0.0.0.0", "port": 80},
        }

        with patch(
            "vibectl.server.main._update_logging_level_from_config",
            side_effect=Exception("Config error"),
        ):
            result = await _async_acme_server_main(server_config)

            assert isinstance(result, Error)
            assert "Async ACME server startup failed: Config error" in result.error

    @pytest.mark.asyncio
    async def test_async_acme_server_main_dns01_challenge(self) -> None:
        """Test async ACME server main with DNS-01 challenge (no challenge server)."""
        server_config = {
            "server": {
                "host": "localhost",
                "port": 443,
                "max_workers": 5,
                "log_level": "INFO",
            },
            "acme": {"enabled": True, "challenge": {"type": "dns-01"}},
            "tls": {"enabled": True},
            "jwt": {"enabled": False},
        }

        with (
            patch("vibectl.server.main._update_logging_level_from_config"),
            patch(
                "vibectl.server.main._create_grpc_server_with_temp_certs"
            ) as mock_create_server,
            patch("vibectl.server.acme_manager.ACMEManager") as mock_acme_manager_class,
            patch("vibectl.server.main._signal_container_ready"),
        ):
            # Mock gRPC server
            mock_server = Mock()
            mock_server.start = Mock()
            mock_server.stop = Mock()
            mock_create_server.return_value = mock_server

            # Mock ACME manager
            mock_acme_manager = AsyncMock()
            mock_acme_manager.start = AsyncMock(return_value=Success())
            mock_acme_manager.stop = AsyncMock()
            mock_acme_manager_class.return_value = mock_acme_manager

            # Mock signal handling to avoid infinite wait
            with patch("signal.signal"), patch("asyncio.Event") as mock_event_class:
                mock_event = AsyncMock()
                mock_event.wait = AsyncMock(side_effect=KeyboardInterrupt())
                mock_event_class.return_value = mock_event

                result = await _async_acme_server_main(server_config)

                assert isinstance(result, Success)
                mock_server.start.assert_called_once()
                mock_acme_manager.start.assert_called_once()
                # Should not create challenge server for DNS-01
                mock_acme_manager_class.assert_called_once()
                args, kwargs = mock_acme_manager_class.call_args
                assert kwargs["challenge_server"] is None
