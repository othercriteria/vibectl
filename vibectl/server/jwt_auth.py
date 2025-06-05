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

import jwt
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


def load_config_from_server(
    server_config: dict[str, Any] | None = None,
) -> JWTConfig:
    """Load JWT configuration from server config with environment variable precedence.

    This follows the same precedence pattern as API keys:
    1. Environment variables (highest precedence)
    2. Environment variable key file
    3. Config file settings
    4. Config file key file
    5. Generate new key (lowest precedence)

    Args:
        server_config: Optional server configuration dict. If None, loads
                       from default location.

    Returns:
        JWTConfig: Configuration object with values from config system
    """
    from pathlib import Path

    # Load server config if not provided
    if server_config is None:
        from .main import load_server_config

        server_config = load_server_config()

    # Get JWT section from config
    jwt_config = server_config.get("jwt", {})

    # 1. Check environment variable override (highest precedence)
    secret_key = os.environ.get("VIBECTL_JWT_SECRET")

    # 2. Check environment variable key file
    if not secret_key:
        env_key_file = os.environ.get("VIBECTL_JWT_SECRET_FILE")
        if env_key_file:
            try:
                key_path = Path(env_key_file).expanduser()
                if key_path.exists():
                    secret_key = key_path.read_text().strip()
                    logger.info(
                        f"Loaded JWT secret from environment key file: {env_key_file}"
                    )
            except OSError as e:
                logger.warning(
                    "Failed to read JWT secret from environment "
                    f"key file {env_key_file}: {e}"
                )

    # 3. Check configured key
    if not secret_key:
        config_key = jwt_config.get("secret_key")
        if config_key:
            secret_key = str(config_key)
            logger.info("Using JWT secret from server configuration")

    # 4. Check configured key file
    if not secret_key:
        config_key_file = jwt_config.get("secret_key_file")
        if config_key_file:
            try:
                key_path = Path(config_key_file).expanduser()
                if key_path.exists():
                    secret_key = key_path.read_text().strip()
                    logger.info(
                        f"Loaded JWT secret from config key file: {config_key_file}"
                    )
            except OSError as e:
                logger.warning(
                    "Failed to read JWT secret from config "
                    f"key file {config_key_file}: {e}"
                )

    # 5. Generate new key if none found (lowest precedence)
    if not secret_key:
        secret_key = generate_secret_key()
        logger.warning(
            "No JWT secret key found in environment (VIBECTL_JWT_SECRET), "
            "environment file (VIBECTL_JWT_SECRET_FILE), or server config. "
            "Generated a new key for this session. For production, "
            "set a persistent key using one of these methods:\n"
            "  1. Environment: export VIBECTL_JWT_SECRET=your-key\n"
            "  2. Environment file: export VIBECTL_JWT_SECRET_FILE=path/to/key\n"
            "  3. Config: edit server config for jwt.secret_key\n"
            "  4. Config file: edit server config for jwt.secret_key_file"
        )

    # Get other settings with precedence: env vars -> config -> defaults
    algorithm = (
        os.environ.get("VIBECTL_JWT_ALGORITHM")
        or jwt_config.get("algorithm")
        or "HS256"
    )
    issuer = (
        os.environ.get("VIBECTL_JWT_ISSUER")
        or jwt_config.get("issuer")
        or "vibectl-server"
    )
    expiration_days = int(
        os.environ.get("VIBECTL_JWT_EXPIRATION_DAYS")
        or jwt_config.get("expiration_days")
        or 30
    )

    return JWTConfig(
        secret_key=secret_key,
        algorithm=algorithm,
        issuer=issuer,
        expiration_days=expiration_days,
    )


