from collections.abc import Callable
from typing import Any, cast
from unittest.mock import Mock

import grpc
import pytest

from vibectl.server.config import ServerConfig
from vibectl.server.limit_backend import InMemoryLimitBackend
from vibectl.server.rate_limit_interceptor import RateLimitInterceptor


@pytest.fixture
def server_config() -> ServerConfig:  # type: ignore[override]
    cfg = ServerConfig()
    # Patch load to avoid IO
    cfg._config_cache = {
        "server": {
            "limits": {
                "global": {
                    "max_requests_per_minute": 2,
                    "max_concurrent_requests": 1,
                },
                "per_token": {},
            }
        }
    }
    return cfg


def _make_handler() -> Callable[[Any, grpc.ServicerContext], str]:
    def _unary_unary(request: Any, context: grpc.ServicerContext) -> str:
        return "ok"

    return _unary_unary


def test_rpm_enforced(server_config: ServerConfig) -> None:
    backend = InMemoryLimitBackend()
    interceptor = RateLimitInterceptor(server_config, backend=backend)

    details = Mock(spec=grpc.HandlerCallDetails)
    details.method = "/svc/Test"
    details.invocation_metadata = []

    continuation = Mock(
        return_value=grpc.unary_unary_rpc_method_handler(_make_handler())
    )

    handler = interceptor.intercept_service(continuation, details)
    assert handler is not None
    handler = cast(grpc.RpcMethodHandler, handler)

    ctx = _make_context()
    # First call passes
    unary = cast(Callable[[Any, grpc.ServicerContext], Any], handler.unary_unary)
    assert unary(None, ctx) == "ok"  # type: ignore[arg-type]

    ctx2 = _make_context()
    # Second call passes (count=2)
    assert unary(None, ctx2) == "ok"  # type: ignore[arg-type]

    ctx3 = _make_context()
    with pytest.raises(grpc.RpcError):
        unary(None, ctx3)  # type: ignore[arg-type]


def test_concurrency_enforced(server_config: ServerConfig) -> None:
    backend = InMemoryLimitBackend()
    interceptor = RateLimitInterceptor(server_config, backend=backend)

    details = Mock(spec=grpc.HandlerCallDetails)
    details.method = "/svc/Test"
    details.invocation_metadata = []

    continuation = Mock(
        return_value=grpc.unary_unary_rpc_method_handler(_make_handler())
    )
    handler = interceptor.intercept_service(continuation, details)

    assert handler is not None
    handler = cast(grpc.RpcMethodHandler, handler)

    ctx1 = _make_context()
    ctx2 = _make_context()

    # First call acquires concurrency slot but we don't release until after return.
    unary2 = cast(Callable[[Any, grpc.ServicerContext], Any], handler.unary_unary)
    result = unary2(None, ctx1)  # type: ignore[arg-type]
    assert result == "ok"

    # Simulate still in-flight by NOT releasing; backend release occurs after
    # return already.
    # Fire second concurrent call quickly (limit=1 so should fail)
    backend.acquire_concurrency("global:conc", 1)  # manually take slot
    with pytest.raises(grpc.RpcError):
        unary2(None, ctx2)  # type: ignore[arg-type]


def _make_context(metadata: list | None = None) -> grpc.ServicerContext:  # type: ignore[override]
    """Return a mocked ServicerContext with optional invocation metadata."""

    ctx = Mock(spec=grpc.ServicerContext)

    ctx.invocation_metadata.return_value = metadata or []

    def _abort(code: grpc.StatusCode, details: str) -> None:
        raise grpc.RpcError()

    ctx.abort.side_effect = _abort
    ctx.set_trailing_metadata = Mock()
    return ctx


# ---------------------------------------------------------------------------
# Additional coverage: disabled interceptor & per-token overrides
# ---------------------------------------------------------------------------


def test_interceptor_disabled_pass_through(server_config: ServerConfig) -> None:
    """When `enabled=False`, interceptor should not perform any checks."""

    interceptor = RateLimitInterceptor(server_config, enabled=False)

    details = Mock(spec=grpc.HandlerCallDetails)
    details.method = "/svc/Test"
    details.invocation_metadata = []

    continuation_called: dict[str, bool] = {"called": False}

    def _continuation(hcd: grpc.HandlerCallDetails) -> grpc.RpcMethodHandler:
        continuation_called["called"] = True
        return grpc.unary_unary_rpc_method_handler(_make_handler())

    handler = interceptor.intercept_service(_continuation, details)
    assert continuation_called["called"] is True
    assert handler is not None


def test_per_token_override(server_config: ServerConfig) -> None:
    """Per-token limits should override global ones."""

    # Adjust config: extremely low per-token RPM=1
    cast(
        dict[str, Any],
        server_config._config_cache,
    )["server"]["limits"]["per_token"]["demo"] = {
        "max_requests_per_minute": 1,
        "max_concurrent_requests": 1,
    }

    backend = InMemoryLimitBackend()
    interceptor = RateLimitInterceptor(server_config, backend=backend)

    # Simulate metadata with subject header (as bytes to hit bytes→str branch)
    details = Mock(spec=grpc.HandlerCallDetails)
    details.method = "/svc/Test"
    details.invocation_metadata = [("x-vibectl-sub", b"demo")]

    continuation = Mock(
        return_value=grpc.unary_unary_rpc_method_handler(_make_handler())
    )
    handler = interceptor.intercept_service(continuation, details)
    assert handler is not None
    handler = cast(grpc.RpcMethodHandler, handler)

    # First request should succeed, second should hit RPM limit
    meta = [("x-vibectl-sub", b"demo")]
    ctx_ok = _make_context(meta)
    unary3 = cast(Callable[[Any, grpc.ServicerContext], Any], handler.unary_unary)
    assert unary3(None, ctx_ok) == "ok"  # type: ignore[arg-type]

    ctx_fail = _make_context(meta)
    with pytest.raises(grpc.RpcError):
        unary3(None, ctx_fail)  # type: ignore[arg-type]
