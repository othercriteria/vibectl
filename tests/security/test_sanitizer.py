"""Tests for RequestSanitizer security module."""

from vibectl.security.config import SecurityConfig
from vibectl.security.sanitizer import DetectedSecret, RequestSanitizer


class TestRequestSanitizer:
    """Test the RequestSanitizer class."""

    def test_sanitizer_disabled_by_config(self) -> None:
        """Test that sanitizer is disabled when configured to be."""
        config = SecurityConfig(sanitize_requests=False)
        sanitizer = RequestSanitizer(config)

        assert not sanitizer.enabled

        # Should pass through unchanged
        text = (
            "Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6IktBblNRVzh2RGpISzRUc0Z6eUo4NFBIdXhBM"
            "EVlLUJWTkctdW9qeUhMaWsiLCJ0eXAiOiJKV1QifQ"
        )
        sanitized, secrets = sanitizer.sanitize_request(text)

        assert sanitized == text
        assert len(secrets) == 0

    def test_sanitizer_enabled_by_config(self) -> None:
        """Test that sanitizer is enabled when configured to be."""
        config = SecurityConfig(sanitize_requests=True)
        sanitizer = RequestSanitizer(config)

        assert sanitizer.enabled

    def test_bearer_token_detection(self) -> None:
        """Test detection of Bearer tokens."""
        config = SecurityConfig(sanitize_requests=True)
        sanitizer = RequestSanitizer(config)

        text = (
            "Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6IktBblNRVzh2RGpIS"
            "zRUc0Z6eUo4NFBIdXhBMEVlLUJWTkctdW9qeUhMaWsiLCJ0eXAiOiJKV1QifQ"
        )
        sanitized, secrets = sanitizer.sanitize_request(text)

        assert len(secrets) == 1
        assert secrets[0].secret_type == "k8s-token"
        assert secrets[0].confidence > 0.8
        assert "Authorization: Bearer [REDACTED-k8s-token-106-chars]" in sanitized
        assert (
            "eyJhbGciOiJSUzI1NiIsImtpZCI6IktBblNRVzh2RGpISzRUc0Z6eUo4NFBIdXhBMEVlLUJWTkctdW9qeUhMaWsiLCJ0eXAiOiJKV1QifQ"
            not in sanitized
        )

    def test_jwt_token_detection(self) -> None:
        """Test detection of JWT tokens."""
        config = SecurityConfig(sanitize_requests=True)
        sanitizer = RequestSanitizer(config)

        jwt_token = (
            "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9."
            "eyJhdWQiOiJrdWJlcm5ldGVzIiwiaXNzIjoia3ViZXJuZXRlcy5kZWZhd"
            "Wx0LnN2Yy5jbHVzdGVyLmxvY2FsIiwia3ViZXJuZXRlcy5pbyI6eyJuYW"
            "1lc3BhY2UiOiJkZWZhdWx0Iiwic2VydmljZWFjY291bnQiOnsibmFtZSI"
            "6InZpYmUtc2EiLCJ1aWQiOiI3NDY2NTY2ZC1jNzE2LTQzNTAtYTMyMy1i"
            "NGUzZWY5NzY4MzgifX0sIm5iZiI6MTczNDc5MTY4Nywic3ViIjoic3lzd"
            "GVtOnNlcnZpY2VhY2NvdW50OmRlZmF1bHQ6dmliZS1zYSJ9."
            "A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0U1V2W3X4Y5Z6"
        )
        text = f"Using token: {jwt_token}"

        sanitized, secrets = sanitizer.sanitize_request(text)

        assert len(secrets) == 1
        assert secrets[0].secret_type == "k8s-token"
        assert secrets[0].confidence > 0.9  # Should be very confident about JWT
        assert jwt_token not in sanitized
        assert "[REDACTED-k8s-token-" in sanitized

    def test_base64_secret_detection(self) -> None:
        """Test detection of base64 encoded secrets."""
        config = SecurityConfig(sanitize_requests=True)
        sanitizer = RequestSanitizer(config)

        # High-entropy base64 (likely a secret)
        high_entropy_b64 = "dGVzdC1zZWNyZXQtaGlnaC1lbnRyb3B5LXZhbHVlLWF3ZXNvbWU="
        text = f"data: {high_entropy_b64}"

        sanitized, secrets = sanitizer.sanitize_request(text)

        assert len(secrets) == 1
        assert secrets[0].secret_type == "base64-data"
        assert secrets[0].confidence > 0.7
        assert high_entropy_b64 not in sanitized
        assert "[REDACTED-base64-data-" in sanitized

    def test_certificate_detection(self) -> None:
        """Test detection of certificate data."""
        config = SecurityConfig(sanitize_requests=True)
        sanitizer = RequestSanitizer(config)

        cert_data = """-----BEGIN CERTIFICATE-----
MIIDXTCCAkWgAwIBAgIJAL5R9QEZ3QZ7MA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNV
BAYTAkFVMRMwEQYDVQQIDApTb21lLVN0YXRlMSEwHwYDVQQKDBhJbnRlcm5ldCBX
aWRnaXRzIFB0eSBMdGQwHhcNMjMxMjA4MDAwMDAwWhcNMjQxMjA3MjM1OTU5WjBF
MQswCQYDVQQGEwJBVTETMBEGA1UECAwKU29tZS1TdGF0ZTEhMB8GA1UECgwYSW50
ZXJuZXQgV2lkZ2l0cyBQdHkgTHRkMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIB
CgKCAQEAyKxbRcGNPaDNOI1AQHh/z6cUvXsZ8Eq8u8b+jC9Cg7YdWZVOhNdBqGtF
X8HxHi9zU7HKQE9kGXzQ2n3r9HxTU9X1+qgGxwERCbvCXL1Kn7jZkH5A3vHxgGnr
+yY9+qOgPcDxXX1JvKgV+V8yCLQ1e8p8AHfNvM8xJtGG8F8g7zHnH2cGg8B/qE9z
-----END CERTIFICATE-----"""
        text = f"Certificate data:\n{cert_data}"

        sanitized, secrets = sanitizer.sanitize_request(text)

        assert len(secrets) == 1
        assert secrets[0].secret_type == "certificate"
        assert secrets[0].confidence > 0.9
        assert "BEGIN CERTIFICATE" not in sanitized
        assert "[REDACTED-certificate-" in sanitized

    def test_multiple_secrets_detection(self) -> None:
        """Test detection of multiple secrets in one request."""
        config = SecurityConfig(sanitize_requests=True)
        sanitizer = RequestSanitizer(config)

        text = """
        I need help with:
        1. This bearer token:
             Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJrdWJlcm5ldGVzIn0.signature
        2. This base64 data:
             dGVzdC1zZWNyZXQtaGlnaC1lbnRyb3B5LXZhbHVlLWF3ZXNvbWU=
        3. Show me the pods
        """

        sanitized, secrets = sanitizer.sanitize_request(text)

        assert len(secrets) == 2  # Bearer token and base64 data
        secret_types = [s.secret_type for s in secrets]
        assert "k8s-token" in secret_types
        assert "base64-data" in secret_types

        # Verify both secrets are redacted
        assert "eyJhbGciOiJSUzI1NiJ9" not in sanitized
        assert "dGVzdC1zZWNyZXQtaGlnaC1lbnRyb3B5" not in sanitized
        assert "Show me the pods" in sanitized  # Non-secret content preserved

    def test_low_entropy_base64_ignored(self) -> None:
        """Test that low-entropy base64 (like repeated chars) is not flagged."""
        config = SecurityConfig(sanitize_requests=True)
        sanitizer = RequestSanitizer(config)

        # Low entropy base64 (repeated pattern)
        low_entropy_b64 = (
            "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFh"  # "aaaaaaaaaaaaaaaaaaaa" in base64
        )
        text = f"data: {low_entropy_b64}"

        sanitized, secrets = sanitizer.sanitize_request(text)

        # Should not detect this as a secret due to low entropy
        assert len(secrets) == 0
        assert sanitized == text

    def test_short_base64_ignored(self) -> None:
        """Test that very short base64 strings are not flagged as secrets."""
        config = SecurityConfig(sanitize_requests=True)
        sanitizer = RequestSanitizer(config)

        # Very short base64
        short_b64 = "dGVzdA=="  # "test" in base64
        text = f"data: {short_b64}"

        sanitized, secrets = sanitizer.sanitize_request(text)

        # Should not detect this as a secret due to short length
        assert len(secrets) == 0
        assert sanitized == text

    def test_false_positive_jwt_ignored(self) -> None:
        """Test that strings that look like JWT but aren't are handled appropriately."""
        config = SecurityConfig(sanitize_requests=True)
        sanitizer = RequestSanitizer(config)

        # Has three parts separated by dots but not actual JWT
        fake_jwt = "abc.def.ghi"
        text = f"File: {fake_jwt}"

        sanitized, secrets = sanitizer.sanitize_request(text)

        # Should not detect this as a secret
        assert len(secrets) == 0
        assert sanitized == text

    def test_kubernetes_service_account_token(self) -> None:
        """Test detection of Kubernetes service account tokens."""
        config = SecurityConfig(sanitize_requests=True)
        sanitizer = RequestSanitizer(config)

        # Realistic K8s service account token structure
        sa_token = (
            "eyJhbGciOiJSUzI1NiIsImtpZCI6InNhLXRva2VuLWtleSJ9."
            "eyJpc3MiOiJrdWJlcm5ldGVzL3NlcnZpY2VhY2NvdW50Iiwia3ViZ"
            "XJuZXRlcy5pby9zZXJ2aWNlYWNjb3VudC9uYW1lc3BhY2UiOiJkZW"
            "ZhdWx0Iiwia3ViZXJuZXRlcy5pby9zZXJ2aWNlYWNjb3VudC9zZWN"
            "yZXQubmFtZSI6InZpYmUtc2EtdG9rZW4iLCJrdWJlcm5ldGVzLmlvL3"
            "NlcnZpY2VhY2NvdW50L3NlcnZpY2UtYWNjb3VudC5uYW1lIjoidmliZS"
            "1zYSJ9."
            "SomeReallyLongSignatureDataHereToMakeItLookRealistic123456789"
        )
        text = f"serviceaccount token: {sa_token}"

        sanitized, secrets = sanitizer.sanitize_request(text)

        assert len(secrets) == 1
        assert secrets[0].secret_type == "k8s-token"
        assert secrets[0].confidence > 0.9
        assert sa_token not in sanitized
        assert "[REDACTED-k8s-token-" in sanitized

    def test_empty_input(self) -> None:
        """Test sanitizer with empty input."""
        config = SecurityConfig(sanitize_requests=True)
        sanitizer = RequestSanitizer(config)

        sanitized, secrets = sanitizer.sanitize_request("")

        assert sanitized == ""
        assert len(secrets) == 0

    def test_none_input(self) -> None:
        """Test sanitizer with None input."""
        config = SecurityConfig(sanitize_requests=True)
        sanitizer = RequestSanitizer(config)

        sanitized, secrets = sanitizer.sanitize_request(None)

        assert sanitized == ""
        assert len(secrets) == 0

    def test_whitespace_only_input(self) -> None:
        """Test sanitizer with whitespace-only input."""
        config = SecurityConfig(sanitize_requests=True)
        sanitizer = RequestSanitizer(config)

        text = "   \n\t   "
        sanitized, secrets = sanitizer.sanitize_request(text)

        assert sanitized == text
        assert len(secrets) == 0

    def test_detected_secret_properties(self) -> None:
        """Test DetectedSecret properties and methods."""
        secret = DetectedSecret(
            secret_type="test-type",
            start_pos=10,
            end_pos=20,
            original_text="secretvalue",
            confidence=0.95,
        )

        assert secret.secret_type == "test-type"
        assert secret.start_pos == 10
        assert secret.end_pos == 20
        assert secret.original_text == "secretvalue"
        assert secret.confidence == 0.95
        assert secret.length == 11  # len("secretvalue")

    def test_config_integration(self) -> None:
        """Test that SecurityConfig properly configures the sanitizer."""
        # Test with sanitization disabled
        config_disabled = SecurityConfig(sanitize_requests=False)
        sanitizer_disabled = RequestSanitizer(config_disabled)
        assert not sanitizer_disabled.enabled

        # Test with sanitization enabled
        config_enabled = SecurityConfig(sanitize_requests=True)
        sanitizer_enabled = RequestSanitizer(config_enabled)
        assert sanitizer_enabled.enabled


