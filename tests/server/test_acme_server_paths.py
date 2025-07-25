"""
Tests for ACME server setup paths in vibectl.server.main.

This file specifically targets the uncovered ACME-related functions:
- _create_and_start_server_with_async_acme
- _async_acme_server_main
- Error handling in async ACME flows
"""

from typing import Any
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
            # Run the provided coroutine to completion in a fresh event loop so
            # that it is properly awaited (avoids RuntimeWarning about an
            # un-awaited coroutine).
            def _run(coro):  # type: ignore[no-untyped-def]
                import asyncio

                loop = asyncio.new_event_loop()
                try:
                    return loop.run_until_complete(coro)
                finally:
                    loop.close()

            mock_run.side_effect = _run

            # Mock _async_acme_server_main to avoid real network operations that
            # attempt to bind privileged ports (e.g., 80) during the test run.
            async def _success_coro():  # type: ignore[no-untyped-def]
                return Success()

            with patch(
                "vibectl.server.main._async_acme_server_main",
                Mock(return_value=_success_coro()),
            ):
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

            # Replace Thread constructor so that calling .start() executes the
            # target synchronously (in the current thread) and .join() becomes
            # a noop. This avoids spawning real threads while still running
            # the target coroutine and awaiting it, preventing coroutine-not-
            # awaited warnings.
            def _thread_ctor(*args: Any, **kwargs: Any) -> Any:  # type: ignore[override]
                target = kwargs.get("target") or (args[0] if args else None)

                class _DummyThread:
                    def __init__(self, _target: Any) -> None:
                        self._target = _target

                    def start(self) -> None:
                        if self._target is not None:
                            self._target()

                    def join(self) -> None:
                        # No-op because start() already executed synchronously
                        pass

                return _DummyThread(target)

            mock_thread.side_effect = _thread_ctor

            # Use regular Mock with return_value that creates a coroutine
            # Since _async_acme_server_main is called via asyncio.run(), we need
            # to mock it as a sync function that returns a coroutine
            async def mock_coro() -> Success:
                return Success()

            with patch(
                "vibectl.server.main._async_acme_server_main",
                Mock(return_value=mock_coro()),
            ):
                _create_and_start_server_with_async_acme(server_config)

            # Should use threading approach
            mock_thread.assert_called_once()

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
            patch("vibectl.server.main._signal_container_ready", return_value=None),
        ):
            # Create futures that are already completed
            import asyncio

            future_start: asyncio.Future[None] = asyncio.Future()
            future_start.set_result(None)

            future_wait_ready: asyncio.Future[bool] = asyncio.Future()
            future_wait_ready.set_result(True)

            future_stop: asyncio.Future[None] = asyncio.Future()
            future_stop.set_result(None)

            future_acme_start: asyncio.Future[Success] = asyncio.Future()
            future_acme_start.set_result(Success())

            # Mock challenge server
            mock_challenge_server = Mock()
            mock_challenge_server.start = Mock(return_value=future_start)
            mock_challenge_server.wait_until_ready = Mock(
                return_value=future_wait_ready
            )
            mock_challenge_server.stop = Mock(return_value=future_stop)
            mock_challenge_server_class.return_value = mock_challenge_server

            # Mock gRPC server
            mock_server = Mock()
            mock_server.start = Mock()
            mock_server.stop = Mock()
            mock_create_server.return_value = mock_server

            # Mock ACME manager
            mock_acme_manager = Mock()
            mock_acme_manager.start = Mock(return_value=future_acme_start)
            mock_acme_manager.stop = Mock(return_value=future_stop)
            mock_acme_manager_class.return_value = mock_acme_manager

            # Mock signal handling to avoid infinite wait without AsyncMock
            class _DummyEvent:
                async def wait(self) -> None:
                    raise KeyboardInterrupt()

                def set(self) -> None:
                    pass

            with (
                patch("signal.signal"),
                patch("asyncio.Event", return_value=_DummyEvent()),
            ):
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
            mock_challenge_server = Mock()
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
            patch("vibectl.server.main._signal_container_ready", return_value=None),
        ):
            # Mock TLS-ALPN challenge server
            mock_tls_challenge_server = Mock()
            mock_tls_challenge_server.stop = AsyncMock()
            mock_tls_challenge_class.return_value = mock_tls_challenge_server

            # Mock gRPC server
            mock_server = Mock()
            mock_server.start = Mock()
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

            # Mock signal handling to avoid infinite wait without AsyncMock
            class _DummyEvent:
                async def wait(self) -> None:
                    raise KeyboardInterrupt()

                def set(self) -> None:
                    pass

            with (
                patch("signal.signal"),
                patch("asyncio.Event", return_value=_DummyEvent()),
            ):
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
            patch("vibectl.server.main._signal_container_ready", return_value=None),
        ):
            # Mock TLS-ALPN challenge server - won't be called due to early exit
            mock_tls_challenge_server = Mock()
            mock_tls_challenge_server.stop = AsyncMock()
            mock_tls_challenge_class.return_value = mock_tls_challenge_server

            # Mock gRPC server - won't be called due to early exit
            mock_server = Mock()
            mock_server.stop = Mock()
            mock_create_server.return_value = mock_server

            # Mock ALPN multiplexer - won't be called due to early exit
            mock_multiplexer = AsyncMock()
            mock_multiplexer.stop = AsyncMock()
            mock_create_multiplexer.return_value = mock_multiplexer

            # Mock ACME manager - won't be called due to early exit
            mock_acme_manager = AsyncMock()
            mock_acme_manager.start = AsyncMock(return_value=Success())
            mock_acme_manager.stop = AsyncMock()
            mock_acme_manager_class.return_value = mock_acme_manager

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
            patch("vibectl.server.main._signal_container_ready", return_value=None),
        ):
            # Mock challenge server
            mock_challenge_server = Mock()
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
            patch("vibectl.server.main._signal_container_ready", return_value=None),
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

            # Mock signal handling to avoid infinite wait using DummyEvent
            class _DummyEvent:
                async def wait(self) -> None:
                    raise KeyboardInterrupt()

                def set(self) -> None:
                    pass

            with (
                patch("signal.signal"),
                patch("asyncio.Event", return_value=_DummyEvent()),
            ):
                result = await _async_acme_server_main(server_config)

                assert isinstance(result, Success)
                mock_server.start.assert_called_once()
                mock_acme_manager.start.assert_called_once()
                # Should not create challenge server for DNS-01
                mock_acme_manager_class.assert_called_once()
                args, kwargs = mock_acme_manager_class.call_args
                assert kwargs["challenge_server"] is None
