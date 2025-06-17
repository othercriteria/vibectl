"""
Security module for vibectl proxy hardening.

This module provides client-side security protections for vibectl when using
proxy servers in semi-trusted environments.
"""

from .config import SecurityConfig
from .sanitizer import DetectedSecret, RequestSanitizer

__all__ = ["DetectedSecret", "RequestSanitizer", "SecurityConfig"]
