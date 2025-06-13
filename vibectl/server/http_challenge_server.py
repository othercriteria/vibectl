"""
HTTP Challenge Server for ACME HTTP-01 challenges.

This module provides a lightweight HTTP server specifically designed to handle
ACME HTTP-01 challenges. It runs concurrently with the main gRPC server to
serve challenge responses during certificate provisioning and renewal.
"""

import asyncio
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from aiohttp import web
from aiohttp.web import Application, Request, Response

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
        challenge_dir: Optional[str] = None,
    ):
        """Initialize the HTTP challenge server.

        Args:
            host: Host to bind to (default: 0.0.0.0)
            port: Port to bind to (default: 80)
            challenge_dir: Directory to serve challenges from. If None,
                          uses in-memory challenge storage.
        """
        self.host = host
        self.port = port
        self.challenge_dir = Path(challenge_dir) if challenge_dir else None
        self.app: Optional[Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None

        # In-memory challenge storage (when not using filesystem)
        self._challenges: Dict[str, str] = {}
        self._lock = threading.Lock()

        # Server state
        self._running = False
        self._start_event = asyncio.Event()

    async def create_app(self) -> Application:
        """Create the aiohttp application with routes."""
        app = web.Application()

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

        logger.debug(f"ACME challenge request for token: {token}")

        # Get challenge response
        challenge_response = await self._get_challenge_response(token)

        if challenge_response is None:
            logger.warning(f"Challenge token not found: {token}")
            return web.Response(text=f"Challenge token not found: {token}", status=404)

        logger.info(f"Serving ACME challenge for token: {token}")
        return web.Response(text=challenge_response, content_type="text/plain")

    async def _get_challenge_response(self, token: str) -> Optional[str]:
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
            logger.debug(f"Set challenge token: {token}")

    def remove_challenge(self, token: str) -> None:
        """Remove a challenge response (in-memory storage).

        Args:
            token: Challenge token to remove
        """
        with self._lock:
            self._challenges.pop(token, None)
            logger.debug(f"Removed challenge token: {token}")

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
        except asyncio.TimeoutError:
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
    host: str = "0.0.0.0", port: int = 80, challenge_dir: Optional[str] = None
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
        self.server: Optional[HTTPChallengeServer] = None

    async def __aenter__(self) -> HTTPChallengeServer:
        """Start the server."""
        self.server = await start_challenge_server(**self.kwargs)
        return self.server

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Stop the server."""
        if self.server:
            await self.server.stop()
