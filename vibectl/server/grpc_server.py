"""
gRPC server for the vibectl LLM proxy service.

This module provides the server setup and configuration for hosting
the LLM proxy service over gRPC with optional JWT authentication.
"""

import logging
import signal
from collections.abc import Callable
from concurrent import futures
from types import FrameType
from typing import Any, cast

import grpc

from vibectl.proto.llm_proxy_pb2_grpc import (
    add_VibectlLLMProxyServicer_to_server,
)
from vibectl.types import CertificateError

from .cert_utils import (
    ensure_certificate_exists,
    get_default_cert_paths,
    load_certificate_credentials,
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
        use_tls: bool = False,
        cert_file: str | None = None,
        key_file: str | None = None,
        hsts_settings: dict | None = None,
    ):
        """Initialize the gRPC server.

        Args:
            host: Host to bind the server to
            port: Port to bind the server to
            default_model: Default LLM model to use
            max_workers: Maximum number of worker threads
            require_auth: Whether to require JWT authentication
            jwt_manager: JWT manager instance (creates default if None and
                         auth enabled)
            use_tls: Whether to use TLS encryption
            cert_file: Path to TLS certificate file (auto-generated if None
                       and TLS enabled)
            key_file: Path to TLS private key file (auto-generated if None
                      and TLS enabled)
            hsts_settings: HSTS settings for the server
        """
        self.host = host
        self.port = port
        self.default_model = default_model
        self.max_workers = max_workers
        self.require_auth = require_auth
        self.use_tls = use_tls
        self.cert_file = cert_file
        self.key_file = key_file
        self.hsts_settings = hsts_settings or {}
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

        tls_status = "with TLS" if self.use_tls else "without TLS"
        logger.info(f"Initialized gRPC server for {host}:{port} ({tls_status})")

    def start(self) -> None:
        """Start the gRPC server."""
        # Create interceptors list
        interceptors: list[grpc.ServerInterceptor] = []
        if self.jwt_interceptor:
            interceptors.append(self.jwt_interceptor)

        # Add HSTS interceptor if enabled and TLS is in use
        if self.use_tls and self.hsts_settings.get("enabled", False):
            header_value = _build_hsts_header(self.hsts_settings)

            class _HSTSInterceptor(grpc.ServerInterceptor):
                """Inject Strict-Transport-Security header into gRPC metadata."""

                def __init__(self, hsts_header: str) -> None:
                    self._hsts_header = hsts_header

                def intercept_service(
                    self,
                    continuation: Callable[
                        [grpc.HandlerCallDetails], grpc.RpcMethodHandler | None
                    ],
                    handler_call_details: grpc.HandlerCallDetails,
                ) -> grpc.RpcMethodHandler | None:
                    handler = continuation(handler_call_details)

                    if handler is None:
                        return None

                    # At this point handler is a valid RpcMethodHandler
                    handler = cast(grpc.RpcMethodHandler, handler)

                    # Wrap unary_unary; for other handler types we simply
                    # return original
                    if handler.unary_unary:
                        unary_fn = cast(
                            Callable[[Any, grpc.ServicerContext], Any],
                            handler.unary_unary,
                        )

                        def new_unary_unary(
                            request: Any, context: grpc.ServicerContext
                        ) -> Any:
                            # Delegate to the original RPC implementation first
                            result = unary_fn(request, context)

                            # Inject HSTS as trailing metadata so it appears in
                            # grpcurl's "Response trailers" section without
                            # risking duplicate initial-metadata sends.
                            context.set_trailing_metadata(
                                (("strict-transport-security", self._hsts_header),)
                            )

                            return result

                        return grpc.unary_unary_rpc_method_handler(
                            new_unary_unary,
                            request_deserializer=handler.request_deserializer,
                            response_serializer=handler.response_serializer,
                        )

                    return handler

            interceptors.append(_HSTSInterceptor(header_value))

        # Create server with interceptors
        self.server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=self.max_workers),
            interceptors=interceptors,
        )

        # Add the servicer to the server
        add_VibectlLLMProxyServicer_to_server(self._servicer, self.server)

        # Bind to the port with or without TLS
        listen_addr = f"{self.host}:{self.port}"

        if self.use_tls:
            # Handle TLS configuration
            try:
                # Ensure certificate files exist (auto-generate if needed)
                if self.cert_file is None or self.key_file is None:
                    from vibectl.config_utils import get_config_dir

                    config_dir = get_config_dir("server")
                    default_cert_file, default_key_file = get_default_cert_paths(
                        config_dir
                    )
                    self.cert_file = self.cert_file or default_cert_file
                    self.key_file = self.key_file or default_key_file

                    logger.info(
                        "Using default certificate paths: cert=%s, key=%s",
                        self.cert_file,
                        self.key_file,
                    )

                # Ensure certificates exist (generate if missing)
                ensure_certificate_exists(
                    self.cert_file,
                    self.key_file,
                    hostname=self.host
                    if self.host not in ("0.0.0.0", "::")
                    else "localhost",
                )

                # Load certificate and private key
                cert_data, key_data = load_certificate_credentials(
                    self.cert_file, self.key_file
                )

                # Create SSL server credentials
                server_credentials = grpc.ssl_server_credentials(
                    [(key_data, cert_data)],
                    root_certificates=None,
                    require_client_auth=False,
                )

                # Add secure port
                self.server.add_secure_port(listen_addr, server_credentials)
                logger.info(
                    "TLS certificates loaded: cert=%s, key=%s",
                    self.cert_file,
                    self.key_file,
                )

            except CertificateError as e:
                logger.error("Failed to configure TLS: %s", e)
                raise RuntimeError(f"TLS configuration failed: {e}") from e
            except Exception as e:
                logger.error("Unexpected error configuring TLS: %s", e)
                raise RuntimeError(f"TLS configuration failed: {e}") from e
        else:
            # Use insecure port
            self.server.add_insecure_port(listen_addr)

        # Start the server
        self.server.start()

        # Log server status
        auth_status = "with JWT auth" if self.require_auth else "without auth"
        tls_status = "with TLS" if self.use_tls else "without TLS"
        logger.info(
            f"gRPC server started on {listen_addr} ({tls_status}, {auth_status})"
        )

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
        def signal_handler(signum: int, frame: FrameType | None) -> None:
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
    use_tls: bool = False,
    cert_file: str | None = None,
    key_file: str | None = None,
    hsts_settings: dict | None = None,
) -> GRPCServer:
    """Create a new gRPC server instance.

    Args:
        host: Host to bind the server to
        port: Port to bind the server to
        default_model: Default LLM model to use
        max_workers: Maximum number of worker threads
        require_auth: Whether to require JWT authentication
        jwt_manager: JWT manager instance (creates default if None and auth enabled)
        use_tls: Whether to use TLS encryption
        cert_file: Path to TLS certificate file (auto-generated if None and TLS enabled)
        key_file: Path to TLS private key file (auto-generated if None and TLS enabled)
        hsts_settings: HSTS settings for the server

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
        use_tls=use_tls,
        cert_file=cert_file,
        key_file=key_file,
        hsts_settings=hsts_settings,
    )


if __name__ == "__main__":
    # For testing - run the server directly
    logging.basicConfig(level=logging.INFO)
    create_server().serve_forever()


def _build_hsts_header(settings: dict) -> str:
    """Build Strict-Transport-Security header value from settings dict."""

    max_age = settings.get("max_age", 31536000)
    include_sub = settings.get("include_subdomains", False)
    preload = settings.get("preload", False)

    parts: list[str] = [f"max-age={int(max_age)}"]
    if include_sub:
        parts.append("includeSubDomains")
    if preload:
        parts.append("preload")
    return "; ".join(parts)
