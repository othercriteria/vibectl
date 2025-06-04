"""
gRPC server for the vibectl LLM proxy service.

This module provides the server setup and configuration for hosting
the LLM proxy service over gRPC.
"""

import logging
import signal
from concurrent import futures

import grpc  # type: ignore

from .llm_proxy import LLMProxyServicer
from .proto.llm_proxy_pb2_grpc import (
    add_VibectlLLMProxyServicer_to_server,  # type: ignore
)

logger = logging.getLogger(__name__)


class GRPCServer:
    """gRPC server for the vibectl LLM proxy service."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 50051,
        default_model: str | None = None,
        max_workers: int = 10,
    ):
        """Initialize the gRPC server.

        Args:
            host: Host to bind the server to
            port: Port to bind the server to
            default_model: Default LLM model to use
            max_workers: Maximum number of worker threads
        """
        self.host = host
        self.port = port
        self.default_model = default_model
        self.max_workers = max_workers
        self.server: grpc.Server | None = None
        self._servicer = LLMProxyServicer(default_model=default_model)

        logger.info(f"Initialized gRPC server for {host}:{port}")

    def start(self) -> None:
        """Start the gRPC server."""
        self.server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=self.max_workers)
        )

        # Add the servicer to the server
        add_VibectlLLMProxyServicer_to_server(self._servicer, self.server)

        # Bind to the port
        listen_addr = f"{self.host}:{self.port}"
        self.server.add_insecure_port(listen_addr)

        # Start the server
        self.server.start()
        logger.info(f"gRPC server started on {listen_addr}")

    def stop(self, grace_period: float = 5.0) -> None:
        """Stop the gRPC server.

        Args:
            grace_period: Time to wait for graceful shutdown
        """
        if self.server:
            logger.info("Stopping gRPC server...")
            self.server.stop(grace_period)
            self.server = None
            logger.info("gRPC server stopped")

    def wait_for_termination(self, timeout: float | None = None) -> None:
        """Wait for the server to terminate.

        Args:
            timeout: Maximum time to wait (None for indefinite)
        """
        if self.server:
            self.server.wait_for_termination(timeout)

    def serve_forever(self) -> None:
        """Start the server and wait for termination.

        This method will block until the server is terminated.
        """

        # Set up signal handlers for graceful shutdown
        def signal_handler(signum: int, frame) -> None:  # type: ignore
            logger.info(f"Received signal {signum}, shutting down...")
            self.stop()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        try:
            self.start()
            logger.info("Server started. Press Ctrl+C to stop.")
            self.wait_for_termination()
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            self.stop()


def create_server(
    host: str = "localhost",
    port: int = 50051,
    default_model: str | None = None,
    max_workers: int = 10,
) -> GRPCServer:
    """Create a new gRPC server instance.

    Args:
        host: Host to bind the server to
        port: Port to bind the server to
        default_model: Default LLM model to use
        max_workers: Maximum number of worker threads

    Returns:
        Configured GRPCServer instance
    """
    return GRPCServer(
        host=host,
        port=port,
        default_model=default_model,
        max_workers=max_workers,
    )


if __name__ == "__main__":
    # For testing - run the server directly
    logging.basicConfig(level=logging.INFO)
    create_server().serve_forever()
