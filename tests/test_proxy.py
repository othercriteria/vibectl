"""Tests for the proxy module.

This module tests the proxy.py module which implements TCP proxying for
port-forward traffic monitoring.
"""

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from vibectl.proxy import (
    ProxyStats,
    StatsProtocol,
    TcpProxy,
    start_proxy_server,
    stop_proxy_server,
)


class AsyncMockClass(MagicMock):
    """Mock class that supports async magic methods."""

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return super().__call__(*args, **kwargs)

    async def __aexit__(self, *args: Any, **kwargs: Any) -> Any:
        return super().__aexit__(*args, **kwargs)

    async def __aenter__(self, *args: Any, **kwargs: Any) -> Any:
        return super().__aenter__(*args, **kwargs)


@pytest.fixture
def mock_asyncio_components() -> dict:
    """Mock asyncio components for proxy testing."""
    # Create mock server
    mock_server = Mock()
    mock_server.close = Mock()
    mock_server.wait_closed = AsyncMockClass()

    # Create mock readers and writers
    mock_client_reader = Mock()
    mock_client_writer = Mock()
    mock_client_writer.close = Mock()
    mock_client_writer.drain = AsyncMockClass()

    mock_target_reader = Mock()
    mock_target_writer = Mock()
    mock_target_writer.close = Mock()
    mock_target_writer.drain = AsyncMockClass()

    # Create mock for connection
    mock_task = Mock()
    mock_task.cancel = Mock()

    # Return all mocks in a dictionary
    return {
        "server": mock_server,
        "client_reader": mock_client_reader,
        "client_writer": mock_client_writer,
        "target_reader": mock_target_reader,
        "target_writer": mock_target_writer,
        "task": mock_task,
    }


def test_proxy_stats_basic() -> None:
    """Test basic functionality of ProxyStats class."""
    # Create stats object
    stats = ProxyStats()

    # Test initial values
    assert stats.bytes_received == 0
    assert stats.bytes_sent == 0
    assert stats.last_activity >= 0  # Should be a timestamp

    # Test last_activity property
    initial_ts = stats.last_activity
    assert initial_ts == stats.last_activity

    # Test last_activity setter
    new_time = time.time()
    stats.last_activity = new_time
    assert stats.last_activity == new_time


def create_test_stats() -> StatsProtocol:
    """Create and return a test implementation of StatsProtocol.

    This function exists to prevent pytest from collecting the TestStats
    class as a test class.

    Returns:
        A StatsProtocol implementation with last_activity_timestamp attribute.
    """

    class TestStats(StatsProtocol):
        """Test implementation of StatsProtocol."""

        def __init__(self) -> None:
            """Initialize test stats with default values."""
            self.bytes_received: int = 0
            self.bytes_sent: int = 0
            self.last_activity_timestamp: float = 0

        @property
        def last_activity(self) -> float:
            """Get the last activity timestamp."""
            return self.last_activity_timestamp

        @last_activity.setter
        def last_activity(self, value: float) -> None:
            """Set the last activity timestamp."""
            self.last_activity_timestamp = value

    # The object actually has a last_activity_timestamp attribute
    # but mypy doesn't know that because it's not in StatsProtocol
    result = TestStats()
    return result


def test_stats_protocol_implementation() -> None:
    """Test that custom stats classes can implement StatsProtocol."""
    # Create test stats object
    stats = create_test_stats()

    # Test initial values
    assert stats.bytes_received == 0
    assert stats.bytes_sent == 0
    assert stats.last_activity == 0  # Use property only

    # Test property and setter
    stats.last_activity = 12345.67
    assert stats.last_activity == 12345.67


@patch("vibectl.proxy.logger.info")
@patch("asyncio.start_server", new_callable=AsyncMockClass)
def test_tcp_proxy_start(
    mock_start_server: AsyncMockClass, mock_log_info: Mock
) -> None:
    """Test TcpProxy.start method."""
    # Setup mocks
    mock_server = Mock()
    mock_start_server.return_value = mock_server

    # Create proxy object
    stats = create_test_stats()
    proxy = TcpProxy(
        local_port=8080, target_host="127.0.0.1", target_port=9090, stats=stats
    )

    # Call start method
    asyncio.run(proxy.start())

    # Verify server was started with correct params
    mock_start_server.assert_called_once_with(proxy._handle_client, "127.0.0.1", 8080)
    assert proxy.server == mock_server
    mock_log_info.assert_called_once()


