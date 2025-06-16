"""Tests for core functions in setup_proxy_cmd.py:
- validation
- redaction
- connection testing."""

from unittest.mock import patch

from vibectl.subcommands.setup_proxy_cmd import (
    redact_jwt_in_url,
    validate_proxy_url,
)


class TestRedactJwtInUrl:
    """Test cases for redact_jwt_in_url function."""

    def test_redact_empty_url(self) -> None:
        """Test redaction of empty URL."""
        result = redact_jwt_in_url("")
        assert result == ""

    def test_redact_url_without_jwt(self) -> None:
        """Test redaction of URL without JWT token."""
        url = "vibectl-server://myserver.com:443"
        result = redact_jwt_in_url(url)
        assert result == url

    def test_redact_url_with_jwt(self) -> None:
        """Test redaction of URL with JWT token."""
        url = "vibectl-server://eyJhbGciOiJIUzI1NiJ9.test@myserver.com:443"
        result = redact_jwt_in_url(url)
        assert result == "vibectl-server://***@myserver.com:443"

    def test_redact_url_with_jwt_no_port(self) -> None:
        """Test redaction of URL with JWT token but no explicit port."""
        url = "vibectl-server://token123@myserver.com"
        result = redact_jwt_in_url(url)
        assert result == "vibectl-server://***@myserver.com"

    def test_redact_insecure_url_with_jwt(self) -> None:
        """Test redaction of insecure URL with JWT token."""
        url = "vibectl-server-insecure://secret@localhost:50051"
        result = redact_jwt_in_url(url)
        assert result == "vibectl-server-insecure://***@localhost:50051"

    def test_redact_invalid_url_format(self) -> None:
        """Test redaction handles invalid URL format gracefully."""
        url = "not-a-valid-url"
        result = redact_jwt_in_url(url)
        assert result == url

    def test_redact_jwt_with_port(self) -> None:
        """Test JWT redaction with port number."""
        url = "vibectl-server://mytoken123@example.com:8443/path"
        result = redact_jwt_in_url(url)
        assert result == "vibectl-server://***@example.com:8443/path"

    def test_redact_jwt_invalid_url(self) -> None:
        """Test JWT redaction with invalid URL."""
        # Test with URL that causes parsing exception
        invalid_url = "not-a-valid-url"
        result = redact_jwt_in_url(invalid_url)
        # Should return original URL when parsing fails
        assert result == invalid_url


class TestValidateProxyUrl:
    """Test cases for validate_proxy_url function."""

    def test_validate_proxy_url_success(self) -> None:
        """Test valid proxy URL validation."""
        is_valid, error = validate_proxy_url("vibectl-server://test.com:443")
        assert is_valid is True
        assert error is None

    def test_validate_proxy_url_empty(self) -> None:
        """Test empty URL validation."""
        is_valid, error = validate_proxy_url("")
        assert is_valid is False
        assert error == "Proxy URL cannot be empty"

    def test_validate_proxy_url_whitespace_only(self) -> None:
        """Test whitespace-only URL validation."""
        is_valid, error = validate_proxy_url("   ")
        assert is_valid is False
        assert error == "Proxy URL cannot be empty"

    def test_validate_proxy_url_invalid_scheme(self) -> None:
        """Test invalid scheme validation."""
        is_valid, error = validate_proxy_url("http://test.com:443")
        assert is_valid is False
        assert error is not None
        assert "Invalid URL scheme" in error

    def test_validate_proxy_url_no_hostname(self) -> None:
        """Test URL without hostname."""
        is_valid, error = validate_proxy_url("vibectl-server://:443")
        assert is_valid is False
        assert error == "URL must include a hostname"

    def test_validate_proxy_url_invalid_port_low(self) -> None:
        """Test port 0 behavior - it's actually accepted and defaults to 50051."""
        # Port 0 is actually accepted and defaults to 50051
        is_valid, error = validate_proxy_url("vibectl-server://test.com:0")
        assert is_valid is True
        assert error is None

    def test_validate_proxy_url_invalid_port_negative(self) -> None:
        """Test negative port."""
        # Negative ports cause urlparse to raise an exception, caught
        # by the general exception handler
        is_valid, error = validate_proxy_url("vibectl-server://test.com:-1")
        assert is_valid is False
        assert error is not None
        assert "URL validation failed:" in error

    def test_validate_proxy_url_invalid_port_high(self) -> None:
        """Test invalid port (too high)."""
        # Very high ports cause urlparse to raise an exception, caught
        # by the general exception handler
        is_valid, error = validate_proxy_url("vibectl-server://test.com:99999")
        assert is_valid is False
        assert error is not None
        assert "URL validation failed:" in error

    def test_validate_proxy_url_parse_proxy_url_none(self) -> None:
        """Test when parse_proxy_url returns None."""
        with patch(
            "vibectl.subcommands.setup_proxy_cmd.parse_proxy_url", return_value=None
        ):
            is_valid, error = validate_proxy_url("vibectl-server://test.com:443")
            assert is_valid is False
            assert error == "Invalid proxy URL format"

    def test_validate_proxy_url_exception_handling(self) -> None:
        """Test exception handling in validate_proxy_url."""
        with patch(
            "vibectl.subcommands.setup_proxy_cmd.urlparse",
            side_effect=Exception("Parse error"),
        ):
            is_valid, error = validate_proxy_url("vibectl-server://test.com:443")
            assert is_valid is False
            assert error is not None
            assert "URL validation failed: Parse error" in error
