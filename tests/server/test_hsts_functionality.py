"""Tests for HSTS configuration, header injection, and redirect behaviour.

These tests focus on verifying that:
1. ``_build_hsts_header`` returns correctly formatted header values for a
   variety of settings combinations.
2. ``HTTPChallengeServer`` injects the ``Strict-Transport-Security`` header
   when HSTS is enabled.
3. Requests to non-ACME paths are redirected to HTTPS when the combination of
   ``redirect_http`` **and** HSTS is enabled - simulating how HSTS helps thwart
   downgrade / mixed-content attacks.

The tests use an ephemeral ``HTTPChallengeServer`` listening on an OS-assigned
port (``port=0``) to avoid collisions and keep execution fast (< 1 s total).
"""

from __future__ import annotations

import aiohttp
import pytest

from vibectl.server.grpc_server import _build_hsts_header  # Helper under test
from vibectl.server.http_challenge_server import HTTPChallengeServer


@pytest.mark.parametrize(
    "settings,expected",
    [
        ({}, "max-age=31536000"),
        ({"max_age": 60}, "max-age=60"),
        (
            {"max_age": 60, "include_subdomains": True},
            "max-age=60; includeSubDomains",
        ),
        ({"max_age": 60, "preload": True}, "max-age=60; preload"),
        (
            {
                "max_age": 60,
                "include_subdomains": True,
                "preload": True,
            },
            "max-age=60; includeSubDomains; preload",
        ),
    ],
)
def test_build_hsts_header(settings: dict[str, object], expected: str) -> None:
    """``_build_hsts_header`` should build the RFC-compliant header value."""

    assert _build_hsts_header(settings) == expected


@pytest.mark.asyncio
async def test_hsts_header_injection_and_redirect() -> None:
    """Full integration test of HSTS middleware + redirect logic.

    The flow is:
    1. Spin up an ``HTTPChallengeServer`` with HSTS enabled **and**
       ``redirect_http`` set to *True* (attack-prevention mode).
    2. Verify:
       a. "Safe" endpoints (``/health`` and ACME challenge path) include the
          header and do **not** redirect.
       b. A generic path (``/unsafe``) triggers an HTTP 308 redirect to HTTPS.
    """

    # Given
    hsts_settings = {
        "enabled": True,
        "max_age": 86400,
        "include_subdomains": True,
    }

    expected_header = _build_hsts_header(hsts_settings)

    server = HTTPChallengeServer(
        host="127.0.0.1",
        port=0,  # Let the OS assign a free port
        hsts_settings=hsts_settings,
        redirect_http=True,
    )

    await server.start()
    try:
        # Discover bound host/port from the underlying socket
        assert (
            server.site and server.site._server and server.site._server.sockets  # type: ignore[attr-defined]
        ), "Server sockets should be initialised"
        sock = server.site._server.sockets[0]  # type: ignore[attr-defined]
        host, port = sock.getsockname()[:2]

        async with aiohttp.ClientSession() as session:
            # 1. /health - should *not* redirect but must include HSTS header.
            async with session.get(f"http://{host}:{port}/health") as resp:
                assert resp.status == 200
                assert resp.headers.get("Strict-Transport-Security") == expected_header

            # 2. ACME challenge path - allowed through, no redirect, header OK.
            async with session.get(
                f"http://{host}:{port}/.well-known/acme-challenge/token123"
            ) as resp:
                # Unknown token returns 404 but must not redirect and must
                # include HSTS header.
                assert resp.status == 404
                assert resp.headers.get("Strict-Transport-Security") == expected_header

            # 3. Arbitrary path - should redirect to HTTPS (mitigation behaviour).
            async with session.get(
                f"http://{host}:{port}/unsafe",
                allow_redirects=False,  # Capture redirect directly
            ) as resp:
                assert resp.status == 308
                # Location header must point to HTTPS version of same resource
                assert resp.headers["Location"] == f"https://{host}:{port}/unsafe"
                # Redirect response may omit HSTS - spec does not require it.

    finally:
        await server.stop()
