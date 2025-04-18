"""
Proxy module for vibectl port-forward traffic monitoring.

Implements a TCP proxy server to monitor traffic between a local port and
an intermediate port, collecting statistics about data transfer.
"""

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from .logutil import logger  # Use shared logger


class StatsProtocol(Protocol):
    """Protocol defining the expected structure of stats objects."""

    bytes_received: int
    bytes_sent: int
    last_activity: float


@dataclass
class ProxyStats:
    """Statistics for tracking proxy data transfer."""

    bytes_received: int = 0  # From target to client
    bytes_sent: int = 0  # From client to target
    active_connections: int = 0
    connection_count: int = 0
    last_activity_timestamp: float = 0

    @property
    def last_activity(self) -> float:
        """Get the last activity timestamp."""
        return self.last_activity_timestamp

    @last_activity.setter
    def last_activity(self, value: float) -> None:
        """Set the last activity timestamp."""
        self.last_activity_timestamp = value


class TcpProxy:
    """TCP proxy for monitoring port-forward traffic."""

    def __init__(
        self,
        local_port: int,
        target_host: str,
        target_port: int,
        stats: StatsProtocol,
        stats_callback: Callable[[], None] | None = None,
    ) -> None:
        """Initialize the TCP proxy.

        Args:
            local_port: The local port to listen on
            target_host: The target host to forward to (usually localhost)
            target_port: The target port to forward to
            stats: Statistics object that tracks bytes_received and bytes_sent
            stats_callback: Optional callback function to call when stats are updated
        """
        self.local_port = local_port
        self.target_host = target_host
        self.target_port = target_port
        self.stats: StatsProtocol = stats
        self.stats_callback = stats_callback
        self.server: asyncio.Server | None = None
        self.connections: set[asyncio.Task[None]] = set()
        self._proxy_stats = ProxyStats()

    async def start(self) -> None:
        """Start the proxy server."""
        try:
            self.server = await asyncio.start_server(
                self._handle_client, "127.0.0.1", self.local_port
            )
            logger.info(
                f"Proxy server started on 127.0.0.1:{self.local_port} -> "
                f"{self.target_host}:{self.target_port}"
            )
        except Exception as e:
            logger.error(f"Failed to start proxy server: {e}")
            raise

    async def stop(self) -> None:
        """Stop the proxy server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("Proxy server stopped")

        # Close all active connections
        for conn in self.connections:
            conn.cancel()

        self.connections = set()

    async def _handle_client(
        self, client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter
    ) -> None:
        """Handle a client connection.

        Args:
            client_reader: StreamReader for client connection
            client_writer: StreamWriter for client connection
        """
        # Connect to the target
        try:
            target_reader, target_writer = await asyncio.open_connection(
                self.target_host, self.target_port
            )
        except Exception as e:
            logger.error(
                f"Failed to connect to target {self.target_host}:"
                f"{self.target_port}: {e}"
            )
            client_writer.close()
            return

        # Create bidirectional proxy tasks
        client_to_target_task = asyncio.create_task(
            self._proxy_data(client_reader, target_writer, "client_to_target")
        )
        target_to_client_task = asyncio.create_task(
            self._proxy_data(target_reader, client_writer, "target_to_client")
        )

        # Update connection statistics
        self._proxy_stats.connection_count += 1
        self._proxy_stats.active_connections += 1

        # Copy stats to the parent object for display
        self.stats.bytes_received = self._proxy_stats.bytes_received
        self.stats.bytes_sent = self._proxy_stats.bytes_sent

        # Update last activity timestamp
        current_time = time.time()
        self._proxy_stats.last_activity = current_time
        self.stats.last_activity = current_time

        # Add tasks to connections set
        self.connections.add(client_to_target_task)
        self.connections.add(target_to_client_task)

        # Wait for either task to complete
        await asyncio.gather(
            client_to_target_task, target_to_client_task, return_exceptions=True
        )

        # Clean up connections
        self.connections.discard(client_to_target_task)
        self.connections.discard(target_to_client_task)

        # Close the writer streams
        target_writer.close()
        client_writer.close()

        # Update connection count
        self._proxy_stats.active_connections -= 1

    async def _proxy_data(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, direction: str
    ) -> None:
        """Proxy data between reader and writer.

        Args:
            reader: Source stream reader
            writer: Destination stream writer
            direction: Direction of data flow ("client_to_target" or "target_to_client")
        """
        try:
            while True:
                # Read data from source
                data = await reader.read(8192)  # 8KB buffer
                if not data:
                    break  # Connection closed

                # Update statistics
                if direction == "client_to_target":
                    self._proxy_stats.bytes_sent += len(data)
                    self.stats.bytes_sent = self._proxy_stats.bytes_sent
                else:
                    self._proxy_stats.bytes_received += len(data)
                    self.stats.bytes_received = self._proxy_stats.bytes_received

                # Update last activity timestamp
                current_time = time.time()
                self._proxy_stats.last_activity = current_time
                self.stats.last_activity = current_time

                # Call the stats callback if provided
                if self.stats_callback:
                    self.stats_callback()

                # Write data to destination
                writer.write(data)
                await writer.drain()

        except asyncio.CancelledError:
            # Handle task cancellation gracefully
            pass
        except Exception as e:
            logger.error(f"Proxy error ({direction}): {e}")


async def start_proxy_server(
    local_port: int,
    target_port: int,
    stats: StatsProtocol,
    stats_callback: Callable[[], None] | None = None,
) -> TcpProxy:
    """Start a proxy server for port forwarding.

    Args:
        local_port: The local port to listen on
        target_port: The target port to forward to
        stats: Statistics object to update
        stats_callback: Optional callback function to call when stats are updated

    Returns:
        A TcpProxy instance
    """
    proxy = TcpProxy(
        local_port=local_port,
        target_host="127.0.0.1",
        target_port=target_port,
        stats=stats,
        stats_callback=stats_callback,
    )
    await proxy.start()
    return proxy


async def stop_proxy_server(proxy: TcpProxy | None = None) -> None:
    """Stop the proxy server.

    Args:
        proxy: The TcpProxy instance to stop. If None, no action is taken.
    """
    if proxy:
        await proxy.stop()
