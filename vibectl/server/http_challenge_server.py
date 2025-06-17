"""
HTTP Challenge Server for ACME HTTP-01 challenges.

This module provides a lightweight HTTP server specifically designed to handle
ACME HTTP-01 challenges. It runs concurrently with the main gRPC server to
serve challenge responses during certificate provisioning and renewal.
"""

import asyncio
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aiohttp import web
from aiohttp.web import Application, Request, Response

# Re-use _build_hsts_header helper from grpc_server to keep logic consistent
from vibectl.server.grpc_server import _build_hsts_header

logger = logging.getLogger(__name__)


class HTTPChallengeServer:
    """HTTP server for ACME HTTP-01 challenges.

    This server handles HTTP-01 challenge validation requests from ACME servers.
    It serves challenge responses from a configurable directory structure.

    Features:
    - Lightweight asyncio-based HTTP server
    - Serves /.well-known/acme-challenge/ endpoints
    - Thread-safe challenge file management
    - Graceful shutdown support
    - Health check endpoint
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 80,
        challenge_dir: str | None = None,
        *,
        hsts_settings: dict | None = None,
        redirect_http: bool = False,
    ) -> None:
        """Initialize the HTTP challenge server.

        Args:
            host: Host to bind to (default: 0.0.0.0)
            port: Port to bind to (default: 80)
            challenge_dir: Directory to serve challenges from. If None,
                          uses in-memory challenge storage.
            hsts_settings: HSTS settings for the server
            redirect_http: Whether to redirect HTTP requests to HTTPS
        """
        self.host = host
        self.port = port
        self.challenge_dir = Path(challenge_dir) if challenge_dir else None
        self.app: Application | None = None
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None

        # In-memory challenge storage (when not using filesystem)
        self._challenges: dict[str, str] = {}
        self._lock = threading.Lock()

        # Server state
        self._running = False
        self._start_event = asyncio.Event()

        # HSTS / redirect settings
        self._hsts_settings = hsts_settings or {}
        self._redirect_http = redirect_http and self._hsts_settings.get(
            "enabled", False
        )

    def _redact_token(self, token: str) -> str:
        """Redact token for logging while preserving usefulness."""
        if hasattr(token, "_mock_name") or not isinstance(token, str):
            return "redacted (test mock)"
        return f"{token[:8]}..." if len(token) > 8 else token

    async def create_app(self) -> Application:
        """Create the aiohttp application with routes."""
        app = web.Application()

        # ------------------------------------------------------------------
        # Middleware for HSTS header injection and optional redirects

        @web.middleware
        async def hsts_middleware(request: Request, handler: Callable[[Request], Any]):  # type: ignore
            # Optionally redirect before handling
            if (
                self._redirect_http
                and not request.path.startswith("/.well-known/acme-challenge/")
                and request.path != "/health"
            ):
                https_url = f"https://{request.host}{request.path_qs}"
                raise web.HTTPPermanentRedirect(location=https_url)

            # Proceed to handler
            response: Response = await handler(request)  # type: ignore[arg-type]

            # Inject HSTS header if enabled and TLS will be used downstream
            if self._hsts_settings.get("enabled", False):
                response.headers["Strict-Transport-Security"] = _build_hsts_header(
                    self._hsts_settings
                )

            return response

        app.middlewares.append(hsts_middleware)

        # ACME challenge endpoint
        app.router.add_get(
            "/.well-known/acme-challenge/{token}", self._handle_challenge
        )

        # Health check endpoint
        app.router.add_get("/health", self._handle_health)

        # Catch-all for debugging
        app.router.add_get("/{path:.*}", self._handle_catchall)

        return app

    async def _handle_challenge(self, request: Request) -> Response:
        """Handle ACME challenge requests."""
        token = request.match_info["token"]

        # Special-case the common "health" probe token to avoid noisy 404/warning logs
        # and simplify external health checking of the challenge service.  Return a
        # standard 200 OK with a short body instead of treating it as a missing
        # challenge.  This is useful for Kubernetes probes and demo scripts that hit
        # `/.well-known/acme-challenge/health` before any real challenge tokens are
        # present.
        if token.lower() == "health":
            logger.debug("Received health probe on ACME challenge endpoint")
            return web.Response(text="OK", content_type="text/plain")

        logger.debug(f"ACME challenge request for token: {self._redact_token(token)}")

        # Get challenge response
        challenge_response = await self._get_challenge_response(token)

        if challenge_response is None:
            logger.warning(f"Challenge token not found: {self._redact_token(token)}")
            return web.Response(text=f"Challenge token not found: {token}", status=404)

        logger.info(f"Serving ACME challenge for token: {self._redact_token(token)}")
        return web.Response(text=challenge_response, content_type="text/plain")

    async def _get_challenge_response(self, token: str) -> str | None:
        """Get the challenge response for a token."""

        # Try filesystem first if challenge_dir is configured
        if self.challenge_dir:
            challenge_file = self.challenge_dir / token
            try:
                if challenge_file.exists():
                    content = challenge_file.read_text().strip()
                    logger.debug(f"Found challenge file: {challenge_file}")
                    return content
            except Exception as e:
                logger.warning(f"Error reading challenge file {challenge_file}: {e}")

        # Try in-memory storage
        with self._lock:
            return self._challenges.get(token)

    async def _handle_health(self, request: Request) -> Response:
        """Handle health check requests."""
        return web.Response(text="OK", content_type="text/plain")

    async def _handle_catchall(self, request: Request) -> Response:
        """Handle all other requests for debugging."""
        path = request.match_info.get("path", "")
        logger.debug(f"HTTP request to: /{path}")

        return web.Response(
            text=f"vibectl HTTP challenge server\nPath: /{path}\n",
            status=404,
            content_type="text/plain",
        )

    def set_challenge(self, token: str, response: str) -> None:
        """Set a challenge response (in-memory storage).

        Args:
            token: Challenge token
            response: Challenge response content
        """
        with self._lock:
            self._challenges[token] = response
            logger.debug(f"Set challenge token: {self._redact_token(token)}")

    def remove_challenge(self, token: str) -> None:
        """Remove a challenge response (in-memory storage).

        Args:
            token: Challenge token to remove
        """
        with self._lock:
            self._challenges.pop(token, None)
            logger.debug(f"Removed challenge token: {self._redact_token(token)}")

    def clear_challenges(self) -> None:
        """Clear all challenge responses."""
        with self._lock:
            self._challenges.clear()
            logger.debug("Cleared all challenge tokens")

    async def start(self) -> None:
        """Start the HTTP challenge server."""
        if self._running:
            logger.warning("HTTP challenge server is already running")
            return

        try:
            logger.info(f"Starting HTTP challenge server on {self.host}:{self.port}")

            # Create application
            self.app = await self.create_app()

            # Create runner and site
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()

            self.site = web.TCPSite(self.runner, self.host, self.port)
            await self.site.start()

            # Get the actual port if port 0 was used (auto-assign)
            if self.port == 0:
                # For port 0 (auto-assign), skip the readiness check
                # aiohttp handles the binding correctly and the server is ready after
                # site.start()
                logger.debug("Port 0 used (auto-assign), skipping port readiness check")
                # Skip port readiness check for auto-assigned ports
            else:
                # Wait for the port to actually be listening
                await self._wait_for_port_ready(self.port)

            self._running = True
            self._start_event.set()

            logger.info(f"HTTP challenge server started on {self.host}:{self.port}")

            if self.challenge_dir:
                logger.info(f"Serving challenges from directory: {self.challenge_dir}")
            else:
                logger.info("Using in-memory challenge storage")

        except Exception as e:
            logger.error(f"Failed to start HTTP challenge server: {e}")
            await self._cleanup()
            raise

    async def _wait_for_port_ready(self, port: int, timeout: float = 5.0) -> None:
        """Wait for the port to actually be listening.

        Args:
            port: The actual port number to check
            timeout: Maximum time to wait in seconds
        """
        import asyncio
        import socket

        start_time = asyncio.get_event_loop().time()

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            try:
                # Test if we can connect to our own port
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.1)
                result = sock.connect_ex(
                    (self.host if self.host != "0.0.0.0" else "localhost", port)
                )
                sock.close()

                if result == 0:
                    logger.debug(f"Port {port} is now listening")
                    return

            except Exception as e:
                logger.debug(f"Port check failed: {e}")

            await asyncio.sleep(0.1)

        raise RuntimeError(f"Port {port} not listening after {timeout} seconds")

    async def stop(self) -> None:
        """Stop the HTTP challenge server."""
        if not self._running:
            return

        logger.info("Stopping HTTP challenge server...")

        await self._cleanup()

        self._running = False
        self._start_event.clear()

        logger.info("HTTP challenge server stopped")

    async def _cleanup(self) -> None:
        """Cleanup server resources."""
        if self.site:
            await self.site.stop()
            self.site = None

        if self.runner:
            await self.runner.cleanup()
            self.runner = None

        self.app = None

    async def wait_until_ready(self, timeout: float = 5.0) -> bool:
        """Wait until the server is ready to serve requests.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if server is ready, False if timeout occurred
        """
        try:
            await asyncio.wait_for(self._start_event.wait(), timeout=timeout)
            return True
        except TimeoutError:
            return False

    @property
    def is_running(self) -> bool:
        """Check if the server is currently running."""
        return self._running

    def get_challenge_url(self, token: str) -> str:
        """Get the full URL for a challenge token.

        Args:
            token: Challenge token

        Returns:
            Full URL for the challenge
        """
        return f"http://{self.host}:{self.port}/.well-known/acme-challenge/{token}"


async def start_challenge_server(
    host: str = "0.0.0.0", port: int = 80, challenge_dir: str | None = None
) -> HTTPChallengeServer:
    """Start an HTTP challenge server.

    Args:
        host: Host to bind to
        port: Port to bind to
        challenge_dir: Optional directory to serve challenges from

    Returns:
        Running HTTPChallengeServer instance
    """
    server = HTTPChallengeServer(host=host, port=port, challenge_dir=challenge_dir)
    await server.start()
    return server


# Context manager for temporary challenge server
class TemporaryChallengeServer:
    """Context manager for temporary HTTP challenge server."""

    def __init__(self, **kwargs: Any):
        """Initialize with HTTPChallengeServer arguments."""
        self.kwargs = kwargs
        self.server: HTTPChallengeServer | None = None

    async def __aenter__(self) -> HTTPChallengeServer:
        """Start the server."""
        self.server = await start_challenge_server(**self.kwargs)
        return self.server

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Stop the server."""
        if self.server:
            await self.server.stop()
