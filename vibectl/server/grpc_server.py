"""
gRPC server for the vibectl LLM proxy service.

This module provides the server setup and configuration for hosting
the LLM proxy service over gRPC with optional JWT authentication.
"""

import logging
import signal
from concurrent import futures

import grpc

from vibectl.proto.llm_proxy_pb2_grpc import (
    add_VibectlLLMProxyServicer_to_server,
)

from .jwt_auth import JWTAuthManager, load_config_from_server
from .jwt_interceptor import JWTAuthInterceptor, create_jwt_interceptor
from .llm_proxy import LLMProxyServicer

logger = logging.getLogger(__name__)


class GRPCServer:
    """gRPC server for the vibectl LLM proxy service."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 50051,
        default_model: str | None = None,
        max_workers: int = 10,
        require_auth: bool = False,
        jwt_manager: JWTAuthManager | None = None,
    ):
        """Initialize the gRPC server.

        Args:
            host: Host to bind the server to
            port: Port to bind the server to
            default_model: Default LLM model to use
            max_workers: Maximum number of worker threads
            require_auth: Whether to require JWT authentication
            jwt_manager: JWT manager instance (creates default if None and auth enabled)
        """
        self.host = host
        self.port = port
        self.default_model = default_model
        self.max_workers = max_workers
        self.require_auth = require_auth
        self.server: grpc.Server | None = None
        self._servicer = LLMProxyServicer(default_model=default_model)

        # Set up JWT authentication if enabled
        self.jwt_manager: JWTAuthManager | None
        self.jwt_interceptor: JWTAuthInterceptor | None

        if require_auth:
            if jwt_manager is None:
                config = load_config_from_server()
                jwt_manager = JWTAuthManager(config)
            self.jwt_manager = jwt_manager
            self.jwt_interceptor = create_jwt_interceptor(jwt_manager, enabled=True)
            logger.info("JWT authentication enabled for gRPC server")
        else:
            self.jwt_manager = None
            self.jwt_interceptor = None
            logger.info("JWT authentication disabled for gRPC server")

        logger.info(f"Initialized gRPC server for {host}:{port}")

    def start(self) -> None:
        """Start the gRPC server."""
        # Create interceptors list
        interceptors: list[grpc.ServerInterceptor] = []
        if self.jwt_interceptor:
            interceptors.append(self.jwt_interceptor)

        # Create server with interceptors
        self.server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=self.max_workers),
            interceptors=interceptors,
        )

        # Add the servicer to the server
        add_VibectlLLMProxyServicer_to_server(self._servicer, self.server)

        # Bind to the port
        listen_addr = f"{self.host}:{self.port}"
        self.server.add_insecure_port(listen_addr)

        # Start the server
        self.server.start()
        auth_status = "with JWT auth" if self.require_auth else "without auth"
        logger.info(f"gRPC server started on {listen_addr} ({auth_status})")

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

    def generate_token(self, subject: str, expiration_days: int | None = None) -> str:
        """Generate a JWT token for authentication.

        Args:
            subject: The subject identifier for the token
            expiration_days: Days until token expires (uses default if None)

        Returns:
            Generated JWT token string

        Raises:
            RuntimeError: If authentication is not enabled
            ValueError: If token generation fails
        """
        if not self.require_auth or not self.jwt_manager:
            raise RuntimeError(
                "Cannot generate token: JWT authentication is not enabled"
            )

        return self.jwt_manager.generate_token(subject, expiration_days)


def create_server(
    host: str = "localhost",
    port: int = 50051,
    default_model: str | None = None,
    max_workers: int = 10,
    require_auth: bool = False,
    jwt_manager: JWTAuthManager | None = None,
) -> GRPCServer:
    """Create a new gRPC server instance.

    Args:
        host: Host to bind the server to
        port: Port to bind the server to
        default_model: Default LLM model to use
        max_workers: Maximum number of worker threads
        require_auth: Whether to require JWT authentication
        jwt_manager: JWT manager instance (creates default if None and auth enabled)

    Returns:
        Configured GRPCServer instance
    """
    return GRPCServer(
        host=host,
        port=port,
        default_model=default_model,
        max_workers=max_workers,
        require_auth=require_auth,
        jwt_manager=jwt_manager,
    )


if __name__ == "__main__":
    # For testing - run the server directly
    logging.basicConfig(level=logging.INFO)
    create_server().serve_forever()
