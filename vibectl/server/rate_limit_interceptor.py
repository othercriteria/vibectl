"""gRPC server interceptor for request rate limiting.

This MVP supports two dimensions:

* **Requests-per-minute (RPM)** - simple fixed 60-second window counter
* **Concurrent requests** - maximum in-flight RPC calls

Future work can extend the backend interface to sliding windows or token
quotas without touching this interceptor surface.
"""

from collections.abc import Callable
from typing import Any

import grpc

from vibectl.server.config import Limits, ServerConfig

from .limit_backend import InMemoryLimitBackend, LimitBackend


class RateLimitInterceptor(grpc.ServerInterceptor):
    """Server-side gRPC interceptor applying rate limits before calling servicers."""

    def __init__(
        self,
        server_config: ServerConfig,
        backend: LimitBackend | None = None,
        enabled: bool = True,
        subject_getter: Callable[[grpc.ServicerContext], str | None] | None = None,
    ) -> None:
        self._config = server_config
        self._backend = backend or InMemoryLimitBackend()
        self.enabled = enabled
        self._subject_getter = subject_getter or _default_subject_getter

    # --------------------------------------------------------------------- gRPC

    def intercept_service(
        self,
        continuation: Callable[[grpc.HandlerCallDetails], grpc.RpcMethodHandler | None],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler | None:
        if not self.enabled:
            return continuation(handler_call_details)

        handler = continuation(handler_call_details)
        if handler is None:
            return None

        # Wrap unary_unary for MVP. Other handler types can be added later.
        if handler.unary_unary:
            return grpc.unary_unary_rpc_method_handler(
                self._wrap_unary_unary(handler.unary_unary),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        return handler  # For non-unary handlers, fall through for now.

    # ----------------------------------------------------------------- helpers

    def _wrap_unary_unary(
        self,
        orig_handler: Callable[[Any, grpc.ServicerContext], Any],
    ) -> Callable[[Any, grpc.ServicerContext], Any]:
        """Closure capturing *self* and *orig_handler* for rate enforcement."""

        def _wrapped(request: Any, context: grpc.ServicerContext) -> Any:
            # Determine subject for per-token limits (falls back to global)
            token_sub = self._subject_getter(context)
            limits: Limits = self._config.get_limits(token_sub)

            # ---------------------------------------------------------------- RPM
            if limits.max_requests_per_minute is not None:
                rpm_key = f"{token_sub or 'global'}:rpm"
                current_rpm = self._backend.incr_fixed_window(rpm_key, 60, amount=1)
                if current_rpm > limits.max_requests_per_minute:
                    _abort_resource_exhausted(
                        context,
                        "rpm",
                        retry_after_ms=60_000,
                        message="Rate limit (RPM) exceeded",
                    )

            # --------------------------------------------------------- concurrency
            conc_key: str | None = None
            acquired_conc = False
            if limits.max_concurrent_requests is not None:
                conc_key = f"{token_sub or 'global'}:conc"
                acquired_conc = self._backend.acquire_concurrency(
                    conc_key, limits.max_concurrent_requests
                )
                if not acquired_conc:
                    _abort_resource_exhausted(
                        context,
                        "concurrency",
                        retry_after_ms=0,
                        message="Concurrent request limit exceeded",
                    )
            try:
                return orig_handler(request, context)
            finally:
                if acquired_conc and conc_key is not None:
                    self._backend.release_concurrency(conc_key)

        return _wrapped


# ------------------------------------------------------------------ utilities


def _default_subject_getter(context: grpc.ServicerContext) -> str | None:
    """Extract JWT *sub* added by JWTAuthInterceptor (if any)."""

    auth_ctx = context.invocation_metadata()
    # JWT interceptor stores subject in new metadata key for downstream usage
    for key, value in auth_ctx:
        if key == "x-vibectl-sub":
            if isinstance(value, bytes):
                try:
                    return value.decode()
                except Exception:  # pragma: no cover
                    return None
            return value
    return None


def _abort_resource_exhausted(
    context: grpc.ServicerContext,
    limit_type: str,
    *,
    retry_after_ms: int,
    message: str,
) -> None:
    """Convenience helper to abort request with RESOURCE_EXHAUSTED status."""

    context.set_trailing_metadata(
        (
            ("limit-type", limit_type),
            ("retry-after-ms", str(retry_after_ms)),
        )
    )
    context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, message)
