"""Tests that GetServerInfo populates ServerLimits from configuration."""

from unittest.mock import Mock, patch

import vibectl.proto.llm_proxy_pb2
from vibectl.server.llm_proxy import LLMProxyServicer


@patch("llm.get_models")
def test_get_server_info_limits_population(mock_get_models: Mock) -> None:
    # Mock the llm.get_models call to prevent AsyncMock issues
    mock_model = Mock()
    mock_model.model_id = "test-model"
    mock_model.display_name = "Test Model"
    mock_model.provider = "test-provider"
    mock_get_models.return_value = [mock_model]

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

    # Create a proper mock context
    mock_context = Mock()

    # Also mock the get_models_with_aliases call that might be causing issues
    with patch("llm.get_models_with_aliases", return_value=[]):
        resp = servicer.GetServerInfo(req, mock_context)

    limits = resp.limits
    assert limits.max_requests_per_minute == 123
    assert limits.max_concurrent_requests == 7
    assert limits.max_input_length == 2048
    assert limits.request_timeout_seconds == 30
