"""Tests that the gRPC HSTS interceptor attaches the Strict-Transport-Security
trailer to unary responses when TLS + HSTS are enabled.

The strategy is to:
1. Patch ``grpc.server`` so we can capture the list of interceptors that
   ``GRPCServer.start()`` registers without having to spin up a real gRPC
   server or generate certificates.
2. Patch out the TLS helper functions & ``grpc.ssl_server_credentials`` so the
   start-up path succeeds quickly in-process.
3. Execute the interceptor with a dummy unary handler and assert that
   ``context.set_trailing_metadata`` is invoked with the expected header.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, Mock

import grpc
import pytest

from vibectl.server.grpc_server import GRPCServer, _build_hsts_header


@pytest.mark.asyncio
async def test_grpc_hsts_interceptor_adds_trailer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Interceptor should append the configured HSTS header as a trailer."""

    # ------------------------------------------------------------------
    # 1.  Capture interceptors when GRPCServer.start() calls grpc.server()
    # ------------------------------------------------------------------
    captured_interceptors: list[grpc.ServerInterceptor] = []

    def fake_grpc_server(*args: Any, **kwargs: Any) -> Mock:
        captured_interceptors.extend(kwargs.get("interceptors", []))
        server_mock = Mock()
        server_mock.add_secure_port = Mock(return_value=None)
        server_mock.start = Mock()
        return server_mock

    monkeypatch.setattr("vibectl.server.grpc_server.grpc.server", fake_grpc_server)

    # ------------------------------------------------------------------
    # 2.  Short-circuit TLS helpers so startup is side-effect-free
    # ------------------------------------------------------------------
    monkeypatch.setattr(
        "vibectl.server.grpc_server.ensure_certificate_exists", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "vibectl.server.grpc_server.load_certificate_credentials",
        lambda *a, **k: (b"cert", b"key"),
    )
    monkeypatch.setattr(
        "vibectl.server.grpc_server.grpc.ssl_server_credentials", lambda *a, **k: Mock()
    )

    # Avoid pulling in the full service implementation during this unit test
    monkeypatch.setattr(
        "vibectl.server.grpc_server.add_VibectlLLMProxyServicer_to_server",
        lambda *a, **k: None,
    )

    # ------------------------------------------------------------------
    # 3.  Start a GRPCServer with TLS + HSTS enabled (cert helpers are patched)
    # ------------------------------------------------------------------
    hsts_settings = {"enabled": True, "max_age": 1234, "include_subdomains": True}

    server = GRPCServer(
        host="127.0.0.1",
        port=0,
        use_tls=True,
        hsts_settings=hsts_settings,
    )
    server.start()  # Interceptor list is captured via fake_grpc_server

    # There should be exactly one custom HSTS interceptor in the captured list
    [interceptor] = [
        i for i in captured_interceptors if i.__class__.__name__ == "_HSTSInterceptor"
    ]

    # ------------------------------------------------------------------
    # 4.  Execute the interceptor against a dummy unary RPC handler
    # ------------------------------------------------------------------
    header_value = _build_hsts_header(hsts_settings)

    def dummy_unary(request: Any, context: grpc.ServicerContext) -> str:
        return "OK"

    # Real RpcMethodHandler object wrapping our func
    dummy_handler = grpc.unary_unary_rpc_method_handler(dummy_unary)

    # Continuation simply returns the dummy handler
    def continuation(details: grpc.HandlerCallDetails) -> grpc.RpcMethodHandler:
        return dummy_handler

    # Intercept to obtain new handler
    new_handler = interceptor.intercept_service(continuation, Mock())
    assert new_handler is not None and new_handler.unary_unary is not None

    # Prepare a fake context with ``set_trailing_metadata``
    context = MagicMock(spec=grpc.ServicerContext)

    # Call through the wrapped handler
    response = new_handler.unary_unary(None, context)
    assert response == "OK"

    # Validate HSTS trailer insertion
    context.set_trailing_metadata.assert_called_once_with(
        (("strict-transport-security", header_value),)
    )
