"""
Comprehensive tests for HTTP Challenge Server.

This module provides thorough test coverage for the HTTPChallengeServer class,
including initialization, configuration, challenge management, and HTTP endpoints.
"""

import asyncio
import tempfile
import threading
from collections.abc import Generator
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from aiohttp import web

from vibectl.server.http_challenge_server import (
    HTTPChallengeServer,
    TemporaryChallengeServer,
    start_challenge_server,
)


class TestHTTPChallengeServerInitialization:
    """Test HTTPChallengeServer initialization and configuration."""

    def test_init_default_params(self) -> None:
        """Test initialization with default parameters."""
        server = HTTPChallengeServer()

        assert server.host == "0.0.0.0"
        assert server.port == 80
        assert server.challenge_dir is None
        assert server.app is None
        assert server.runner is None
        assert server.site is None
        assert server._challenges == {}
        assert isinstance(server._lock, type(threading.Lock()))
        assert server._running is False
        assert isinstance(server._start_event, asyncio.Event)

    def test_init_custom_params(self) -> None:
        """Test initialization with custom parameters."""
        server = HTTPChallengeServer(
            host="127.0.0.1", port=8080, challenge_dir="/tmp/challenges"
        )

        assert server.host == "127.0.0.1"
        assert server.port == 8080
        assert server.challenge_dir == Path("/tmp/challenges")
        assert server._challenges == {}
        assert server._running is False

    def test_init_challenge_dir_none(self) -> None:
        """Test initialization with challenge_dir=None."""
        server = HTTPChallengeServer(challenge_dir=None)
        assert server.challenge_dir is None

    def test_init_challenge_dir_string(self) -> None:
        """Test initialization with challenge_dir as string."""
        server = HTTPChallengeServer(challenge_dir="/var/challenges")
        assert server.challenge_dir == Path("/var/challenges")

    def test_is_running_property(self) -> None:
        """Test the is_running property."""
        server = HTTPChallengeServer()
        assert server.is_running is False

        # Simulate running state
        server._running = True
        assert server.is_running is True

    def test_get_challenge_url(self) -> None:
        """Test get_challenge_url method."""
        server = HTTPChallengeServer(host="example.com", port=8080)

        url = server.get_challenge_url("test-token")
        assert url == "http://example.com:8080/.well-known/acme-challenge/test-token"

    def test_get_challenge_url_default_port(self) -> None:
        """Test get_challenge_url with default port."""
        server = HTTPChallengeServer(host="localhost", port=80)

        url = server.get_challenge_url("abc123")
        assert url == "http://localhost:80/.well-known/acme-challenge/abc123"


