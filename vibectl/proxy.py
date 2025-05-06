"""
Proxy module for vibectl port-forward traffic monitoring.

Implements a TCP proxy server to monitor traffic between a local port and
an intermediate port, collecting statistics about data transfer.
"""

import asyncio
import time
from typing import Protocol

from .logutil import logger  # Use shared logger


class StatsProtocol(Protocol):
    """Protocol defining the expected structure of stats objects."""

    bytes_received: int
    bytes_sent: int
    last_activity: float


class TcpProxy:
    """TCP proxy for monitoring port-forward traffic."""

    def __init__(
        self,
        local_port: int,
        target_host: str,
        target_port: int,
        stats: StatsProtocol,
    ) -> None:
        """Initialize the TCP proxy.

        Args:
            local_port: The local port to listen on
            target_host: The target host to forward to (usually localhost)
            target_port: The target port to forward to
            stats: Statistics object that tracks bytes_received and bytes_sent
        """
        self.local_port = local_port
        self.target_host = target_host
        self.target_port = target_port
        self.stats: StatsProtocol = stats
        self.server: asyncio.Server | None = None
        self.connections: set[asyncio.Task[None]] = set()

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

        # Update last activity timestamp
        current_time = time.time()
        self.stats.last_activity = current_time

        # Wait for either task to complete using TaskGroup
        try:
            async with asyncio.TaskGroup() as tg:
                # Pass the coroutines directly to create_task
                tg.create_task(
                    self._proxy_data(client_reader, target_writer, "client_to_target")
                )
                tg.create_task(
                    self._proxy_data(target_reader, client_writer, "target_to_client")
                )
        except* Exception as eg:
            logger.error(f"Error in connection handler task group: {eg.exceptions}")
            # Ensure connections are closed even if the task group fails
            if not client_writer.is_closing():
                client_writer.close()
                await client_writer.wait_closed()
            if not target_writer.is_closing():
                target_writer.close()
                await target_writer.wait_closed()
        finally:
            # Break long log message
            logger.debug(
                f"Closing connection for {self.target_host}:{self.target_port}"
            )
            # Ensure writers are closed in finally block for robustness
            if not client_writer.is_closing():
                client_writer.close()
                await client_writer.wait_closed()
            if not target_writer.is_closing():
                target_writer.close()
                await target_writer.wait_closed()

        # TaskGroup manages task lifecycle; manual cleanup of self.connections removed.

    async def _proxy_data(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, direction: str
    ) -> None:
        """Proxy data between reader and writer.

        Args:
            reader: Source stream reader
            writer: Destination stream writer
            direction: Direction of data flow ("client_to_target" or "target_to_client")
        """
        logger.debug(f"_proxy_data started for direction: {direction}")
        try:
            while True:
                # Read data from source
                data = await reader.read(8192)  # 8KB buffer
                logger.debug(f"_proxy_data ({direction}): read {len(data)} bytes")
                if not data:
                    logger.debug(
                        f"_proxy_data ({direction}): no data, "
                        "connection closed by peer."
                    )
                    break  # Connection closed

                # Update statistics
                if direction == "client_to_target":
                    self.stats.bytes_sent += len(data)
                    logger.debug(
                        f"_proxy_data ({direction}): updated self.stats.bytes_sent "
                        f"to {self.stats.bytes_sent}"
                    )
                else:
                    self.stats.bytes_received += len(data)
                    logger.debug(
                        f"_proxy_data ({direction}): updated self.stats.bytes_received "
                        f"to {self.stats.bytes_received}"
                    )

                # Update last activity timestamp
                current_time = time.time()
                self.stats.last_activity = current_time

                # Write data to destination
                logger.debug(
                    f"_proxy_data ({direction}): writing {len(data)} bytes "
                    "to destination."
                )
                writer.write(data)
                await writer.drain()

        except asyncio.CancelledError:
            # Handle task cancellation gracefully
            logger.debug(f"_proxy_data ({direction}): task cancelled.")
            pass
        except Exception as e:
            logger.error(f"Proxy error ({direction}): {e}")


async def start_proxy_server(
    local_port: int,
    target_port: int,
    stats: StatsProtocol,
) -> TcpProxy:
    """Start a proxy server for port forwarding.

    Args:
        local_port: The local port to listen on
        target_port: The target port to forward to
        stats: Statistics object to update

    Returns:
        A TcpProxy instance
    """
    proxy = TcpProxy(
        local_port=local_port,
        target_host="127.0.0.1",
        target_port=target_port,
        stats=stats,
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
