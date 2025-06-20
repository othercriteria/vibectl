"""Tests for security configuration classes."""

import pytest

from vibectl.security.config import ConfirmationMode, ProxyProfile, SecurityConfig


class TestConfirmationMode:
    """Test the ConfirmationMode enum."""

    def test_confirmation_mode_values(self) -> None:
        """Test that confirmation mode enum has expected values."""
        assert ConfirmationMode.NONE.value == "none"
        assert ConfirmationMode.PER_SESSION.value == "per-session"
        assert ConfirmationMode.PER_COMMAND.value == "per-command"

    def test_confirmation_mode_from_string(self) -> None:
        """Test creating ConfirmationMode from string values."""
        assert ConfirmationMode("none") == ConfirmationMode.NONE
        assert ConfirmationMode("per-session") == ConfirmationMode.PER_SESSION
        assert ConfirmationMode("per-command") == ConfirmationMode.PER_COMMAND

    def test_confirmation_mode_invalid_value(self) -> None:
        """Test that invalid confirmation mode values raise ValueError."""
        with pytest.raises(ValueError):
            ConfirmationMode("invalid-mode")


class TestSecurityConfig:
    """Test the SecurityConfig class."""

    def test_security_config_defaults(self) -> None:
        """Test SecurityConfig default values."""
        config = SecurityConfig()

        assert config.sanitize_requests is True
        assert config.audit_logging is True
        assert config.confirmation_mode == ConfirmationMode.PER_COMMAND
        assert config.audit_log_path is None
        assert config.warn_sanitization is True

    def test_security_config_custom_values(self) -> None:
        """Test SecurityConfig with custom values."""
        config = SecurityConfig(
            sanitize_requests=False,
            audit_logging=False,
            confirmation_mode=ConfirmationMode.NONE,
            audit_log_path="/tmp/audit.log",
            warn_sanitization=False,
        )

        assert config.sanitize_requests is False
        assert config.audit_logging is False
        assert config.confirmation_mode == ConfirmationMode.NONE
        assert config.audit_log_path == "/tmp/audit.log"
        assert config.warn_sanitization is False

    def test_security_config_from_dict_defaults(self) -> None:
        """Test SecurityConfig.from_dict() with empty dict uses defaults."""
        config = SecurityConfig.from_dict({})

        assert config.sanitize_requests is True
        assert config.audit_logging is True
        assert config.confirmation_mode == ConfirmationMode.PER_COMMAND
        assert config.audit_log_path is None
        assert config.warn_sanitization is True

    def test_security_config_from_dict_full(self) -> None:
        """Test SecurityConfig.from_dict() with all fields."""
        data = {
            "sanitize_requests": False,
            "audit_logging": False,
            "confirmation_mode": "none",
            "audit_log_path": "/var/log/audit.log",
            "warn_sanitization": False,
        }

        config = SecurityConfig.from_dict(data)

        assert config.sanitize_requests is False
        assert config.audit_logging is False
        assert config.confirmation_mode == ConfirmationMode.NONE
        assert config.audit_log_path == "/var/log/audit.log"
        assert config.warn_sanitization is False

    def test_security_config_from_dict_enum_object(self) -> None:
        """Test SecurityConfig.from_dict() with ConfirmationMode enum object."""
        data = {
            "confirmation_mode": ConfirmationMode.PER_SESSION,
        }

        config = SecurityConfig.from_dict(data)
        assert config.confirmation_mode == ConfirmationMode.PER_SESSION

    def test_security_config_to_dict(self) -> None:
        """Test SecurityConfig.to_dict() conversion."""
        config = SecurityConfig(
            sanitize_requests=False,
            audit_logging=True,
            confirmation_mode=ConfirmationMode.PER_SESSION,
            audit_log_path="/custom/audit.log",
            warn_sanitization=False,
        )

        result = config.to_dict()

        expected = {
            "sanitize_requests": False,
            "audit_logging": True,
            "confirmation_mode": "per-session",
            "audit_log_path": "/custom/audit.log",
            "warn_sanitization": False,
        }

        assert result == expected

    def test_security_config_round_trip(self) -> None:
        """Test SecurityConfig round-trip conversion (dict -> object -> dict)."""
        original_data = {
            "sanitize_requests": True,
            "audit_logging": False,
            "confirmation_mode": "per-command",
            "audit_log_path": "/tmp/test.log",
            "warn_sanitization": True,
        }

        config = SecurityConfig.from_dict(original_data)
        result_data = config.to_dict()

        assert result_data == original_data


