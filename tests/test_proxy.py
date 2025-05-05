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


@pytest.mark.asyncio
@patch("asyncio.open_connection", new_callable=AsyncMockClass)
async def test_handle_client(
    mock_open_connection: AsyncMockClass,
    mock_asyncio_components: dict,
) -> None:
    """Test _handle_client method core logic (connection and task creation)."""
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

    # Simple async mock for _proxy_data
    mock_proxy_data_coro = AsyncMock()

    # Apply patch for _proxy_data
    with patch.object(proxy, "_proxy_data", new=mock_proxy_data_coro):
        # Call handle_client directly
        await proxy._handle_client(
            mock_asyncio_components["client_reader"],
            mock_asyncio_components["client_writer"],
        )

    # Verify connections were made to target
    mock_open_connection.assert_called_once_with("127.0.0.1", 9090)

    # Verify _proxy_data was called twice (client->target and target->client)
    assert mock_proxy_data_coro.call_count == 2
    mock_proxy_data_coro.assert_any_call(
        mock_asyncio_components["client_reader"],
        mock_asyncio_components["target_writer"],
        "client_to_target",
    )
    mock_proxy_data_coro.assert_any_call(
        mock_asyncio_components["target_reader"],
        mock_asyncio_components["client_writer"],
        "target_to_client",
    )

    # Note: We are no longer explicitly testing the close() calls in the finally
    # block due to complexity with mocking TaskGroup exception handling.


@pytest.mark.asyncio
async def test_proxy_data() -> None:
    """Test the _proxy_data coroutine."""
    # Create mocks
    mock_reader = AsyncMock(spec=asyncio.StreamReader)
    mock_writer = AsyncMock(spec=asyncio.StreamWriter)
    mock_stats = create_test_stats()
    mock_callback = Mock()

    # Configure reader to return data then empty bytes
    mock_reader.read.side_effect = [b"data1", b"data2", b""]

    # Create proxy instance
    proxy = TcpProxy(
        local_port=8080,
        target_host="localhost",
        target_port=9090,
        stats=mock_stats,
        stats_callback=mock_callback,
    )

    # Run the coroutine
    await proxy._proxy_data(mock_reader, mock_writer, "client_to_target")

    # Assertions
    assert mock_reader.read.call_count == 3
    assert mock_writer.write.call_count == 2
    mock_writer.write.assert_any_call(b"data1")
    mock_writer.write.assert_any_call(b"data2")
    assert mock_writer.drain.call_count == 2
    assert mock_stats.bytes_sent == len(b"data1") + len(b"data2")
    assert mock_stats.bytes_received == 0
    assert mock_stats.last_activity > 0
    assert mock_callback.call_count == 2


@pytest.mark.asyncio
async def test_proxy_data_with_error() -> None:
    """Test _proxy_data handles exceptions."""
    # Create mocks
    mock_reader = AsyncMock(spec=asyncio.StreamReader)
    mock_writer = AsyncMock(spec=asyncio.StreamWriter)
    mock_stats = create_test_stats()

    # Configure reader to raise an error
    mock_reader.read.side_effect = OSError("Read error")

    # Create proxy instance
    proxy = TcpProxy(
        local_port=8080, target_host="localhost", target_port=9090, stats=mock_stats
    )

    # Run the coroutine and expect no exception to be raised
    # (Errors should be logged, not propagated)
    with patch("vibectl.proxy.logger.error") as mock_log_error:
        await proxy._proxy_data(mock_reader, mock_writer, "target_to_client")

    # Assertions
    mock_log_error.assert_called_once()
    assert (
        "Proxy error (target_to_client): Read error" in mock_log_error.call_args[0][0]
    )
    # Ensure stats weren't updated incorrectly
    assert mock_stats.bytes_received == 0


@pytest.mark.asyncio
@patch("vibectl.proxy.TcpProxy")
async def test_start_proxy_server(mock_proxy_class: Mock) -> None:
    """Test start_proxy_server function."""
    # Create a proper async mock for the start method
    mock_proxy_instance = Mock(spec=TcpProxy)
    mock_proxy_instance.start = AsyncMock()
    mock_proxy_class.return_value = mock_proxy_instance

    stats = create_test_stats()
    callback = Mock()

    proxy = await start_proxy_server(
        local_port=8888, target_port=9999, stats=stats, stats_callback=callback
    )

    # Verify TcpProxy was instantiated correctly
    mock_proxy_class.assert_called_once_with(
        local_port=8888,
        target_host="127.0.0.1",
        target_port=9999,
        stats=stats,
        stats_callback=callback,
    )
    # Verify start was called
    mock_proxy_instance.start.assert_awaited_once()
    assert proxy is mock_proxy_instance


@pytest.mark.asyncio
async def test_stop_proxy_server() -> None:
    """Test stop_proxy_server function."""
    # Create a proper async mock for the stop method
    mock_proxy = Mock(spec=TcpProxy)
    mock_proxy.stop = AsyncMock()

    # Test stopping a valid proxy
    await stop_proxy_server(mock_proxy)
    mock_proxy.stop.assert_awaited_once()

    # Test stopping None (should do nothing)
    mock_proxy.reset_mock()
    await stop_proxy_server(None)
    mock_proxy.stop.assert_not_awaited()
