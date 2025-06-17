"""
Security configuration for proxy hardening.

This module handles security settings for named proxy profiles.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ConfirmationMode(Enum):
    """Confirmation mode for LLM operations."""

    NONE = "none"
    PER_SESSION = "per-session"
    PER_COMMAND = "per-command"


@dataclass
class SecurityConfig:
    """Security configuration for a proxy profile."""

    sanitize_requests: bool = True
    audit_logging: bool = True
    confirmation_mode: ConfirmationMode = ConfirmationMode.PER_COMMAND
    audit_log_path: str | None = None
    warn_sanitization: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SecurityConfig":
        """Create SecurityConfig from dictionary data.

        Args:
            data: Dictionary containing security configuration

        Returns:
            SecurityConfig instance
        """
        confirmation_mode = data.get("confirmation_mode", "per-command")
        if isinstance(confirmation_mode, str):
            confirmation_mode = ConfirmationMode(confirmation_mode)

        return cls(
            sanitize_requests=data.get("sanitize_requests", True),
            audit_logging=data.get("audit_logging", True),
            confirmation_mode=confirmation_mode,
            audit_log_path=data.get("audit_log_path"),
            warn_sanitization=data.get("warn_sanitization", True),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert SecurityConfig to dictionary.

        Returns:
            Dictionary representation of security config
        """
        return {
            "sanitize_requests": self.sanitize_requests,
            "audit_logging": self.audit_logging,
            "confirmation_mode": self.confirmation_mode.value,
            "audit_log_path": self.audit_log_path,
            "warn_sanitization": self.warn_sanitization,
        }


@dataclass
class ProxyProfile:
    """Configuration for a named proxy profile."""

    name: str
    server_url: str
    jwt_path: str | None = None
    ca_bundle_path: str | None = None
    timeout_seconds: int | None = None
    retry_attempts: int | None = None
    security: SecurityConfig | None = None

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> "ProxyProfile":
        """Create ProxyProfile from dictionary data.

        Args:
            name: Profile name
            data: Dictionary containing profile configuration

        Returns:
            ProxyProfile instance
        """
        security_data = data.get("security", {})
        security = SecurityConfig.from_dict(security_data) if security_data else None

        return cls(
            name=name,
            server_url=data["server_url"],
            jwt_path=data.get("jwt_path"),
            ca_bundle_path=data.get("ca_bundle_path"),
            timeout_seconds=data.get("timeout_seconds"),
            retry_attempts=data.get("retry_attempts"),
            security=security,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert ProxyProfile to dictionary.

        Returns:
            Dictionary representation of profile config
        """
        result: dict[str, Any] = {"server_url": self.server_url}

        if self.jwt_path is not None:
            result["jwt_path"] = self.jwt_path
        if self.ca_bundle_path is not None:
            result["ca_bundle_path"] = self.ca_bundle_path
        if self.timeout_seconds is not None:
            result["timeout_seconds"] = self.timeout_seconds
        if self.retry_attempts is not None:
            result["retry_attempts"] = self.retry_attempts
        if self.security is not None:
            result["security"] = self.security.to_dict()

        return result