class TestRequestSanitizerEdgeCases:
    """Test edge cases and error conditions for RequestSanitizer."""

    def test_overlapping_detections(self) -> None:
        """Test behavior when secrets might overlap."""
        config = SecurityConfig(sanitize_requests=True)
        sanitizer = RequestSanitizer(config)

        # Text where a JWT token might contain base64-like segments
        jwt_token = (
            "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJrdWJlcm5ldGVzIn0."
            "dGVzdC1zZWNyZXQtaGlnaC1lbnRyb3B5LXZhbHVlLWF3ZXNvbWU"
        )
        text = f"Token: {jwt_token}"

        sanitized, secrets = sanitizer.sanitize_request(text)

        # Should primarily detect as JWT/k8s-token, not separate base64 pieces
        assert len(secrets) >= 1
        assert any(s.secret_type == "k8s-token" for s in secrets)
        assert jwt_token not in sanitized

    def test_very_long_input(self) -> None:
        """Test sanitizer with very long input text."""
        config = SecurityConfig(sanitize_requests=True)
        sanitizer = RequestSanitizer(config)

        # Create a long text with a secret in the middle
        long_prefix = "This is a very long text. " * 1000
        secret_token = (
            "Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJrdWJlcm5ldGVzIn0.signature"
        )
        long_suffix = " And this continues for a while." * 1000
        text = long_prefix + secret_token + long_suffix

        sanitized, secrets = sanitizer.sanitize_request(text)

        assert len(secrets) == 1
        assert secrets[0].secret_type == "k8s-token"
        assert "eyJhbGciOiJSUzI1NiJ9" not in sanitized
        assert long_prefix[:50] in sanitized  # Prefix should be preserved
        assert long_suffix[-50:] in sanitized  # Suffix should be preserved

    def test_special_characters_in_secrets(self) -> None:
        """Test handling of secrets containing special regex characters."""
        config = SecurityConfig(sanitize_requests=True)
        sanitizer = RequestSanitizer(config)

        # Base64 with special characters that could break regex
        special_b64 = "dGVzdC1zZWNyZXQrLz0="  # Contains +, /, =
        text = f"data: {special_b64}"

        sanitized, secrets = sanitizer.sanitize_request(text)

        # Should handle special characters correctly
        if secrets:  # May or may not be detected depending on entropy
            assert special_b64 not in sanitized

    def test_unicode_handling(self) -> None:
        """Test sanitizer with Unicode characters."""
        config = SecurityConfig(sanitize_requests=True)
        sanitizer = RequestSanitizer(config)

        # Text with Unicode and a secret
        text = (
            "こんにちは Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJrdWJlcm5ldGVzIn0."
            "signature 世界"
        )

        sanitized, secrets = sanitizer.sanitize_request(text)

        assert len(secrets) == 1
        assert secrets[0].secret_type == "k8s-token"
        assert "こんにちは" in sanitized
        assert "世界" in sanitized
        assert "eyJhbGciOiJSUzI1NiJ9" not in sanitized

    def test_multiline_certificate(self) -> None:
        """Test handling of multiline certificates with various formatting."""
        config = SecurityConfig(sanitize_requests=True)
        sanitizer = RequestSanitizer(config)

        multiline_cert = """-----BEGIN CERTIFICATE-----
MIIDXTCCAkWgAwIBAgIJAL5R9QEZ3QZ7MA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNV
BAYTAkFVMRMwEQYDVQQIDApTb21lLVN0YXRlMSEwHwYDVQQKDBhJbnRlcm5ldCBX
aWRnaXRzIFB0eSBMdGQwHhcNMjMxMjA4MDAwMDAwWhcNMjQxMjA3MjM1OTU5WjBF
-----END CERTIFICATE-----"""

        text = f"Here is my cert:\n{multiline_cert}\nPlease help."

        sanitized, secrets = sanitizer.sanitize_request(text)

        assert len(secrets) == 1
        assert secrets[0].secret_type == "certificate"
        assert "BEGIN CERTIFICATE" not in sanitized
        assert "Here is my cert:" in sanitized
        assert "Please help." in sanitized