class TestProxyProfile:
    """Test the ProxyProfile class."""

    def test_proxy_profile_minimal(self) -> None:
        """Test ProxyProfile with minimal required fields."""
        profile = ProxyProfile(
            name="test-profile", server_url="vibectl-server://example.com:443"
        )

        assert profile.name == "test-profile"
        assert profile.server_url == "vibectl-server://example.com:443"
        assert profile.jwt_path is None
        assert profile.ca_bundle_path is None
        assert profile.timeout_seconds is None
        assert profile.retry_attempts is None
        assert profile.security is None

    def test_proxy_profile_full(self) -> None:
        """Test ProxyProfile with all fields."""
        security = SecurityConfig(sanitize_requests=False)

        profile = ProxyProfile(
            name="full-profile",
            server_url="vibectl-server://secure.example.com:443",
            jwt_path="/path/to/jwt.token",
            ca_bundle_path="/path/to/ca.pem",
            timeout_seconds=60,
            retry_attempts=5,
            security=security,
        )

        assert profile.name == "full-profile"
        assert profile.server_url == "vibectl-server://secure.example.com:443"
        assert profile.jwt_path == "/path/to/jwt.token"
        assert profile.ca_bundle_path == "/path/to/ca.pem"
        assert profile.timeout_seconds == 60
        assert profile.retry_attempts == 5
        assert profile.security == security

    def test_proxy_profile_from_dict_minimal(self) -> None:
        """Test ProxyProfile.from_dict() with minimal data."""
        data = {"server_url": "vibectl-server://test.com:443"}

        profile = ProxyProfile.from_dict("test-profile", data)

        assert profile.name == "test-profile"
        assert profile.server_url == "vibectl-server://test.com:443"
        assert profile.jwt_path is None
        assert profile.ca_bundle_path is None
        assert profile.timeout_seconds is None
        assert profile.retry_attempts is None
        assert profile.security is None

    def test_proxy_profile_from_dict_full(self) -> None:
        """Test ProxyProfile.from_dict() with all fields."""
        data = {
            "server_url": "vibectl-server://full.example.com:443",
            "jwt_path": "/custom/jwt.token",
            "ca_bundle_path": "/custom/ca.pem",
            "timeout_seconds": 120,
            "retry_attempts": 3,
            "security": {
                "sanitize_requests": False,
                "audit_logging": True,
                "confirmation_mode": "per-session",
                "audit_log_path": "/custom/audit.log",
                "warn_sanitization": False,
            },
        }

        profile = ProxyProfile.from_dict("full-profile", data)

        assert profile.name == "full-profile"
        assert profile.server_url == "vibectl-server://full.example.com:443"
        assert profile.jwt_path == "/custom/jwt.token"
        assert profile.ca_bundle_path == "/custom/ca.pem"
        assert profile.timeout_seconds == 120
        assert profile.retry_attempts == 3

        assert profile.security is not None
        assert profile.security.sanitize_requests is False
        assert profile.security.audit_logging is True
        assert profile.security.confirmation_mode == ConfirmationMode.PER_SESSION
        assert profile.security.audit_log_path == "/custom/audit.log"
        assert profile.security.warn_sanitization is False

    def test_proxy_profile_from_dict_empty_security(self) -> None:
        """Test ProxyProfile.from_dict() with empty security dict.

        An empty security dict results in None security config,
        since empty dict is falsey in Python.
        """
        data = {"server_url": "vibectl-server://test.com:443", "security": {}}

        profile = ProxyProfile.from_dict("test-profile", data)

        # Empty dict is falsey, so security becomes None
        assert profile.security is None

    def test_proxy_profile_from_dict_no_security(self) -> None:
        """Test ProxyProfile.from_dict() with no security field."""
        data = {"server_url": "vibectl-server://test.com:443"}

        profile = ProxyProfile.from_dict("test-profile", data)
        assert profile.security is None

    def test_proxy_profile_from_dict_security_with_defaults(self) -> None:
        """Test ProxyProfile.from_dict() with security field containing partial data."""
        data = {
            "server_url": "vibectl-server://test.com:443",
            "security": {
                "sanitize_requests": False,
                # Other fields should use defaults
            },
        }

        profile = ProxyProfile.from_dict("test-profile", data)

        assert profile.security is not None
        assert profile.security.sanitize_requests is False
        assert profile.security.audit_logging is True  # Default
        assert (
            profile.security.confirmation_mode == ConfirmationMode.PER_COMMAND
        )  # Default
        assert profile.security.warn_sanitization is True  # Default

    def test_proxy_profile_to_dict_minimal(self) -> None:
        """Test ProxyProfile.to_dict() with minimal fields."""
        profile = ProxyProfile(
            name="test-profile", server_url="vibectl-server://test.com:443"
        )

        result = profile.to_dict()

        expected = {"server_url": "vibectl-server://test.com:443"}

        assert result == expected

    def test_proxy_profile_to_dict_full(self) -> None:
        """Test ProxyProfile.to_dict() with all fields."""
        security = SecurityConfig(
            sanitize_requests=False,
            confirmation_mode=ConfirmationMode.NONE,
        )

        profile = ProxyProfile(
            name="full-profile",
            server_url="vibectl-server://full.example.com:443",
            jwt_path="/path/to/jwt.token",
            ca_bundle_path="/path/to/ca.pem",
            timeout_seconds=90,
            retry_attempts=4,
            security=security,
        )

        result = profile.to_dict()

        expected = {
            "server_url": "vibectl-server://full.example.com:443",
            "jwt_path": "/path/to/jwt.token",
            "ca_bundle_path": "/path/to/ca.pem",
            "timeout_seconds": 90,
            "retry_attempts": 4,
            "security": {
                "sanitize_requests": False,
                "audit_logging": True,  # Default value
                "confirmation_mode": "none",
                "audit_log_path": None,
                "warn_sanitization": True,  # Default value
            },
        }

        assert result == expected

    def test_proxy_profile_round_trip(self) -> None:
        """Test ProxyProfile round-trip conversion (dict -> object -> dict)."""
        original_data = {
            "server_url": "vibectl-server://roundtrip.example.com:443",
            "jwt_path": "/round/trip.jwt",
            "ca_bundle_path": "/round/trip.ca",
            "timeout_seconds": 75,
            "retry_attempts": 2,
            "security": {
                "sanitize_requests": True,
                "audit_logging": False,
                "confirmation_mode": "per-command",
                "audit_log_path": "/round/trip.log",
                "warn_sanitization": False,
            },
        }

        profile = ProxyProfile.from_dict("roundtrip-profile", original_data)
        result_data = profile.to_dict()

        assert result_data == original_data

    def test_proxy_profile_missing_server_url(self) -> None:
        """Test ProxyProfile.from_dict() raises KeyError for missing server_url."""
        data = {"jwt_path": "/path/to/jwt.token"}

        with pytest.raises(KeyError):
            ProxyProfile.from_dict("invalid-profile", data)


