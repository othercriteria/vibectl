"""Tests that GetServerInfo populates ServerLimits from configuration."""

import vibectl.proto.llm_proxy_pb2
from vibectl.server.llm_proxy import LLMProxyServicer


def test_get_server_info_limits_population() -> None:
    cfg = {
        "server": {
            "limits": {
                "global": {
                    "max_requests_per_minute": 123,
                    "max_concurrent_requests": 7,
                    "max_input_length": 2048,
                    "request_timeout_seconds": 30,
                }
            }
        }
    }

    servicer = LLMProxyServicer(default_model=None, config=cfg)

    req = vibectl.proto.llm_proxy_pb2.GetServerInfoRequest()  # type: ignore[attr-defined]
    resp = servicer.GetServerInfo(req, None)  # type: ignore[arg-type]

    limits = resp.limits
    assert limits.max_requests_per_minute == 123
    assert limits.max_concurrent_requests == 7
    assert limits.max_input_length == 2048
    assert limits.request_timeout_seconds == 30