@patch("vibectl.proxy.logger.error")
@patch("asyncio.start_server", new_callable=AsyncMockClass)
def test_tcp_proxy_start_error(
    mock_start_server: AsyncMockClass, mock_log_error: Mock
) -> None:
    """Test TcpProxy.start method with error."""
    # Setup mocks to raise exception
    mock_start_server.side_effect = Exception("Failed to start server")

    # Create proxy object
    stats = create_test_stats()
    proxy = TcpProxy(
        local_port=8080, target_host="127.0.0.1", target_port=9090, stats=stats
    )

    # Call start method and expect exception
    with pytest.raises(Exception, match="Failed to start server"):
        asyncio.run(proxy.start())

    # Verify error was logged
    mock_log_error.assert_called_once()


@patch("vibectl.proxy.logger.info")
def test_tcp_proxy_stop(mock_log_info: Mock, mock_asyncio_components: dict) -> None:
    """Test TcpProxy.stop method."""
    # Setup proxy with mock server
    stats = create_test_stats()
    proxy = TcpProxy(
        local_port=8080, target_host="127.0.0.1", target_port=9090, stats=stats
    )
    proxy.server = mock_asyncio_components["server"]

    # Add mock connection to the set
    proxy.connections.add(mock_asyncio_components["task"])

    # Call stop method
    asyncio.run(proxy.stop())

    # Verify server was closed
    mock_asyncio_components["server"].close.assert_called_once()
    mock_asyncio_components["server"].wait_closed.assert_called_once()

    # Verify connections were cancelled
    mock_asyncio_components["task"].cancel.assert_called_once()
    assert len(proxy.connections) == 0
    mock_log_info.assert_called_once()


@patch("vibectl.proxy.logger.error")
@patch("asyncio.open_connection", new_callable=AsyncMockClass)
def test_handle_client_connection_error(
    mock_open_connection: AsyncMockClass,
    mock_log_error: Mock,
    mock_asyncio_components: dict,
) -> None:
    """Test _handle_client method with connection error."""
    # Setup mock to raise exception
    mock_open_connection.side_effect = Exception("Connection failed")

    # Create proxy
    stats = create_test_stats()
    proxy = TcpProxy(
        local_port=8080, target_host="127.0.0.1", target_port=9090, stats=stats
    )

    # Call handle_client (it should now handle the error internally and return)
    asyncio.run(
        proxy._handle_client(
            mock_asyncio_components["client_reader"],
            mock_asyncio_components["client_writer"],
        )
    )

    # Assert logger.error was called
    mock_log_error.assert_called_once()
    # Assert client_writer.close was called
    mock_asyncio_components["client_writer"].close.assert_called_once()


@patch("asyncio.open_connection", new_callable=AsyncMockClass)
@patch("asyncio.gather", new_callable=AsyncMockClass)
def test_handle_client(
    mock_gather: AsyncMockClass,
    mock_open_connection: AsyncMockClass,
    mock_asyncio_components: dict,
) -> None:
    """Test _handle_client method."""
    # Setup mocks
    mock_open_connection.return_value = (
        mock_asyncio_components["target_reader"],
        mock_asyncio_components["target_writer"],
    )

    # Create proxy
    stats = create_test_stats()
    proxy = TcpProxy(
        local_port=8080, target_host="127.0.0.1", target_port=9090, stats=stats
    )

    # We need to patch the _proxy_data method return value and asyncio.create_task
    # This approach directly mocks gather to avoid issues with coroutines/awaitables

    # Patch the gather used inside the handle_client method
    async def mock_proxy_data(*args: Any, **kwargs: Any) -> None:
        # Record calls but don't do anything
        return None

    # Apply patches within the test function
    with (
        patch.object(proxy, "_proxy_data", side_effect=mock_proxy_data),
        patch("asyncio.create_task", side_effect=lambda x: x),
    ):
        # Call handle_client
        asyncio.run(
            proxy._handle_client(
                mock_asyncio_components["client_reader"],
                mock_asyncio_components["client_writer"],
            )
        )

    # Verify connections were made to target
    mock_open_connection.assert_called_once_with("127.0.0.1", 9090)

    # Verify connections were closed
    mock_asyncio_components["target_writer"].close.assert_called_once()
    mock_asyncio_components["client_writer"].close.assert_called_once()