def load_config_with_generation(
    server_config: dict[str, Any] | None = None,
    persist_generated_key: bool = False,
) -> JWTConfig:
    """Load JWT configuration with optional key generation and persistence.

    This follows the same precedence pattern as load_config_from_server,
    but can optionally persist a generated key to the server config file.

    Args:
        server_config: Optional server configuration dict. If None, loads
                       from default location.
        persist_generated_key: If True and no key is found, generate one and
                              save it to the server config file.

    Returns:
        JWTConfig: Configuration object with values from config system
    """
    from pathlib import Path

    import yaml

    # Load server config if not provided
    if server_config is None:
        from .main import get_server_config_path, load_server_config

        server_config = load_server_config()
        config_path = get_server_config_path()
    else:
        config_path = None

    # Get JWT section from config
    jwt_config = server_config.get("jwt", {})

    # 1. Check environment variable override (highest precedence)
    secret_key = os.environ.get("VIBECTL_JWT_SECRET")

    # 2. Check environment variable key file
    if not secret_key:
        env_key_file = os.environ.get("VIBECTL_JWT_SECRET_FILE")
        if env_key_file:
            try:
                key_path = Path(env_key_file).expanduser()
                if key_path.exists():
                    secret_key = key_path.read_text().strip()
                    logger.info(
                        f"Loaded JWT secret from environment key file: {env_key_file}"
                    )
            except OSError as e:
                logger.warning(
                    "Failed to read JWT secret from environment "
                    f"key file {env_key_file}: {e}"
                )

    # 3. Check configured key
    if not secret_key:
        config_key = jwt_config.get("secret_key")
        if config_key:
            secret_key = str(config_key)
            logger.info("Using JWT secret from server configuration")

    # 4. Check configured key file
    if not secret_key:
        config_key_file = jwt_config.get("secret_key_file")
        if config_key_file:
            try:
                key_path = Path(config_key_file).expanduser()
                if key_path.exists():
                    secret_key = key_path.read_text().strip()
                    logger.info(
                        f"Loaded JWT secret from config key file: {config_key_file}"
                    )
            except OSError as e:
                logger.warning(
                    "Failed to read JWT secret from config "
                    f"key file {config_key_file}: {e}"
                )

    # 5. Generate new key if none found (with optional persistence)
    if not secret_key:
        secret_key = generate_secret_key()

        if persist_generated_key and config_path:
            try:
                # Ensure JWT section exists in config
                if "jwt" not in server_config:
                    server_config["jwt"] = {}

                # Update the server config with the generated key
                server_config["jwt"]["secret_key"] = secret_key

                # Write back to config file
                with open(config_path, "w") as f:
                    yaml.dump(server_config, f, default_flow_style=False)

                logger.info(
                    f"Generated and saved new JWT secret key to {config_path}. "
                    "This key will be reused for future token generations."
                )
            except Exception as e:
                logger.error(
                    f"Failed to save generated JWT secret to config file "
                    f"{config_path}: {e}. "
                    "Using temporary key for this session only."
                )
        else:
            logger.warning(
                "No JWT secret key found in environment (VIBECTL_JWT_SECRET), "
                "environment file (VIBECTL_JWT_SECRET_FILE), or server config. "
                "Generated a new key for this session. For production, "
                "set a persistent key using one of these methods:\n"
                "  1. Environment: export VIBECTL_JWT_SECRET=your-key\n"
                "  2. Environment file: export VIBECTL_JWT_SECRET_FILE=path/to/key\n"
                "  3. Config: edit server config for jwt.secret_key\n"
                "  4. Config file: edit server config for jwt.secret_key_file"
            )

    # Get other settings with precedence: env vars -> config -> defaults
    algorithm = (
        os.environ.get("VIBECTL_JWT_ALGORITHM")
        or jwt_config.get("algorithm")
        or "HS256"
    )
    issuer = (
        os.environ.get("VIBECTL_JWT_ISSUER")
        or jwt_config.get("issuer")
        or "vibectl-server"
    )
    expiration_days = int(
        os.environ.get("VIBECTL_JWT_EXPIRATION_DAYS")
        or jwt_config.get("expiration_days")
        or 30
    )

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
    """Create a JWT manager with configuration from server config.

    Returns:
        JWTAuthManager: Configured JWT manager
    """
    config = load_config_from_server()
    return JWTAuthManager(config)
