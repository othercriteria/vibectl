"""
JWT authentication utilities for the vibectl LLM proxy server.

This module provides JWT token generation and verification for secure
proxy authentication with configurable expiration and cryptographic signing.
"""

import datetime
import os
import secrets
import uuid
from typing import Any

import jwt  # type: ignore
from pydantic import BaseModel

from vibectl.logutil import logger


class JWTConfig(BaseModel):
    """Configuration for JWT authentication."""

    secret_key: str
    algorithm: str = "HS256"
    issuer: str = "vibectl-server"
    expiration_days: int = 30


def generate_secret_key() -> str:
    """Generate a secure random secret key for JWT signing.

    Returns:
        str: A URL-safe base64-encoded secret key
    """
    # Generate 32 bytes (256 bits) of random data and encode as base64
    return secrets.token_urlsafe(32)


def load_jwt_config_from_env() -> JWTConfig:
    """Load JWT configuration from environment variables.

    Returns:
        JWTConfig: Configuration object with values from environment
    """
    secret_key = os.environ.get("VIBECTL_JWT_SECRET")

    if not secret_key:
        # Generate a new key for this session
        secret_key = generate_secret_key()
        logger.warning(
            "No JWT secret key found in environment (VIBECTL_JWT_SECRET). "
            "Generated a new key for this session. For production, "
            "set a persistent key."
        )

    algorithm = os.environ.get("VIBECTL_JWT_ALGORITHM", "HS256")
    issuer = os.environ.get("VIBECTL_JWT_ISSUER", "vibectl-server")
    expiration_days = int(os.environ.get("VIBECTL_JWT_EXPIRATION_DAYS", "30"))

    return JWTConfig(
        secret_key=secret_key,
        algorithm=algorithm,
        issuer=issuer,
        expiration_days=expiration_days,
    )


class JWTAuthManager:
    """Manages JWT token generation and validation."""

    def __init__(self, config: JWTConfig):
        """Initialize the JWT manager.

        Args:
            config: JWT configuration
        """
        self.config = config
        logger.info(f"JWT Auth Manager initialized with issuer: {config.issuer}")

    def generate_token(self, subject: str, expiration_days: int | None = None) -> str:
        """Generate a JWT token for the given subject.

        Args:
            subject: Subject identifier (e.g., username or client ID)
            expiration_days: Token expiration in days (overrides config default)

        Returns:
            str: Encoded JWT token
        """
        if expiration_days is None:
            expiration_days = self.config.expiration_days

        # Calculate expiration time
        now = datetime.datetime.now(datetime.UTC)
        expiration = now + datetime.timedelta(days=expiration_days)

        # Create JWT payload
        payload = {
            "sub": subject,  # Subject
            "iss": self.config.issuer,  # Issuer
            "iat": now,  # Issued at
            "exp": expiration,  # Expiration
            "jti": str(uuid.uuid4()),  # JWT ID (unique identifier)
        }

        # Generate and return the token
        token: str = jwt.encode(
            payload, self.config.secret_key, algorithm=self.config.algorithm
        )

        logger.info(
            f"Generated JWT token for subject '{subject}' "
            f"(expires: {expiration.isoformat()})"
        )

        return token

    def validate_token(self, token: str) -> dict[str, Any]:
        """Validate a JWT token and return its payload.

        Args:
            token: JWT token to validate

        Returns:
            dict: Token payload if valid

        Raises:
            jwt.InvalidTokenError: If token is invalid, expired, or malformed
        """
        try:
            # Decode and validate the token
            payload: dict[str, Any] = jwt.decode(
                token,
                self.config.secret_key,
                algorithms=[self.config.algorithm],
                issuer=self.config.issuer,
            )

            logger.debug(
                f"Successfully validated JWT token for subject: {payload.get('sub')}"
            )
            return payload

        except jwt.ExpiredSignatureError:
            logger.warning("JWT token has expired")
            raise jwt.InvalidTokenError("Token has expired") from None
        except jwt.InvalidIssuerError:
            logger.warning("JWT token has invalid issuer")
            raise jwt.InvalidTokenError("Invalid token issuer") from None
        except jwt.InvalidSignatureError:
            logger.warning("JWT token has invalid signature")
            raise jwt.InvalidTokenError("Invalid token signature") from None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT token: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error validating JWT token: {e}")
            raise jwt.InvalidTokenError(f"Token validation failed: {e}") from e

    def get_token_subject(self, token: str) -> str | None:
        """Get the subject from a JWT token without full validation.

        This method extracts the subject claim without verifying the signature.
        Use only for logging or debugging purposes.

        Args:
            token: JWT token

        Returns:
            str | None: Subject if present, None otherwise
        """
        try:
            # Decode without verification for inspection
            payload: dict[str, Any] = jwt.decode(
                token, options={"verify_signature": False}
            )
            return payload.get("sub")
        except Exception as e:
            logger.debug(f"Failed to extract subject from token: {e}")
            return None


def create_jwt_manager() -> JWTAuthManager:
    """Create a JWT manager with configuration from environment.

    Returns:
        JWTAuthManager: Configured JWT manager
    """
    config = load_jwt_config_from_env()
    return JWTAuthManager(config)