def test_proxy_data() -> None:
    """Test _proxy_data method."""

    async def test_proxy_data_async() -> None:
        # Create mocks
        reader = AsyncMock()
        writer = AsyncMock()

        # Mock reading data chunks then empty (connection closed)
        reader.read.side_effect = [b"first chunk", b"second chunk", b""]

        # Create stats and proxy
        stats = create_test_stats()
        stats_callback = Mock()
        proxy = TcpProxy(
            local_port=8080,
            target_host="127.0.0.1",
            target_port=9090,
            stats=stats,
            stats_callback=stats_callback,
        )

        # Test client to target direction
        await proxy._proxy_data(reader, writer, "client_to_target")

        # Verify bytes were counted and written
        assert proxy._proxy_stats.bytes_sent == len(b"first chunk") + len(
            b"second chunk"
        )
        assert stats.bytes_sent == proxy._proxy_stats.bytes_sent
        assert reader.read.call_count == 3
        assert writer.write.call_count == 2
        assert writer.drain.call_count == 2
        assert stats_callback.call_count == 2

        # Reset mocks and test target to client direction
        reader.reset_mock()
        writer.reset_mock()
        reader.read.side_effect = [b"response chunk", b""]

        await proxy._proxy_data(reader, writer, "target_to_client")

        # Verify bytes were counted and written
        assert proxy._proxy_stats.bytes_received == len(b"response chunk")
        assert stats.bytes_received == proxy._proxy_stats.bytes_received
        assert reader.read.call_count == 2
        assert writer.write.call_count == 1
        assert writer.drain.call_count == 1
        assert stats_callback.call_count == 3  # One more call

    asyncio.run(test_proxy_data_async())


def test_proxy_data_with_error() -> None:
    """Test _proxy_data method error handling."""

    async def test_proxy_data_error_async() -> None:
        # Create mocks
        reader = AsyncMock()
        writer = AsyncMock()

        # Mock reading to raise exception
        reader.read.side_effect = Exception("Read error")

        # Create stats and proxy
        stats = create_test_stats()
        proxy = TcpProxy(
            local_port=8080, target_host="127.0.0.1", target_port=9090, stats=stats
        )

        # Test with exception
        with patch("vibectl.proxy.logger.error") as mock_log_error:
            await proxy._proxy_data(reader, writer, "client_to_target")
            mock_log_error.assert_called_once()

        # Test with cancellation
        reader.read.side_effect = asyncio.CancelledError()
        with patch("vibectl.proxy.logger.error") as mock_log_error:
            await proxy._proxy_data(reader, writer, "client_to_target")
            mock_log_error.assert_not_called()  # Should not log for cancellation

    asyncio.run(test_proxy_data_error_async())


@patch("vibectl.proxy.TcpProxy")
def test_start_proxy_server(mock_proxy_class: Mock) -> None:
    """Test start_proxy_server function."""

    async def test_start_proxy_server_async() -> None:
        # Create a proper async mock for the start method
        mock_proxy = Mock()
        mock_proxy.start = AsyncMock()
        mock_proxy_class.return_value = mock_proxy

        # Create stats and callback
        stats = create_test_stats()
        stats_callback = Mock()

        # Call function
        result = await start_proxy_server(8080, 9090, stats, stats_callback)

        # Verify proxy was created and started
        mock_proxy_class.assert_called_once_with(
            local_port=8080,
            target_host="127.0.0.1",
            target_port=9090,
            stats=stats,
            stats_callback=stats_callback,
        )
        mock_proxy.start.assert_awaited_once()
        assert result == mock_proxy

    asyncio.run(test_start_proxy_server_async())


def test_stop_proxy_server() -> None:
    """Test stop_proxy_server function."""

    async def test_stop_proxy_server_async() -> None:
        # Create a proper async mock for the stop method
        mock_proxy = Mock()
        mock_proxy.stop = AsyncMock()

        # Call function with proxy
        await stop_proxy_server(mock_proxy)

        # Verify proxy was stopped
        mock_proxy.stop.assert_awaited_once()

        # Call function with None
        await stop_proxy_server(None)

        # Verify proxy.stop wasn't called again
        assert mock_proxy.stop.await_count == 1

    asyncio.run(test_stop_proxy_server_async())
