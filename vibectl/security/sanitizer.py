"""
Request sanitization for proxy hardening.

This module detects and removes sensitive information from requests before
sending them to proxy servers.
"""

import base64
import re
from dataclasses import dataclass

from .config import SecurityConfig


@dataclass
class DetectedSecret:
    """Information about a detected secret in a request."""

    secret_type: str
    start_pos: int
    end_pos: int
    redacted_value: str
    confidence: float  # 0.0 to 1.0


class RequestSanitizer:
    """Client-side request sanitization before proxy transmission."""

    def __init__(self, config: SecurityConfig | None = None):
        """Initialize request sanitizer.

        Args:
            config: Security configuration for sanitization behavior
        """
        self.config = config or SecurityConfig()
        self.enabled = self.config.sanitize_requests

        # Kubernetes secret patterns
        self.k8s_patterns = [
            # Bearer tokens (Authorization headers)
            re.compile(r"Bearer\s+([A-Za-z0-9._-]+)", re.IGNORECASE),
            # JWT tokens (basic pattern)
            re.compile(r"eyJ[A-Za-z0-9._-]+"),
            # Kubernetes service account tokens (file content patterns)
            re.compile(r"eyJhbGciOiJSUzI1NiIsImtpZCI6[A-Za-z0-9._-]+"),
            # API server URLs with embedded tokens
            re.compile(
                r"https://[^/]+/api/v1/.*\?.*token=([A-Za-z0-9._-]+)", re.IGNORECASE
            ),
        ]

        # Base64 pattern for potential secrets (must be selective)
        self.base64_pattern = re.compile(r"[A-Za-z0-9+/]{20,}={0,2}")

        # Certificate patterns
        self.cert_patterns = [
            re.compile(r"-----BEGIN [A-Z ]+-----.*?-----END [A-Z ]+-----", re.DOTALL),
        ]

    def sanitize_request(self, request: str) -> tuple[str, list[DetectedSecret]]:
        """Sanitize request and return cleaned version + detected secrets.

        Args:
            request: The original request text

        Returns:
            Tuple of (sanitized_request, detected_secrets)
        """
        if not self.enabled:
            return request, []

        detected_secrets = []
        sanitized_text = request

        # Detect and redact Kubernetes secrets
        k8s_secrets = self._detect_k8s_secrets(request)
        detected_secrets.extend(k8s_secrets)

        # Detect and redact base64 secrets (with high confidence threshold)
        base64_secrets = self._detect_base64_secrets(request)
        detected_secrets.extend(base64_secrets)

        # Detect and redact certificates
        cert_secrets = self._detect_certificates(request)
        detected_secrets.extend(cert_secrets)

        # Apply redaction (process in reverse order to maintain positions)
        for secret in sorted(detected_secrets, key=lambda s: s.start_pos, reverse=True):
            sanitized_text = (
                sanitized_text[: secret.start_pos]
                + secret.redacted_value
                + sanitized_text[secret.end_pos :]
            )

        return sanitized_text, detected_secrets

    def _detect_k8s_secrets(self, text: str) -> list[DetectedSecret]:
        """Detect Kubernetes-specific secret patterns.

        Args:
            text: Text to analyze

        Returns:
            List of detected Kubernetes secrets
        """
        secrets = []

        for pattern in self.k8s_patterns:
            for match in pattern.finditer(text):
                secret_value = match.group(0)
                # For Bearer tokens, get just the token part
                if match.groups():
                    secret_value = match.group(1)

                secrets.append(
                    DetectedSecret(
                        secret_type="k8s-token",
                        start_pos=match.start(),
                        end_pos=match.end(),
                        redacted_value=f"[REDACTED-K8S-TOKEN-{len(secret_value)}]",
                        confidence=0.9,
                    )
                )

        return secrets

    def _detect_base64_secrets(self, text: str) -> list[DetectedSecret]:
        """Detect base64 patterns that might be secrets.

        Args:
            text: Text to analyze

        Returns:
            List of detected base64 secrets with high confidence
        """
        secrets = []

        for match in self.base64_pattern.finditer(text):
            base64_text = match.group(0)

            # Skip if too short or looks like regular text
            if len(base64_text) < 20:
                continue

            # Try to decode to check if it's valid base64
            try:
                decoded = base64.b64decode(base64_text + "==", validate=True)
                # Skip if decoded content looks like regular text (low entropy)
                if self._is_likely_secret_data(decoded):
                    secrets.append(
                        DetectedSecret(
                            secret_type="base64-data",
                            start_pos=match.start(),
                            end_pos=match.end(),
                            redacted_value=f"[REDACTED-BASE64-{len(base64_text)}]",
                            confidence=0.7,
                        )
                    )
            except Exception:
                # Not valid base64, skip
                continue

        return secrets

    def _detect_certificates(self, text: str) -> list[DetectedSecret]:
        """Detect PEM certificate patterns.

        Args:
            text: Text to analyze

        Returns:
            List of detected certificate secrets
        """
        secrets = []

        for pattern in self.cert_patterns:
            for match in pattern.finditer(text):
                secrets.append(
                    DetectedSecret(
                        secret_type="certificate",
                        start_pos=match.start(),
                        end_pos=match.end(),
                        redacted_value="[REDACTED-CERTIFICATE]",
                        confidence=0.95,
                    )
                )

        return secrets

    def _is_likely_secret_data(self, data: bytes) -> bool:
        """Determine if decoded data is likely secret material.

        Args:
            data: Decoded binary data

        Returns:
            True if data appears to be secret material
        """
        # Skip if too short
        if len(data) < 10:
            return False

        # Check for high entropy (measure of randomness)
        # Secret data typically has higher entropy than regular text
        try:
            text = data.decode("utf-8", errors="ignore")

            # Count unique characters as a simple entropy measure
            unique_chars = len(set(text))
            entropy_ratio = unique_chars / len(text) if text else 0

            # High entropy suggests secret data
            return entropy_ratio > 0.6

        except Exception:
            # Binary data that doesn't decode - likely secret
            return True