class TestIntegration:
    """Integration tests for security config classes."""

    def test_security_config_in_proxy_profile(self) -> None:
        """Test that SecurityConfig integrates properly with ProxyProfile."""
        # Create a SecurityConfig
        security = SecurityConfig(
            sanitize_requests=False,
            confirmation_mode=ConfirmationMode.PER_SESSION,
            warn_sanitization=False,
        )

        # Create a ProxyProfile with the SecurityConfig
        profile = ProxyProfile(
            name="integration-test",
            server_url="vibectl-server://integration.test:443",
            security=security,
        )

        # Verify the integration
        assert profile.security is not None
        assert profile.security.sanitize_requests is False
        assert profile.security.confirmation_mode == ConfirmationMode.PER_SESSION
        assert profile.security.warn_sanitization is False

    def test_nested_config_serialization(self) -> None:
        """Test that nested SecurityConfig serializes correctly in ProxyProfile."""
        profile_data = {
            "server_url": "vibectl-server://nested.test:443",
            "security": {
                "sanitize_requests": True,
                "audit_logging": False,
                "confirmation_mode": "none",
                "warn_sanitization": True,
            },
        }

        # Convert to object and back
        profile = ProxyProfile.from_dict("nested-test", profile_data)
        result = profile.to_dict()

        # Verify security config was preserved
        assert "security" in result
        assert result["security"]["sanitize_requests"] is True
        assert result["security"]["audit_logging"] is False
        assert result["security"]["confirmation_mode"] == "none"
        assert result["security"]["warn_sanitization"] is True
