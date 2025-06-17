from unittest.mock import patch

import pytest

from vibectl.subcommands import setup_proxy_cmd as spc


@pytest.mark.parametrize(
    "url",
    [
        "vibectl-server://example.com:443",
        "vibectl-server://token123@example.com:443",
        "vibectl-server-insecure://localhost:50051",
    ],
)
def test_validate_proxy_url_valid(url: str) -> None:
    """validate_proxy_url should accept well-formed vibectl URLs."""
    is_valid, error = spc.validate_proxy_url(url)
    assert is_valid, f"Expected valid URL: {url} (error: {error})"
    assert error is None


@pytest.mark.parametrize(
    "url",
    [
        "",  # empty
        "http://bad.com",  # wrong scheme
        "vibectl://host",  # unknown scheme
        "vibectl-server://",  # missing host
    ],
)
def test_validate_proxy_url_invalid(url: str) -> None:
    """validate_proxy_url should reject malformed URLs."""
    is_valid, error = spc.validate_proxy_url(url)
    assert not is_valid
    assert error is not None and error != ""


def test_redact_jwt_in_url() -> None:
    """JWT token embedded in the URL should be redacted."""
    original = "vibectl-server://secretjwt@host.example.com:443"
    redacted = spc.redact_jwt_in_url(original)
    assert redacted == "vibectl-server://***@host.example.com:443"
    # Ensure the secret token is no longer present
    assert "secretjwt" not in redacted


def test_print_server_info_table() -> None:
    """Ensure _print_server_info renders without errors, using safe_print."""

    sample_data = {
        "server_name": "test-server",
        "version": "1.2.3",
        "supported_models": ["gpt-4", "claude-3"],
        "limits": {
            "max_request_size": 1024,
            "max_concurrent_requests": 5,
            "timeout_seconds": 30,
        },
    }

    with patch.object(spc.console_manager, "safe_print") as mock_safe_print:
        # Call function - should not raise and must invoke safe_print exactly once
        spc._print_server_info(sample_data)

    mock_safe_print.assert_called_once()
    # The first argument is the console, second should be a rich Table instance
    _, table_arg = mock_safe_print.call_args[0]
    # Avoid importing rich.Table directly; just assert it has a title attribute
    assert hasattr(table_arg, "title")
