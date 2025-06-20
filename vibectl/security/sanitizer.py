"""
Request sanitization for proxy hardening.

This module detects and removes sensitive information from requests before
sending them to proxy servers.
"""

import base64
import re
from dataclasses import dataclass

from vibectl.logutil import logger

from .config import SecurityConfig


@dataclass
class DetectedSecret:
    """Information about a detected secret in a request."""

    secret_type: str
    start_pos: int
    end_pos: int
    original_text: str
    confidence: float  # 0.0 to 1.0

    @property
    def length(self) -> int:
        """Length of the original secret text."""
        return len(self.original_text)

    @property
    def redacted_value(self) -> str:
        """Generate appropriate redacted value based on secret type."""
        if self.secret_type == "certificate":
            return "[REDACTED-certificate-multiple-lines]"
        else:
            return f"[REDACTED-{self.secret_type}-{self.length}-chars]"


class RequestSanitizer:
    """Client-side request sanitization before proxy transmission."""

    def __init__(self, config: SecurityConfig | None = None):
        """Initialize request sanitizer.

        Args:
            config: Security configuration for sanitization behavior
        """
        self.config = config or SecurityConfig()
        self.enabled = self.config.sanitize_requests

        # Kubernetes secret patterns (in order of specificity)
        self.k8s_patterns = [
            # Bearer tokens (Authorization headers) - most specific
            re.compile(r"Bearer\s+([A-Za-z0-9._-]{20,})", re.IGNORECASE),
            # JWT tokens (three-part structure) - more specific than generic eyJ
            re.compile(r"eyJ[A-Za-z0-9._-]+\.[A-Za-z0-9._-]+\.[A-Za-z0-9._-]+"),
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

    def sanitize_request(self, request: str | None) -> tuple[str, list[DetectedSecret]]:
        """Sanitize request and return cleaned version + detected secrets.

        Args:
            request: The original request text (can be None)

        Returns:
            Tuple of (sanitized_request, detected_secrets)
        """
        # Handle None input
        if request is None:
            return "", []

        if not self.enabled:
            return request, []

        detected_secrets = []

        # Detect and redact Kubernetes secrets
        k8s_secrets = self._detect_k8s_secrets(request)
        detected_secrets.extend(k8s_secrets)

        # Detect and redact base64 secrets (with high confidence threshold)
        # Always run base64 detection, let the overlap removal handle duplicates
        base64_secrets = self._detect_base64_secrets(request)
        detected_secrets.extend(base64_secrets)

        # Detect and redact certificates
        cert_secrets = self._detect_certificates(request)
        detected_secrets.extend(cert_secrets)

        # Remove overlapping detections (keep the most specific one)
        detected_secrets = self._remove_overlapping_secrets(detected_secrets)

        # Apply redaction (process in reverse order to maintain positions)
        sanitized_text = request
        for secret in sorted(detected_secrets, key=lambda s: s.start_pos, reverse=True):
            sanitized_text = (
                sanitized_text[: secret.start_pos]
                + secret.redacted_value
                + sanitized_text[secret.end_pos :]
            )

        # Warn user if secrets were detected and warnings are enabled
        if detected_secrets and self.config.warn_sanitization:
            secret_types = [s.secret_type for s in detected_secrets]
            unique_types = list(
                dict.fromkeys(secret_types)
            )  # Preserve order, remove duplicates
            type_summary = ", ".join(unique_types)
            logger.warning(
                f"⚠️  Sanitized {len(detected_secrets)} secret(s) from request "
                f"({type_summary}). Use --no-sanitization-warnings to disable."
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

        # Keep track of already detected positions to avoid duplicates
        detected_positions: set[tuple[int, int]] = set()

        for pattern in self.k8s_patterns:
            for match in pattern.finditer(text):
                start_pos = match.start()
                end_pos = match.end()

                # Skip if this position is already covered
                if any(
                    start_pos >= dp[0] and end_pos <= dp[1] for dp in detected_positions
                ):
                    continue

                secret_value = match.group(0)
                # For Bearer tokens, get just the token part
                if match.groups():
                    secret_value = match.group(1)
                    # Adjust positions for Bearer token pattern
                    bearer_match = re.search(
                        r"Bearer\s+", match.group(0), re.IGNORECASE
                    )
                    if bearer_match:
                        start_pos = match.start() + bearer_match.end()

                secrets.append(
                    DetectedSecret(
                        secret_type="k8s-token",
                        start_pos=start_pos,
                        end_pos=end_pos,
                        original_text=secret_value,
                        confidence=0.95,  # Higher confidence for K8s tokens
                    )
                )

                detected_positions.add((start_pos, end_pos))

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
                # Try to decode as-is first, then with padding if needed
                try:
                    decoded = base64.b64decode(base64_text, validate=True)
                except Exception:
                    # Try adding padding if needed
                    padding_needed = 4 - (len(base64_text) % 4)
                    if padding_needed != 4:
                        padded_text = base64_text + ("=" * padding_needed)
                        decoded = base64.b64decode(padded_text, validate=True)
                    else:
                        raise

                # Skip if decoded content looks like regular text (low entropy)
                if self._is_likely_secret_data(decoded):
                    secrets.append(
                        DetectedSecret(
                            secret_type="base64-data",
                            start_pos=match.start(),
                            end_pos=match.end(),
                            original_text=base64_text,
                            confidence=0.8,  # Higher confidence for base64 secrets
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
                cert_text = match.group(0)
                secrets.append(
                    DetectedSecret(
                        secret_type="certificate",
                        start_pos=match.start(),
                        end_pos=match.end(),
                        original_text=cert_text,
                        confidence=0.95,
                    )
                )

        return secrets

    def _remove_overlapping_secrets(
        self, secrets: list[DetectedSecret]
    ) -> list[DetectedSecret]:
        """Remove overlapping secret detections, keeping the most specific ones.

        Args:
            secrets: List of detected secrets

        Returns:
            List of non-overlapping secrets
        """
        if not secrets:
            return secrets

        # Sort by start position
        sorted_secrets = sorted(secrets, key=lambda s: (s.start_pos, s.end_pos))

        # Remove overlaps
        filtered_secrets: list[DetectedSecret] = []
        for secret in sorted_secrets:
            # Check if this secret overlaps with any already filtered secret
            overlaps = False
            for existing in filtered_secrets:
                if (
                    secret.start_pos < existing.end_pos
                    and secret.end_pos > existing.start_pos
                ):
                    # There's an overlap; keep the more specific one (higher confidence)
                    if secret.confidence > existing.confidence:
                        # Remove the existing one and add this one
                        filtered_secrets.remove(existing)
                        filtered_secrets.append(secret)
                    overlaps = True
                    break

            if not overlaps:
                filtered_secrets.append(secret)

        return filtered_secrets

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

            # Skip very common low-entropy patterns (but not all test patterns)
            if text.lower() in ["hello", "world", "example", "test123", "password"]:
                return False

            # Check for repeated characters (low entropy)
            if len(set(text)) < 3:  # Very few unique characters
                return False

            # Count unique characters as a simple entropy measure
            unique_chars = len(set(text))
            entropy_ratio = unique_chars / len(text) if text else 0

            # Look for secret-like patterns
            has_mixed_case = any(c.isupper() for c in text) and any(
                c.islower() for c in text
            )
            has_special_chars = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in text)
            has_hyphens = "-" in text  # Common in secret strings

            # More permissive detection for potential secrets
            # Either good entropy OR secret-like patterns OR longer strings
            # with some complexity
            return (
                entropy_ratio > 0.4
                or has_mixed_case
                or has_special_chars
                or has_hyphens
                or (len(text) > 15 and entropy_ratio > 0.3)
            )

        except Exception:
            # Binary data that doesn't decode - likely secret
            return True
