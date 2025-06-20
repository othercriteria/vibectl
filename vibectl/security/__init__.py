"""
Security module for vibectl proxy hardening.

This module provides client-side security protections for vibectl when using
proxy servers in semi-trusted environments.
"""

from .audit import AuditLogger
from .config import SecurityConfig
from .response_validation import (
    ValidationOutcome,
    ValidationResult,
    validate_action,
)
from .sanitizer import DetectedSecret, RequestSanitizer

__all__ = [
    "AuditLogger",
    "DetectedSecret",
    "RequestSanitizer",
    "SecurityConfig",
    "ValidationOutcome",
    "ValidationResult",
    "validate_action",
]
