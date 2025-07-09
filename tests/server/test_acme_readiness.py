from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import pytest

from vibectl.server.acme_manager import ACMEManager
from vibectl.server.http_challenge_server import HTTPChallengeServer


@pytest.fixture()
def minimal_acme_http_config() -> dict[str, object]:
    """Return a minimal but valid ACME HTTP-01 config dict."""
    return {
        "enabled": True,
        "email": "test@example.com",
        "domains": ["localhost"],
        "directory_url": "https://acme.example.com/directory",
        "challenge": {"type": "http-01"},
        "http_port": 80,
    }


@pytest.mark.asyncio
async def test_wait_for_readiness_skips_for_mock(
    minimal_acme_http_config: dict[str, object],
) -> None:
    """If challenge_server is not a real HTTPChallengeServer the readiness wait
    should be skipped immediately (unit-test optimisation).
    """
    mock_server = Mock()  # Not an instance of HTTPChallengeServer

    manager = ACMEManager(
        challenge_server=mock_server, acme_config=minimal_acme_http_config
    )  # type: ignore[arg-type]

    with patch("asyncio.open_connection", new_callable=AsyncMock) as mock_open_conn:
        # Should return instantly and never try to open a socket
        await manager._wait_for_http01_readiness(timeout=0.1)
        mock_open_conn.assert_not_called()


@pytest.mark.asyncio
async def test_wait_for_readiness_success(
    minimal_acme_http_config: dict[str, object],
) -> None:
    """Successful readiness returns as soon as the socket is connectable."""

    challenge_server = HTTPChallengeServer(host="localhost", port=80)
    manager = ACMEManager(
        challenge_server=challenge_server, acme_config=minimal_acme_http_config
    )

    writer_mock = Mock()
    writer_mock.close = Mock()  # Synchronous close to match real StreamWriter
    writer_mock.wait_closed = AsyncMock()

    async_mock = AsyncMock(return_value=(None, writer_mock))
    with patch("asyncio.open_connection", async_mock):
        await manager._wait_for_http01_readiness(timeout=0.5)

    async_mock.assert_called()  # At least once


@pytest.mark.asyncio
async def test_wait_for_readiness_timeout(
    minimal_acme_http_config: dict[str, object],
) -> None:
    """If the socket never becomes reachable the method should exit after the
    timeout and perform several retries.
    """

    challenge_server = HTTPChallengeServer(host="localhost", port=80)
    manager = ACMEManager(
        challenge_server=challenge_server, acme_config=minimal_acme_http_config
    )

    with (
        patch("asyncio.open_connection", side_effect=ConnectionRefusedError),
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        await manager._wait_for_http01_readiness(timeout=0.2)

    # Called multiple times due to retries
    assert mock_sleep.await_count >= 1


@pytest.mark.asyncio
async def test_http_challenge_server_health_endpoint() -> None:
    """`GET /health` should return 200 OK once the server is started."""
    server = HTTPChallengeServer(host="127.0.0.1", port=0)
    await server.start()

    # Discover the actual bound port (since we used 0)
    assert server.site is not None, "Server site should not be None after start"
    assert server.site._server is not None, "Server instance should not be None"
    assert hasattr(server.site._server, "sockets"), (
        "Server should have sockets attribute"
    )
    sock = server.site._server.sockets[0]

    async with (
        aiohttp.ClientSession() as session,
        session.get(
            f"http://{sock.getsockname()[0]}:{sock.getsockname()[1]}/health"
        ) as resp,
    ):
        text = await resp.text()
        assert resp.status == 200
        assert text == "OK"

    await server.stop()
