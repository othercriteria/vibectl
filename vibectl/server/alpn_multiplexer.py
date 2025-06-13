"""
ALPN Multiplexing Server for vibectl-server.

This module provides a TLS server that can multiplex between different protocols
based on ALPN (Application-Layer Protocol Negotiation) during the TLS handshake.

Supported protocols:
- "h2" (HTTP/2) → Routes to gRPC server
- "acme-tls/1" → Routes to TLS-ALPN-01 challenge handler

This allows a single server on port 443 to handle both the main gRPC service
and ACME TLS-ALPN-01 challenges.
"""

import asyncio
import contextlib
import logging
import ssl
from collections.abc import Callable
from typing import Any, Protocol, cast

from .alpn_bridge import TLSALPNBridge

logger = logging.getLogger(__name__)


class ALPNHandler(Protocol):
    """Protocol for ALPN-specific connection handlers."""

    async def handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle a connection for this ALPN protocol."""
        ...


class GRPCHandler:
    """Handler for gRPC connections (ALPN: h2)."""

    def __init__(self, grpc_server_port: int = 50051):
        """Initialize with internal gRPC server port."""
        self.grpc_server_port = grpc_server_port

    async def handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle gRPC connection by proxying to internal gRPC server."""
        try:
            # Connect to internal gRPC server
            upstream_reader, upstream_writer = await asyncio.open_connection(
                "127.0.0.1", self.grpc_server_port
            )

            # Start bidirectional proxy tasks
            upstream_task = asyncio.create_task(
                self._proxy_data(upstream_reader, writer, "upstream->client")
            )
            downstream_task = asyncio.create_task(
                self._proxy_data(reader, upstream_writer, "client->upstream")
            )

            # Wait for either direction to complete
            done, pending = await asyncio.wait(
                [upstream_task, downstream_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel remaining tasks
            for task in pending:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        except Exception as e:
            logger.error(f"Error in gRPC proxy: {e}")
        finally:
            # Cleanup connections
            for w in [
                writer,
                upstream_writer if "upstream_writer" in locals() else None,
            ]:
                if w and not w.is_closing():
                    w.close()
                    with contextlib.suppress(Exception):
                        await w.wait_closed()

    async def _proxy_data(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, direction: str
    ) -> None:
        """Proxy data between reader and writer."""
        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        except Exception as e:
            logger.debug(f"Proxy error in {direction}: {e}")
        finally:
            if not writer.is_closing():
                writer.close()


class TLSALPNHandler:
    """Handler for TLS-ALPN-01 challenge connections (ALPN: acme-tls/1).

    This handler manages its own SSL context with challenge certificates,
    separate from the main server's SSL context.
    """

    def __init__(self, tls_alpn_server: Any):
        """Initialize with TLS-ALPN challenge server instance."""
        self.tls_alpn_server = tls_alpn_server

    async def handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle TLS-ALPN-01 challenge connection.

        For TLS-ALPN-01 challenges, the connection is handled by checking
        the SNI and presenting the appropriate challenge certificate.
        The ALPN multiplexer routes here, and we handle the rest.
        """
        try:
            # Get SSL object to extract SNI information
            ssl_object = writer.get_extra_info("ssl_object")
            if ssl_object is None:
                logger.warning("❌ No SSL object in TLS-ALPN-01 connection")
                return

            # Extract SNI and connection info for detailed logging
            server_name = ssl_object.server_hostname if ssl_object else None
            peer_addr = writer.get_extra_info("peername", "unknown")

            logger.info(f"🎯 TLS-ALPN-01 challenge connection from {peer_addr}")
            logger.info(f"🎯 Challenge connection for domain: '{server_name}'")

            # Log certificate info that was presented
            try:
                cert = ssl_object.getpeercert(binary_form=False)
                if cert:
                    subject = dict(x[0] for x in cert["subject"])
                    logger.info(
                        "🎯 Certificate subject presented: "
                        f"{subject.get('commonName', 'unknown')}"
                    )
                else:
                    logger.debug("No peer certificate info available")
            except Exception as e:
                logger.debug(f"Could not get certificate info: {e}")

            logger.info(
                "✅ TLS-ALPN-01 challenge connection completed successfully for "
                f"domain: '{server_name}'"
            )

            # Note: At this point, the TLS handshake is complete and we're in the
            # application layer. For TLS-ALPN-01, the ACME server has already
            # validated the certificate during the handshake.

            # The TLS-ALPN-01 protocol is stateless - once the handshake completes
            # with the correct challenge certificate, the validation is done.
            # We can immediately close the connection per RFC 8737.

            # Per RFC 8737 Section 4: "Once the handshake is completed, the client
            # MUST NOT exchange any further data with the server and MUST immediately
            # close the connection."

        except Exception as e:
            logger.error(f"❌ Error handling TLS-ALPN-01 connection: {e}")
        finally:
            # Always close the connection immediately per RFC 8737
            if not writer.is_closing():
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()


class ALPNMultiplexer:
    """ALPN multiplexing server for handling multiple protocols on port 443.

    This multiplexer routes connections based on the negotiated ALPN protocol:
    - h2: Routes to gRPC handler (proxies to internal gRPC server)
    - acme-tls/1: Routes to TLS-ALPN challenge handler (uses challenge certificates)

    Each protocol can have its own SSL certificate management strategy.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 443,
        cert_file: str | None = None,
        key_file: str | None = None,
        bridge: TLSALPNBridge | None = None,
    ):
        """Initialize ALPN multiplexer.

        Args:
            host: Host address to bind to
            port: Port to bind to
            cert_file: Path to TLS certificate file
            key_file: Path to TLS private key file
            bridge: TLSALPNBridge instance for challenge server linkage
        """
        self.host = host
        self.port = port
        self.cert_file = cert_file
        self.key_file = key_file

        # Server state
        self._server: asyncio.Server | None = None
        self._ssl_context: ssl.SSLContext | None = None
        self._running = False
        self._start_event = asyncio.Event()

        # Protocol handlers
        self._handlers: dict[str, ALPNHandler] = {}

        # Bridge for challenge server linkage
        self._bridge: TLSALPNBridge | None = bridge
        if self._bridge:
            self._bridge.attach_multiplexer(self)

    def register_handler(self, alpn_protocol: str, handler: ALPNHandler) -> None:
        """Register a handler for a specific ALPN protocol.

        Args:
            alpn_protocol: ALPN protocol string (e.g., "h2", "acme-tls/1")
            handler: Handler instance for this protocol
        """
        self._handlers[alpn_protocol] = handler
        logger.info(f"Registered ALPN handler for protocol: {alpn_protocol}")

    def _create_ssl_context(self) -> ssl.SSLContext:
        """Create SSL context with ALPN support.

        For TLS-ALPN-01 challenges, certificate selection is handled by
        a custom SSL context callback that can access the negotiated ALPN protocol.
        """
        if not self.cert_file or not self.key_file:
            raise ValueError("cert_file and key_file must be provided for TLS")

        # Create SSL context with the default certificate
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)

        # NOTE: We intentionally allow TLS 1.2 here so that ACME
        # validation clients (which frequently fall back to TLS 1.2)
        # can complete the `tls-alpn-01` handshake.  Runtime routing
        # logic (see `_handle_connection`) still rejects gRPC traffic
        # that does not negotiate TLS 1.3, so normal proxy use remains
        # hardened while ACME remains interoperable.

        context.load_cert_chain(self.cert_file, self.key_file)

        # Set ALPN protocols based on registered handlers
        alpn_protocols = list(self._handlers.keys())
        if alpn_protocols:
            context.set_alpn_protocols(alpn_protocols)
            logger.info(f"ALPN protocols configured: {alpn_protocols}")

        # Add SNI callback for TLS-ALPN-01 challenge certificates
        # if handler is registered
        if "acme-tls/1" in self._handlers:
            context.sni_callback = self._create_sni_callback()
            logger.info(
                "SNI callback configured for TLS-ALPN-01 challenge certificates"
            )

        return context

    def _select_challenge_context(
        self, tls_alpn_server: Any, server_name: str | None
    ) -> ssl.SSLContext | None:
        """Select an appropriate SSL context for a TLS-ALPN-01 challenge.

        The logic is centralised here so that it can be unit-tested and reused
        from the SNI callback without cluttering that callback with
        conditional branches.

        Args:
            tls_alpn_server: The ACME TLS-ALPN challenge server instance.
            server_name: The SNI server name provided by the client (may be
                ``None`` when the client did not include SNI).

        Returns:
            An ``ssl.SSLContext`` with the correct challenge certificate loaded
            when a matching challenge exists, otherwise ``None``.
        """
        try:
            # When SNI is present, look for an exact challenge for that domain.
            if server_name:
                if tls_alpn_server._get_challenge_response(server_name):
                    return cast(
                        ssl.SSLContext, tls_alpn_server._create_ssl_context(server_name)
                    )
                return None

            # No SNI provided - fall back to heuristics based on active challenges.
            active_domains = tls_alpn_server._get_active_challenge_domains()
            if len(active_domains) == 1:
                # Single challenge active - use its certificate.
                domain = next(iter(active_domains))
                return cast(ssl.SSLContext, tls_alpn_server._create_ssl_context(domain))

            # Zero or multiple active challenges - no unambiguous choice.
            return None

        except Exception as exc:  # pragma: no cover - defensive guard
            logger.warning(f"⚠️ Failed to select challenge SSL context: {exc}")
            return None

    def _create_sni_callback(self) -> Callable:
        """Create SNI callback that can present challenge certificates for TLS-ALPN-01.

        Returns:
            SNI callback function for SSL context
        """

        def sni_callback(
            ssl_socket: Any, server_name: str | None, ssl_context: ssl.SSLContext
        ) -> None:
            """SNI callback for dynamic certificate selection during TLS handshake."""

            logger.info(f"🔍 SNI callback triggered - server_name='{server_name}'")

            try:
                tls_alpn_handler = self._handlers.get("acme-tls/1")
                if not isinstance(tls_alpn_handler, TLSALPNHandler):
                    logger.debug(
                        "🔧 TLS-ALPN handler not available; falling back to "
                        "default certificate"
                    )
                    return

                tls_alpn_server = tls_alpn_handler.tls_alpn_server

                # Delegate the actual selection logic to a helper for readability.
                challenge_context = self._select_challenge_context(
                    tls_alpn_server, server_name
                )

                if challenge_context is not None:
                    ssl_socket.context = challenge_context
                    chosen = server_name or getattr(
                        challenge_context, "server_name", "<auto>"
                    )
                    logger.info(
                        "✅ Using TLS-ALPN-01 challenge certificate for "
                        f"domain: '{chosen}'"
                    )
                else:
                    logger.info(
                        f"🔧 Using default certificate for server_name: '{server_name}'"
                    )

            except Exception as exc:  # pragma: no cover - defensive guard
                logger.error(f"❌ Exception in SNI callback: {exc}")
                # Allow TLS handshake to continue with default certificate.

        return sni_callback

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle incoming connection and route based on ALPN protocol."""
        logger.info("🔄 ALPN multiplexer received new connection")
        try:
            # Get connection info for debugging
            try:
                peer_addr = writer.get_extra_info("peername")
                sockname = writer.get_extra_info("sockname")
                logger.info(f"🔄 New connection from {peer_addr} to {sockname}")
            except Exception as e:
                logger.debug(f"Could not get connection info: {e}")
                logger.info("🔄 New connection (no peer info available)")

            # Get SSL object from the connection
            ssl_object = writer.get_extra_info("ssl_object")
            if ssl_object is None:
                logger.warning("❌ No SSL object in connection - rejecting")
                return

            # Log SNI and cipher info
            try:
                server_hostname = getattr(ssl_object, "server_hostname", None)
                cipher = ssl_object.cipher()
                logger.debug(
                    f"🔍 SSL info - SNI: '{server_hostname}', Cipher: {cipher}"
                )
            except Exception as e:
                logger.debug(f"Could not get SSL details: {e}")

            # Get the negotiated ALPN protocol
            alpn_protocol = ssl_object.selected_alpn_protocol()
            if alpn_protocol is None:
                logger.warning("❌ No ALPN protocol negotiated - rejecting connection")
                return

            logger.info(f"✅ ALPN protocol negotiated: '{alpn_protocol}'")

            # Runtime TLS-version enforcement:
            #  • ACME validation clients ("acme-tls/1") are permitted to use
            #    TLS ≥1.2 per RFC 8737.
            #  • All gRPC traffic ("h2") must still negotiate TLS 1.3 for
            #    hardened security.
            tls_version = None
            with contextlib.suppress(Exception):
                # Best-effort only - continue if version cannot be determined.
                tls_version = (
                    ssl_object.version()
                    if callable(getattr(ssl_object, "version", None))
                    else None
                )

            if (
                alpn_protocol == "h2"
                and tls_version is not None
                and tls_version != "TLSv1.3"
            ):
                logger.warning(
                    "❌ Connection rejected - gRPC (h2) requires TLS 1.3, got %s",
                    tls_version,
                )
                return

            # Route to appropriate handler
            handler = self._handlers.get(alpn_protocol)
            if handler is None:
                logger.warning(
                    f"❌ No handler registered for ALPN protocol: {alpn_protocol}"
                )
                return

            logger.debug(f"🔄 Routing to handler for protocol: {alpn_protocol}")
            # Delegate to the protocol-specific handler
            await handler.handle_connection(reader, writer)

        except Exception as e:
            logger.error(f"Error in ALPN multiplexer connection handling: {e}")
        finally:
            # Ensure cleanup happens regardless of how we exit
            if not writer.is_closing():
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()

    async def start(self) -> None:
        """Start the ALPN multiplexing server."""
        if self._running:
            logger.warning("ALPN multiplexer is already running")
            return

        if not self._handlers:
            raise ValueError("No ALPN handlers registered - cannot start server")

        try:
            logger.info(f"🚀 Starting ALPN multiplexer on {self.host}:{self.port}")
            logger.info(f"🎯 Supported ALPN protocols: {list(self._handlers.keys())}")

            # Create SSL context with SNI callback for dynamic certificate selection
            self._ssl_context = self._create_ssl_context()
            logger.info("✅ SSL context created successfully")

            # Start the server
            self._server = await asyncio.start_server(
                self._handle_connection,
                self.host,
                self.port,
                ssl=self._ssl_context,
                reuse_address=True,
                reuse_port=True,
            )

            # Get the actual port if we used 0 (dynamic port allocation)
            if self.port == 0:
                self.port = self._server.sockets[0].getsockname()[1]
                logger.info(f"📍 Server bound to dynamic port: {self.port}")

            self._running = True
            self._start_event.set()
            logger.info(
                f"🎉 ALPN multiplexer started successfully on {self.host}:{self.port}"
            )

        except Exception as e:
            logger.error(f"❌ Failed to start ALPN multiplexer: {e}")
            logger.error(f"❌ Exception details: {type(e).__name__}: {e}")
            await self._cleanup()
            raise

    async def stop(self) -> None:
        """Stop the ALPN multiplexing server."""
        if not self._running:
            return

        logger.info("Stopping ALPN multiplexer...")

        await self._cleanup()

        self._running = False
        self._start_event.clear()

        logger.info("ALPN multiplexer stopped")

    async def wait_until_ready(self, timeout: float = 10.0) -> bool:
        """Wait until the server is ready to accept connections.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if server is ready, False if timeout occurred
        """
        try:
            await asyncio.wait_for(self._start_event.wait(), timeout=timeout)
            return True
        except TimeoutError:
            logger.warning(
                f"⏰ Timeout waiting for ALPN multiplexer to be ready ({timeout}s)"
            )
            return False

    async def _cleanup(self) -> None:
        """Clean up server resources."""
        logger.info("🧹 Cleaning up ALPN multiplexer...")

        self._running = False
        self._start_event.clear()

        if self._server:
            try:
                self._server.close()
                await self._server.wait_closed()
                logger.info("✅ Server closed successfully")
            except Exception as e:
                logger.warning(f"⚠️ Error closing server: {e}")
            finally:
                self._server = None

        self._ssl_context = None
        logger.info("🧹 ALPN multiplexer cleanup complete")

    @property
    def is_running(self) -> bool:
        """Check if the server is currently running."""
        return self._running


async def create_alpn_multiplexer_for_acme(
    host: str,
    port: int,
    cert_file: str,
    key_file: str,
    grpc_server: Any,
    tls_alpn_server: Any,
    grpc_internal_port: int = 50051,
) -> ALPNMultiplexer:
    """Create and configure an ALPN multiplexer for ACME and gRPC.

    This function sets up a TLS server that can handle both gRPC connections
    (via ALPN "h2") and TLS-ALPN-01 ACME challenges (via ALPN "acme-tls/1") on
    the same port (typically 443).

    The gRPC server is started on a separate internal port and the multiplexer proxies
    gRPC connections to it, while handling ACME challenges directly.

    Args:
        host: Host to bind the multiplexer to
        port: Port to bind the multiplexer to (should be 443 for ACME compliance)
        cert_file: TLS certificate file for the multiplexer
        key_file: TLS private key file for the multiplexer
        grpc_server: gRPC server instance to start on internal port
        tls_alpn_server: TLS-ALPN challenge server instance
        grpc_internal_port: Internal port for the gRPC server (default: 50051)

    Returns:
        Configured and started ALPNMultiplexer

    Raises:
        Exception: If the gRPC server fails to start or multiplexer setup fails
    """
    logger.info(
        "Setting up ALPN multiplexer with gRPC server on internal port "
        f"{grpc_internal_port}"
    )

    # Start the gRPC server on the internal port (insecure, since it's local)
    # Override the server's port to use the internal port
    grpc_server.port = grpc_internal_port
    grpc_server.host = "127.0.0.1"  # Bind to localhost only
    grpc_server.use_tls = False  # No TLS needed for internal connection

    try:
        # Start the gRPC server
        grpc_server.start()
        logger.info(f"gRPC server started on 127.0.0.1:{grpc_internal_port}")

        # Create the bridge and wire both components
        bridge = TLSALPNBridge()
        multiplexer = ALPNMultiplexer(
            host=host, port=port, cert_file=cert_file, key_file=key_file, bridge=bridge
        )
        if hasattr(tls_alpn_server, "_attach_bridge"):
            tls_alpn_server._attach_bridge(bridge)

        # Register handlers with the internal gRPC port
        multiplexer.register_handler(
            "h2", GRPCHandler(grpc_server_port=grpc_internal_port)
        )
        multiplexer.register_handler("acme-tls/1", TLSALPNHandler(tls_alpn_server))

        # Start the multiplexer
        await multiplexer.start()

        logger.info(f"ALPN multiplexer ready - gRPC and TLS-ALPN-01 on {host}:{port}")
        return multiplexer

    except Exception as e:
        # Clean up if something goes wrong
        logger.error(f"Failed to set up ALPN multiplexer: {e}")
        with contextlib.suppress(Exception):
            grpc_server.stop()
        raise
