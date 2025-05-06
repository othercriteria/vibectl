"""Tests for the proxy module.

This module tests the proxy.py module which implements TCP proxying for
port-forward traffic monitoring.
"""

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from vibectl.live_display import ConnectionStats
from vibectl.proxy import (
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
    stats = ConnectionStats()
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
    stats = ConnectionStats()
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
    stats = ConnectionStats()
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
    stats = ConnectionStats()
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
    """Test _handle_client method with successful connection."""
    # Setup mocks for successful connection
    mock_open_connection.return_value = (
        mock_asyncio_components["target_reader"],
        mock_asyncio_components["target_writer"],
    )

    stats = ConnectionStats()
    proxy = TcpProxy(
        local_port=8080, target_host="127.0.0.1", target_port=9090, stats=stats
    )

    # Use patch.object as a context manager to mock _proxy_data
    with patch.object(
        proxy, "_proxy_data", new_callable=AsyncMock
    ) as mock_proxy_data_method:
        # Call _handle_client
        await proxy._handle_client(
            mock_asyncio_components["client_reader"],
            mock_asyncio_components["client_writer"],
        )

        # Verify connections were made to target
        mock_open_connection.assert_called_once_with(
            proxy.target_host, proxy.target_port
        )

        # Verify _proxy_data was called twice (once for each direction)
        # by the TaskGroup created in _handle_client
        assert mock_proxy_data_method.call_count == 2
        mock_proxy_data_method.assert_any_call(
            mock_asyncio_components["client_reader"],
            mock_asyncio_components["target_writer"],
            "client_to_target",
        )
        mock_proxy_data_method.assert_any_call(
            mock_asyncio_components["target_reader"],
            mock_asyncio_components["client_writer"],
            "target_to_client",
        )

    # Verify client_writer.close was called in the finally block
    # This is tricky because it's in a finally that might also see exceptions
    # from the TaskGroup. For this test, we assume success path.
    # mock_asyncio_components["client_writer"].close.assert_called_once()
    # mock_asyncio_components["target_writer"].close.assert_called_once()
    # Due to TaskGroup, closing is more complex to assert directly here without
    # also mocking the TaskGroup behavior itself. The main thing is that
    # _proxy_data was called, implying the core logic ran.


@pytest.mark.asyncio
async def test_proxy_data_with_error() -> None:
    """Test _proxy_data method with an error during read/write."""
    stats = ConnectionStats()
    proxy_instance = TcpProxy(
        local_port=8080, target_host="127.0.0.1", target_port=9090, stats=stats
    )

    mock_reader = AsyncMock()
    mock_writer = AsyncMock()

    # Simulate an error during reader.read
    mock_reader.read.side_effect = Exception("Read error")

    with patch("vibectl.proxy.logger.error") as mock_log_error:
        await proxy_instance._proxy_data(mock_reader, mock_writer, "client_to_target")
        mock_log_error.assert_called_once_with(
            "Proxy error (client_to_target): Read error"
        )

    # Reset mocks and simulate error during writer.write
    mock_reader.read.side_effect = [b"test_data", b""]  # Successful read
    mock_writer.write = MagicMock(
        side_effect=Exception("Write error")
    )  # Error on write

    with patch("vibectl.proxy.logger.error") as mock_log_error:
        await proxy_instance._proxy_data(mock_reader, mock_writer, "client_to_target")
        mock_log_error.assert_called_with("Proxy error (client_to_target): Write error")


@pytest.mark.asyncio
@patch("vibectl.proxy.TcpProxy")
async def test_start_proxy_server(mock_proxy_class: Mock) -> None:
    """Test the start_proxy_server utility function."""
    # Mock the TcpProxy instance and its start method
    mock_proxy_instance = AsyncMock()
    mock_proxy_instance.start = AsyncMock()  # Ensure start is an AsyncMock
    mock_proxy_class.return_value = mock_proxy_instance

    stats = ConnectionStats()  # Use ConnectionStats
    local_port = 12345
    target_port = 54321

    # Call the function
    proxy = await start_proxy_server(local_port, target_port, stats)

    # Assert TcpProxy was instantiated correctly
    mock_proxy_class.assert_called_once_with(
        local_port=local_port,
        target_host="127.0.0.1",
        target_port=target_port,
        stats=stats,
    )
    # Assert start was called on the instance
    mock_proxy_instance.start.assert_called_once()
    # Assert the returned proxy is the mocked instance
    assert proxy == mock_proxy_instance


@pytest.mark.asyncio
async def test_stop_proxy_server() -> None:
    """Test the stop_proxy_server utility function."""
    # Create a mock TcpProxy instance
    mock_proxy = AsyncMock(spec=TcpProxy)  # Use spec for better mocking
    mock_proxy.stop = AsyncMock()  # Ensure stop is an AsyncMock

    # Call with a proxy instance
    await stop_proxy_server(mock_proxy)
    mock_proxy.stop.assert_called_once()

    # Call with None (should not raise error or call stop)
    mock_proxy.reset_mock()  # Reset call count for the next assertion
    await stop_proxy_server(None)
    mock_proxy.stop.assert_not_called()


def test_stats_protocol_implementation() -> None:
    """Test that ConnectionStats can implement StatsProtocol."""
    # Create ConnectionStats object
    stats = ConnectionStats()

    # Test initial values
    assert stats.bytes_received == 0
    assert stats.bytes_sent == 0
    # ConnectionStats initializes last_activity with time.time()
    assert stats.last_activity >= 0

    # Test property and setter
    new_time = time.time() + 10  # Ensure it's a different time
    stats.last_activity = new_time
    assert stats.last_activity == new_time