class TestHTTPChallengeServerChallengeManagement:
    """Test challenge management functionality."""

    def test_set_challenge(self) -> None:
        """Test setting a challenge token."""
        server = HTTPChallengeServer()

        server.set_challenge("token1", "response1")

        assert server._challenges["token1"] == "response1"

    def test_set_multiple_challenges(self) -> None:
        """Test setting multiple challenge tokens."""
        server = HTTPChallengeServer()

        server.set_challenge("token1", "response1")
        server.set_challenge("token2", "response2")

        assert server._challenges["token1"] == "response1"
        assert server._challenges["token2"] == "response2"
        assert len(server._challenges) == 2

    def test_remove_challenge(self) -> None:
        """Test removing a challenge token."""
        server = HTTPChallengeServer()

        server.set_challenge("token1", "response1")
        server.set_challenge("token2", "response2")

        server.remove_challenge("token1")

        assert "token1" not in server._challenges
        assert server._challenges["token2"] == "response2"

    def test_remove_nonexistent_challenge(self) -> None:
        """Test removing a non-existent challenge token (should not raise error)."""
        server = HTTPChallengeServer()

        # Should not raise an exception
        server.remove_challenge("nonexistent")

        assert len(server._challenges) == 0

    def test_clear_challenges(self) -> None:
        """Test clearing all challenge tokens."""
        server = HTTPChallengeServer()

        server.set_challenge("token1", "response1")
        server.set_challenge("token2", "response2")

        server.clear_challenges()

        assert len(server._challenges) == 0

    def test_challenge_management_thread_safety(self) -> None:
        """Test thread safety of challenge management."""
        server = HTTPChallengeServer()
        results = []

        def set_challenges() -> None:
            for i in range(100):
                server.set_challenge(f"token{i}", f"response{i}")
                results.append(f"set{i}")

        def remove_challenges() -> None:
            for i in range(50):
                server.remove_challenge(f"token{i}")
                results.append(f"remove{i}")

        # Run operations concurrently
        threads = [
            threading.Thread(target=set_challenges),
            threading.Thread(target=remove_challenges),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should not crash due to race conditions
        # Exact final state depends on timing, but should be consistent
        assert len(results) == 150  # 100 sets + 50 removes


class TestHTTPChallengeServerFilesystemOperations:
    """Test filesystem-based challenge operations."""

    @pytest.fixture
    def temp_challenge_dir(self) -> Generator[str, None, None]:
        """Create a temporary directory for challenge files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.mark.asyncio
    async def test_get_challenge_response_from_filesystem(
        self, temp_challenge_dir: str
    ) -> None:
        """Test retrieving challenge response from filesystem."""
        server = HTTPChallengeServer(challenge_dir=temp_challenge_dir)

        # Create a challenge file
        challenge_file = Path(temp_challenge_dir) / "test-token"
        challenge_file.write_text("test-response-content")

        response = await server._get_challenge_response("test-token")

        assert response == "test-response-content"

    @pytest.mark.asyncio
    async def test_get_challenge_response_from_filesystem_with_whitespace(
        self, temp_challenge_dir: str
    ) -> None:
        """Test retrieving challenge response strips whitespace."""
        server = HTTPChallengeServer(challenge_dir=temp_challenge_dir)

        # Create a challenge file with whitespace
        challenge_file = Path(temp_challenge_dir) / "test-token"
        challenge_file.write_text("  test-response-content  \n\t")

        response = await server._get_challenge_response("test-token")

        assert response == "test-response-content"

    @pytest.mark.asyncio
    async def test_get_challenge_response_filesystem_missing_file(
        self, temp_challenge_dir: str
    ) -> None:
        """Test retrieving non-existent challenge file."""
        server = HTTPChallengeServer(challenge_dir=temp_challenge_dir)

        response = await server._get_challenge_response("nonexistent-token")

        assert response is None

    @pytest.mark.asyncio
    async def test_get_challenge_response_filesystem_read_error(
        self, temp_challenge_dir: str
    ) -> None:
        """Test handling filesystem read errors."""
        server = HTTPChallengeServer(challenge_dir=temp_challenge_dir)

        # Create a directory with the token name (can't read as file)
        challenge_dir = Path(temp_challenge_dir) / "test-token"
        challenge_dir.mkdir()

        response = await server._get_challenge_response("test-token")

        # Should fall back to in-memory storage (None)
        assert response is None

    @pytest.mark.asyncio
    async def test_get_challenge_response_fallback_to_memory(
        self, temp_challenge_dir: str
    ) -> None:
        """Test fallback from filesystem to in-memory storage."""
        server = HTTPChallengeServer(challenge_dir=temp_challenge_dir)

        # Set challenge in memory
        server.set_challenge("memory-token", "memory-response")

        # File doesn't exist, should use memory
        response = await server._get_challenge_response("memory-token")

        assert response == "memory-response"

    @pytest.mark.asyncio
    async def test_get_challenge_response_filesystem_priority(
        self, temp_challenge_dir: str
    ) -> None:
        """Test that filesystem takes priority over in-memory storage."""
        server = HTTPChallengeServer(challenge_dir=temp_challenge_dir)

        # Set different values in file and memory
        challenge_file = Path(temp_challenge_dir) / "test-token"
        challenge_file.write_text("filesystem-response")
        server.set_challenge("test-token", "memory-response")

        response = await server._get_challenge_response("test-token")

        # Filesystem should take priority
        assert response == "filesystem-response"

    @pytest.mark.asyncio
    async def test_get_challenge_response_memory_only(self) -> None:
        """Test in-memory storage when no filesystem configured."""
        server = HTTPChallengeServer()  # No challenge_dir

        server.set_challenge("test-token", "memory-response")

        response = await server._get_challenge_response("test-token")

        assert response == "memory-response"


class TestHTTPChallengeServerAsyncLifecycle:
    """Test async server lifecycle operations."""

    @pytest.mark.asyncio
    async def test_create_app(self) -> None:
        """Test application creation."""
        server = HTTPChallengeServer()

        app = await server.create_app()

        assert isinstance(app, web.Application)
        # Check that routes are registered
        assert len(app.router._resources) > 0

    @pytest.mark.asyncio
    async def test_wait_until_ready_not_started(self) -> None:
        """Test wait_until_ready when server is not started."""
        server = HTTPChallengeServer()

        # Should timeout quickly since server isn't started
        ready = await server.wait_until_ready(timeout=0.1)

        assert ready is False

    @pytest.mark.asyncio
    async def test_wait_until_ready_timeout(self) -> None:
        """Test wait_until_ready timeout behavior."""
        server = HTTPChallengeServer()

        # Should timeout
        ready = await server.wait_until_ready(timeout=0.01)

        assert ready is False

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self) -> None:
        """Test stopping server when it's not running."""
        server = HTTPChallengeServer()

        # Should not raise an exception
        await server.stop()

        assert not server.is_running

    @pytest.mark.asyncio
    async def test_start_when_already_running(self) -> None:
        """Test starting server when it's already running."""
        server = HTTPChallengeServer()
        server._running = True  # Simulate running state

        # Should return without doing anything
        await server.start()

        # Should still be marked as running
        assert server.is_running

    @pytest.mark.asyncio
    async def test_cleanup_with_no_resources(self) -> None:
        """Test cleanup when no resources are allocated."""
        server = HTTPChallengeServer()

        # Should not raise an exception
        await server._cleanup()

        assert server.app is None
        assert server.runner is None
        assert server.site is None

    @pytest.mark.asyncio
    async def test_start_with_port_readiness_check(self) -> None:
        """Test server start with port readiness check for non-zero ports."""
        server = HTTPChallengeServer(
            host="127.0.0.1", port=0
        )  # Use port 0 to get auto-assigned port

        try:
            await server.start()
            assert server.is_running
            # Port 0 means auto-assign, so we don't update self.port in
            # our implementation
            # The actual port is handled internally by aiohttp
            assert server.port == 0  # Our implementation keeps the original port value
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_port_readiness_check_timeout(self) -> None:
        """Test port readiness check timeout behavior."""
        server = HTTPChallengeServer(
            host="127.0.0.1", port=12345
        )  # Use a specific port

        # Mock the port check to always fail
        with patch.object(server, "_wait_for_port_ready") as mock_wait:
            mock_wait.side_effect = RuntimeError(
                "Port 12345 not listening after 5.0 seconds"
            )

            with pytest.raises(
                RuntimeError, match="Port 12345 not listening after 5.0 seconds"
            ):
                await server.start()

    @pytest.mark.asyncio
    async def test_wait_for_port_ready_success(self) -> None:
        """Test successful port readiness check."""
        server = HTTPChallengeServer()

        # Mock socket connection to succeed immediately
        with patch("socket.socket") as mock_socket_class:
            mock_socket = Mock()
            mock_socket.connect_ex.return_value = 0  # Success
            mock_socket_class.return_value = mock_socket

            # Should complete without raising
            await server._wait_for_port_ready(8080, timeout=1.0)

            mock_socket.connect_ex.assert_called_once_with(("localhost", 8080))
            mock_socket.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_wait_for_port_ready_timeout_failure(self) -> None:
        """Test port readiness check timeout failure."""
        server = HTTPChallengeServer()

        # Mock socket connection to always fail
        with patch("socket.socket") as mock_socket_class:
            mock_socket = Mock()
            mock_socket.connect_ex.return_value = 1  # Connection refused
            mock_socket_class.return_value = mock_socket

            with pytest.raises(
                RuntimeError, match="Port 8080 not listening after 0.1 seconds"
            ):
                await server._wait_for_port_ready(8080, timeout=0.1)

    @pytest.mark.asyncio
    async def test_wait_for_port_ready_socket_exception(self) -> None:
        """Test port readiness check with socket exceptions."""
        server = HTTPChallengeServer()

        # Mock socket to raise exception
        with patch("socket.socket") as mock_socket_class:
            mock_socket = Mock()
            mock_socket.connect_ex.side_effect = OSError("Network error")
            mock_socket_class.return_value = mock_socket

            with pytest.raises(
                RuntimeError, match="Port 8080 not listening after 0.1 seconds"
            ):
                await server._wait_for_port_ready(8080, timeout=0.1)

    @pytest.mark.asyncio
    async def test_start_and_stop_full_lifecycle(self) -> None:
        """Test complete start and stop lifecycle."""
        server = HTTPChallengeServer(host="127.0.0.1", port=0)

        # Start server
        await server.start()
        assert server.is_running
        assert server.app is not None
        assert server.runner is not None
        assert server.site is not None

        # Stop server
        await server.stop()
        assert not server.is_running
        assert server.app is None
        assert server.runner is None
        assert server.site is None

    @pytest.mark.asyncio
    async def test_start_failure_cleanup(self) -> None:
        """Test that cleanup happens when start fails."""
        server = HTTPChallengeServer(host="127.0.0.1", port=12345)

        # Mock site.start to fail
        with patch("aiohttp.web.TCPSite") as mock_site_class:
            mock_site = Mock()
            mock_site.start.side_effect = OSError("Address already in use")
            mock_site_class.return_value = mock_site

            with patch.object(server, "_cleanup") as mock_cleanup:
                with pytest.raises(OSError, match="Address already in use"):
                    await server.start()

                # Cleanup should have been called
                mock_cleanup.assert_called_once()


class TestHTTPChallengeServerHTTPEndpoints:
    """Test HTTP endpoint handling."""

    @pytest.fixture
    def server(self) -> HTTPChallengeServer:
        """Create a server instance for testing."""
        return HTTPChallengeServer(host="127.0.0.1", port=8080)

    @pytest.fixture
    def mock_request(self) -> Mock:
        """Create a mock request object."""
        request = Mock()
        request.match_info = {}
        return request

    @pytest.mark.asyncio
    async def test_handle_health_endpoint(
        self, server: HTTPChallengeServer, mock_request: Mock
    ) -> None:
        """Test health check endpoint."""
        response = await server._handle_health(mock_request)

        assert response.text == "OK"
        assert response.content_type == "text/plain"
        assert response.status == 200

    @pytest.mark.asyncio
    async def test_handle_catchall_endpoint(
        self, server: HTTPChallengeServer, mock_request: Mock
    ) -> None:
        """Test catch-all endpoint."""
        mock_request.match_info = {"path": "some/random/path"}

        response = await server._handle_catchall(mock_request)

        assert response.text is not None
        assert "vibectl HTTP challenge server" in response.text
        assert "Path: /some/random/path" in response.text
        assert response.status == 404
        assert response.content_type == "text/plain"

    @pytest.mark.asyncio
    async def test_handle_catchall_endpoint_empty_path(
        self, server: HTTPChallengeServer, mock_request: Mock
    ) -> None:
        """Test catch-all endpoint with empty path."""
        mock_request.match_info = {}  # No path key

        response = await server._handle_catchall(mock_request)

        assert response.text is not None
        assert "vibectl HTTP challenge server" in response.text
        assert "Path: /" in response.text

    @pytest.mark.asyncio
    async def test_handle_challenge_endpoint_found(
        self, server: HTTPChallengeServer, mock_request: Mock
    ) -> None:
        """Test challenge endpoint when token is found."""
        mock_request.match_info = {"token": "test-token"}
        server.set_challenge("test-token", "test-response")

        response = await server._handle_challenge(mock_request)

        assert response.text == "test-response"
        assert response.content_type == "text/plain"
        assert response.status == 200

    @pytest.mark.asyncio
    async def test_handle_challenge_endpoint_not_found(
        self, server: HTTPChallengeServer, mock_request: Mock
    ) -> None:
        """Test challenge endpoint when token is not found."""
        mock_request.match_info = {"token": "nonexistent-token"}

        response = await server._handle_challenge(mock_request)

        assert response.text is not None
        assert "Challenge token not found: nonexistent-token" in response.text
        assert response.status == 404

    @pytest.mark.asyncio
    async def test_handle_challenge_endpoint_with_filesystem(
        self, server: HTTPChallengeServer, mock_request: Mock
    ) -> None:
        """Test challenge endpoint with filesystem storage."""
        with tempfile.TemporaryDirectory() as temp_dir:
            server.challenge_dir = Path(temp_dir)
            challenge_file = Path(temp_dir) / "fs-token"
            challenge_file.write_text("filesystem-response")

            mock_request.match_info = {"token": "fs-token"}

            response = await server._handle_challenge(mock_request)

            assert response.text == "filesystem-response"
            assert response.status == 200

    @pytest.mark.asyncio
    async def test_handle_challenge_endpoint_filesystem_error_fallback(
        self, server: HTTPChallengeServer, mock_request: Mock
    ) -> None:
        """Test challenge endpoint fallback when filesystem has errors."""
        with tempfile.TemporaryDirectory() as temp_dir:
            server.challenge_dir = Path(temp_dir)
            # Create a directory with the token name (will cause read error)
            challenge_dir = Path(temp_dir) / "problematic-token"
            challenge_dir.mkdir()

            # Set fallback in memory
            server.set_challenge("problematic-token", "memory-fallback")

            mock_request.match_info = {"token": "problematic-token"}

            response = await server._handle_challenge(mock_request)

            assert response.text == "memory-fallback"
            assert response.status == 200

    @pytest.mark.asyncio
    async def test_create_app_routes(self, server: HTTPChallengeServer) -> None:
        """Test that all expected routes are created."""
        app = await server.create_app()

        # Check that the expected routes exist
        route_patterns = [str(resource.canonical) for resource in app.router._resources]

        # Should have challenge route, health route, and catch-all route
        assert "/.well-known/acme-challenge/{token}" in route_patterns
        assert "/health" in route_patterns
        assert (
            "/{path}" in route_patterns
        )  # Canonical form simplifies {path:.*} to {path}


class TestHTTPChallengeServerUtilityFunctions:
    """Test utility functions and helper methods."""

    @pytest.mark.asyncio
    async def test_start_challenge_server_function(self) -> None:
        """Test the start_challenge_server utility function."""
        server = await start_challenge_server(
            host="127.0.0.1", port=0
        )  # port 0 = random available port

        try:
            assert server.is_running
            assert server.host == "127.0.0.1"
            assert server.port == 0
            assert server.challenge_dir is None
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_start_challenge_server_with_challenge_dir(self) -> None:
        """Test start_challenge_server with challenge directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            server = await start_challenge_server(
                host="127.0.0.1", port=0, challenge_dir=temp_dir
            )

            try:
                assert server.is_running
                assert server.challenge_dir == Path(temp_dir)
            finally:
                await server.stop()


class TestTemporaryChallengeServer:
    """Test the TemporaryChallengeServer context manager."""

    @pytest.mark.asyncio
    async def test_temporary_challenge_server_context_manager(self) -> None:
        """Test the context manager functionality."""
        async with TemporaryChallengeServer(host="127.0.0.1", port=0) as server:
            assert isinstance(server, HTTPChallengeServer)
            assert server.is_running
            assert server.host == "127.0.0.1"

        # Server should be stopped after context exit
        assert not server.is_running

    @pytest.mark.asyncio
    async def test_temporary_challenge_server_with_challenge_dir(self) -> None:
        """Test temporary server with challenge directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            async with TemporaryChallengeServer(
                host="127.0.0.1", port=0, challenge_dir=temp_dir
            ) as server:
                assert server.challenge_dir == Path(temp_dir)
                assert server.is_running

            assert not server.is_running

    @pytest.mark.asyncio
    async def test_temporary_challenge_server_exception_handling(self) -> None:
        """Test that temporary server is properly cleaned up on exception."""
        server_ref = None

        try:
            async with TemporaryChallengeServer(host="127.0.0.1", port=0) as server:
                server_ref = server
                assert server.is_running
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Server should be stopped even after exception
        assert server_ref is not None
        assert not server_ref.is_running

    @patch("vibectl.server.http_challenge_server.logger")
    def test_sensitive_token_redaction_in_logs(self, mock_logger: Mock) -> None:
        """Test that challenge tokens are redacted in debug logs."""
        server = HTTPChallengeServer()

        # Test token operations that should redact sensitive data
        test_token = "very_long_secret_challenge_token_123456789"
        test_response = "challenge_response_data"

        # Test set_challenge
        server.set_challenge(test_token, test_response)

        # Verify debug log redacts the token
        debug_calls = list(mock_logger.debug.call_args_list)
        set_token_logged = False
        for call in debug_calls:
            call_msg = call[0][0]  # Extract the message from the call
            if "Set challenge token:" in call_msg:
                set_token_logged = True
                # Should log partial token but not the full token
                assert test_token[:8] in call_msg  # First 8 chars should be logged
                assert test_token not in call_msg  # Full token should not be logged

        assert set_token_logged, "Set challenge token should be logged with redaction"

        # Test remove_challenge
        server.remove_challenge(test_token)

        # Verify debug log redacts the token
        debug_calls = list(mock_logger.debug.call_args_list)
        remove_token_logged = False
        for call in debug_calls:
            call_msg = call[0][0]  # Extract the message from the call
            if "Removed challenge token:" in call_msg:
                remove_token_logged = True
                # Should log partial token but not the full token
                assert test_token[:8] in call_msg  # First 8 chars should be logged
                assert test_token not in call_msg  # Full token should not be logged

        assert remove_token_logged, (
            "Remove challenge token should be logged with redaction"
        )

    @patch("vibectl.server.http_challenge_server.logger")
    async def test_challenge_request_token_redaction(self, mock_logger: Mock) -> None:
        """Test that tokens in challenge requests are redacted in logs."""
        server = HTTPChallengeServer()

        # Test the actual _handle_challenge method with a simple mock request
        test_token = "another_long_secret_token_abcdefghijk"
        test_response = "test_challenge_response"
        server.set_challenge(test_token, test_response)

        # Reset mock to focus on request handling
        mock_logger.debug.reset_mock()
        mock_logger.info.reset_mock()
        mock_logger.warning.reset_mock()

        # Create a simple mock request
        mock_request = Mock()
        mock_request.match_info = {"token": test_token}

        # Mock the _get_challenge_response method to return our test response
        with patch.object(
            server, "_get_challenge_response", return_value=test_response
        ):
            # Handle the challenge request
            response = await server._handle_challenge(mock_request)

        # Verify response is correct
        assert response.status == 200

        # Verify that logs redact the token
        all_calls = (
            mock_logger.debug.call_args_list
            + mock_logger.info.call_args_list
            + mock_logger.warning.call_args_list
        )

        token_request_logged = False
        token_serving_logged = False

        for call in all_calls:
            call_msg = call[0][0] if call[0] else ""
            if "ACME challenge request for token:" in call_msg:
                token_request_logged = True
                assert test_token not in call_msg  # Full token should not be logged
                assert test_token[:8] in call_msg  # First 8 chars should be logged
            elif "Serving ACME challenge for token:" in call_msg:
                token_serving_logged = True
                assert test_token not in call_msg  # Full token should not be logged
                assert test_token[:8] in call_msg  # First 8 chars should be logged

        assert token_request_logged, "Challenge request should be logged with redaction"
        assert token_serving_logged, "Challenge serving should be logged with redaction"
