from pathlib import Path
from unittest.mock import patch

import pytest

from vibectl.subcommands import setup_proxy_cmd as spc
from vibectl.types import Error


@pytest.mark.parametrize(
    "url, expected_msg_part",
    [
        ("", "cannot be empty"),
        ("http://example.com", "Invalid URL scheme"),
        ("vibectl-server://", "hostname"),
        ("vibectl-server://host:-1", "port"),
    ],
)
def test_validate_proxy_url_errors(url: str, expected_msg_part: str) -> None:
    """validate_proxy_url returns a helpful error message for bad input."""
    valid, msg = spc.validate_proxy_url(url)
    assert not valid
    assert msg and expected_msg_part.lower() in msg.lower()


def test_print_server_info_without_limits() -> None:
    """_print_server_info works when 'limits' key is absent."""
    minimal_data = {
        "server_name": "srv",
        "version": "0.0.1",
        "supported_models": [],
    }
    with patch.object(spc.console_manager, "safe_print") as mock_safe_print:
        spc._print_server_info(minimal_data)
    mock_safe_print.assert_called_once()


@pytest.mark.asyncio
async def test_check_proxy_connection_invalid_url() -> None:
    """check_proxy_connection returns Error for malformed URLs without grpc call."""
    res = await spc.check_proxy_connection("not-a-url")
    assert isinstance(res, Error)


@pytest.mark.asyncio
async def test_check_proxy_connection_missing_ca_file(tmp_path: Path) -> None:
    """Providing non-existent CA bundle path should yield Error early."""
    url = "vibectl-server://localhost:443"
    missing_file = tmp_path / "no-such-ca.pem"
    res = await spc.check_proxy_connection(url, ca_bundle=str(missing_file))
    assert isinstance(res, Error)
    assert "not found" in res.error.lower()
