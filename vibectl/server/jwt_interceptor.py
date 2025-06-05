"""
gRPC interceptor for JWT authentication.

This module provides JWT authentication middleware for gRPC services.
"""

from collections.abc import Callable
from typing import Any

import grpc
import jwt

from vibectl.logutil import logger

from .jwt_auth import JWTAuthManager, load_config_from_server


class JWTAuthInterceptor(grpc.ServerInterceptor):  # type: ignore
    """gRPC server interceptor for JWT authentication."""

    def __init__(self, jwt_manager: JWTAuthManager, enabled: bool = True):
        """Initialize the JWT authentication interceptor.

        Args:
            jwt_manager: JWT authentication manager instance
            enabled: Whether authentication is enabled (default: True)
        """
        self.jwt_manager = jwt_manager
        self.enabled = enabled
        self.exempt_methods: set[str] = set()
        # Methods that don't require authentication (if any)
        # Currently all methods require auth when enabled
        logger.info(f"JWT authentication interceptor initialized (enabled: {enabled})")

    def intercept_service(
        self,
        continuation: Callable[..., Any],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> Any:
        """Intercept gRPC service calls for authentication.

        Args:
            continuation: The next handler in the chain
            handler_call_details: Details about the current call

        Returns:
            The result of the next handler or an authentication error
        """
        # If authentication is disabled, pass through
        if not self.enabled:
            return continuation(handler_call_details)

        # Check if this method is exempt from authentication
        method_name = handler_call_details.method
        if method_name in self.exempt_methods:
            logger.debug(f"Method {method_name} is exempt from authentication")
            return continuation(handler_call_details)

        # Extract metadata from the request
        metadata = dict(handler_call_details.invocation_metadata)

        # Look for authorization header
        auth_header = metadata.get("authorization")
        if not auth_header:
            logger.warning(f"Missing authorization header for method {method_name}")
            return self._create_unauthenticated_response()

        # Extract JWT token from Bearer header
        try:
            # Convert bytes to string if needed and ensure we have a string
            auth_header_str: str
            if isinstance(auth_header, bytes):
                auth_header_str = auth_header.decode("utf-8")
            else:
                auth_header_str = str(auth_header)

            if not auth_header_str.startswith("Bearer "):
                logger.warning(f"Invalid authorization header format for {method_name}")
                return self._create_unauthenticated_response()

            token = auth_header_str[7:]  # Remove "Bearer " prefix

            # Validate the token
            claims = self.jwt_manager.validate_token(token)
            logger.debug(f"Authenticated request for subject: {claims.get('sub')}")

            # Authentication successful, proceed to the next handler
            return continuation(handler_call_details)

        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT token for method {method_name}: {e}")
            return self._create_unauthenticated_response()
        except Exception as e:
            logger.error(f"Authentication error for method {method_name}: {e}")
            return self._create_authentication_error_response()

    def _create_unauthenticated_response(self) -> Any:
        """Create a gRPC response for unauthenticated requests.

        Returns:
            gRPC error response indicating authentication required
        """

        def unauthenticated_handler(request: Any, context: Any) -> Any:
            context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "Authentication required. Please provide a valid JWT token "
                "in the authorization header: 'Bearer <token>'",
            )

        return grpc.unary_unary_rpc_method_handler(unauthenticated_handler)

    def _create_authentication_error_response(self) -> Any:
        """Create a gRPC response for authentication errors.

        Returns:
            gRPC error response indicating authentication failure
        """

        def auth_error_handler(request: Any, context: Any) -> Any:
            context.abort(
                grpc.StatusCode.INTERNAL,
                "Authentication service error. Please try again later.",
            )

        return grpc.unary_unary_rpc_method_handler(auth_error_handler)


def create_jwt_interceptor(
    jwt_manager: JWTAuthManager | None = None, enabled: bool = True
) -> JWTAuthInterceptor:
    """Create a JWT authentication interceptor.

    Args:
        jwt_manager: JWT manager instance. If None, creates a default one.
        enabled: Whether authentication should be enabled

    Returns:
        Configured JWT authentication interceptor
    """
    if jwt_manager is None:
        config = load_config_from_server()
        jwt_manager = JWTAuthManager(config)

    return JWTAuthInterceptor(jwt_manager, enabled)
