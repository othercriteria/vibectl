"""Tests for ProxyModelAdapter server-side alias resolution.

This module tests the ProxyModelAdapter's new server-side alias resolution
capabilities, replacing the previous hardcoded client-side approach.
"""

import asyncio
import uuid
from typing import Any
from unittest.mock import Mock, patch

import grpc
import pytest
from pydantic import BaseModel

from vibectl.proxy_model_adapter import (
    ProxyModelAdapter,
    ProxyModelWrapper,
    ProxyStreamingMetricsCollector,
)
from vibectl.types import Fragment, LLMMetrics, SystemFragments, UserFragments


class SampleResponseModel(BaseModel):
    """Sample response model for testing structured responses."""

    message: str
    code: int


@pytest.fixture
def mock_server_info() -> Mock:
    """Create a mock GetServerInfoResponse with alias mappings."""
    mock_response = Mock()

    # Mock available models
    mock_model1 = Mock()
    mock_model1.model_id = "anthropic/claude-sonnet-4-0"
    mock_model1.aliases = ["claude-4-sonnet", "claude-4"]

    mock_model2 = Mock()
    mock_model2.model_id = "anthropic/claude-3-5-sonnet-latest"
    mock_model2.aliases = ["claude-3.5-sonnet", "claude-3.5"]

    mock_model3 = Mock()
    mock_model3.model_id = "gpt-4o"
    mock_model3.aliases = []

    mock_model4 = Mock()
    mock_model4.model_id = "anthropic/claude-3-opus-latest"
    mock_model4.aliases = ["claude-3-opus"]

    mock_response.available_models = [
        mock_model1,
        mock_model2,
        mock_model3,
        mock_model4,
    ]

    # Mock global alias mappings
    mock_response.model_aliases = {
        "claude-4-sonnet": "anthropic/claude-sonnet-4-0",
        "claude-3.5-sonnet": "anthropic/claude-3-5-sonnet-latest",
        "gpt-4": "gpt-4o",
    }

    return mock_response


@pytest.fixture
def proxy_adapter() -> ProxyModelAdapter:
    """Create a ProxyModelAdapter instance for testing."""
    return ProxyModelAdapter(host="localhost", port=50051, use_tls=False)


@pytest.fixture
def proxy_adapter_with_auth() -> ProxyModelAdapter:
    """Create a ProxyModelAdapter instance with JWT authentication for testing."""
    return ProxyModelAdapter(
        host="localhost", port=50051, use_tls=True, jwt_token="test-jwt-token"
    )


@pytest.fixture
def mock_grpc_stub() -> Mock:
    """Create a mock gRPC stub for testing."""
    return Mock()


@pytest.fixture
def mock_llm_metrics() -> LLMMetrics:
    """Create a mock LLMMetrics object for testing."""
    return LLMMetrics(
        token_input=100,
        token_output=50,
        latency_ms=250.0,
        total_processing_duration_ms=2500.0,
        call_count=1,
        cost_usd=0.0075,
    )


@pytest.fixture
def mock_pb_metrics() -> Mock:
    """Create a mock protobuf metrics object for testing."""
    mock_metrics = Mock()
    mock_metrics.HasField.side_effect = lambda field: field in [
        "input_tokens",
        "output_tokens",
        "cost_usd",
    ]
    mock_metrics.input_tokens = 100
    mock_metrics.output_tokens = 50
    mock_metrics.duration_ms = 250.0
    mock_metrics.cost_usd = 0.0075
    return mock_metrics


def create_system_fragments(items: list[str]) -> SystemFragments:
    """Helper to create SystemFragments with proper types."""
    return SystemFragments([Fragment(item) for item in items])


def create_user_fragments(items: list[str]) -> UserFragments:
    """Helper to create UserFragments with proper types."""
    return UserFragments([Fragment(item) for item in items])


class TestProxyModelWrapper:
    """Test the ProxyModelWrapper class."""

    def test_proxy_model_wrapper_creation(
        self, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test ProxyModelWrapper creation and basic properties."""
        wrapper = ProxyModelWrapper("test-model", proxy_adapter)

        assert wrapper.model_name == "test-model"
        assert wrapper.model_id == "test-model"
        assert wrapper.adapter == proxy_adapter

    def test_proxy_model_wrapper_string_representation(
        self, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test ProxyModelWrapper string representations."""
        wrapper = ProxyModelWrapper("test-model", proxy_adapter)

        assert str(wrapper) == "ProxyModel(test-model)"
        assert repr(wrapper) == "ProxyModelWrapper(model_name='test-model')"


class TestProxyStreamingMetricsCollector:
    """Test the ProxyStreamingMetricsCollector class."""

    def test_streaming_metrics_collector_initialization(self) -> None:
        """Test metrics collector initialization."""
        collector = ProxyStreamingMetricsCollector("test-request-id")

        assert collector.request_id == "test-request-id"
        assert not collector.completed
        assert collector._metrics is None

    async def test_streaming_metrics_collector_lifecycle(
        self, mock_llm_metrics: LLMMetrics
    ) -> None:
        """Test complete metrics collector lifecycle."""
        collector = ProxyStreamingMetricsCollector("test-request-id")

        # Initially no metrics
        metrics = await collector.get_metrics()
        assert metrics is None
        assert not collector.completed

        # Set final metrics
        collector.set_final_metrics(mock_llm_metrics)
        assert collector.completed

        # Get final metrics
        final_metrics = await collector.get_metrics()
        assert final_metrics == mock_llm_metrics


class TestProxyModelAdapterInitialization:
    """Test ProxyModelAdapter initialization and basic setup."""

    @patch("vibectl.proxy_model_adapter.logger")
    def test_adapter_initialization_defaults(self, mock_logger: Mock) -> None:
        """Test adapter initialization with default values."""
        adapter = ProxyModelAdapter()

        assert adapter.host == "localhost"
        assert adapter.port == 50051
        assert adapter.use_tls is True
        assert adapter.jwt_token is None
        assert adapter.channel is None
        assert adapter.stub is None
        assert len(adapter._model_cache) == 0
        assert adapter._server_info_cache is None

        mock_logger.debug.assert_called_once()

    @patch("vibectl.proxy_model_adapter.logger")
    def test_adapter_initialization_with_auth(self, mock_logger: Mock) -> None:
        """Test ProxyModelAdapter initialization with authentication."""
        adapter = ProxyModelAdapter(
            host="proxy.example.com", port=9443, use_tls=True, jwt_token="test-token"
        )

        assert adapter.host == "proxy.example.com"
        assert adapter.port == 9443
        assert adapter.use_tls is True
        assert adapter.jwt_token == "test-token"

        # Check that initialization was logged correctly
        mock_logger.debug.assert_called_once()
        log_call_args = mock_logger.debug.call_args[0]
        assert (
            log_call_args[0]
            == "ProxyModelAdapter initialized for %s:%d (TLS: %s, Auth: %s)"
        )
        assert log_call_args[1] == "proxy.example.com"
        assert log_call_args[2] == 9443
        assert log_call_args[3] is True  # use_tls
        assert log_call_args[4] == "enabled"  # auth status

    def test_get_metadata_without_auth(self, proxy_adapter: ProxyModelAdapter) -> None:
        """Test metadata generation without authentication."""
        metadata = proxy_adapter._get_metadata()
        assert metadata == []

    def test_get_metadata_with_auth(
        self, proxy_adapter_with_auth: ProxyModelAdapter
    ) -> None:
        """Test metadata generation with JWT authentication."""
        metadata = proxy_adapter_with_auth._get_metadata()
        assert len(metadata) == 1
        assert metadata[0] == ("authorization", "Bearer test-jwt-token")


class TestProxyModelAdapterConnection:
    """Test ProxyModelAdapter gRPC connection handling."""

    @patch("vibectl.proxy_model_adapter.grpc.insecure_channel")
    @patch("vibectl.proxy_model_adapter.logger")
    def test_get_channel_insecure(
        self,
        mock_logger: Mock,
        mock_insecure_channel: Mock,
        proxy_adapter: ProxyModelAdapter,
    ) -> None:
        """Test creating insecure gRPC channel."""
        mock_channel = Mock()
        mock_insecure_channel.return_value = mock_channel

        channel = proxy_adapter._get_channel()

        assert channel == mock_channel
        assert proxy_adapter.channel == mock_channel
        assert proxy_adapter.stub is not None

        mock_insecure_channel.assert_called_once_with("localhost:50051")
        mock_logger.debug.assert_called()

    @patch("vibectl.proxy_model_adapter.grpc.secure_channel")
    @patch("vibectl.proxy_model_adapter.grpc.ssl_channel_credentials")
    @patch("vibectl.proxy_model_adapter.logger")
    def test_get_channel_secure(
        self,
        mock_logger: Mock,
        mock_ssl_creds: Mock,
        mock_secure_channel: Mock,
        proxy_adapter_with_auth: ProxyModelAdapter,
    ) -> None:
        """Test creating secure gRPC channel."""
        mock_channel = Mock()
        mock_creds = Mock()
        mock_secure_channel.return_value = mock_channel
        mock_ssl_creds.return_value = mock_creds

        channel = proxy_adapter_with_auth._get_channel()

        assert channel == mock_channel
        assert proxy_adapter_with_auth.channel == mock_channel
        assert proxy_adapter_with_auth.stub is not None

        mock_ssl_creds.assert_called_once()
        mock_secure_channel.assert_called_once_with("localhost:50051", mock_creds)
        mock_logger.debug.assert_called()

    def test_get_channel_reuses_existing(
        self, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test that get_channel reuses existing channel."""
        # Set up existing channel and stub
        mock_channel = Mock()
        mock_stub = Mock()
        proxy_adapter.channel = mock_channel
        proxy_adapter.stub = mock_stub

        channel = proxy_adapter._get_channel()

        assert channel == mock_channel
        assert proxy_adapter.stub == mock_stub

    def test_get_stub_creates_channel_if_needed(
        self, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test that get_stub creates channel if not exists."""
        with patch.object(proxy_adapter, "_get_channel") as mock_get_channel:
            mock_channel = Mock()
            mock_get_channel.return_value = mock_channel
            proxy_adapter.stub = Mock()  # Set stub after channel creation

            stub = proxy_adapter._get_stub()

            mock_get_channel.assert_called_once()
            assert stub == proxy_adapter.stub

    def test_get_stub_raises_if_no_stub(self, proxy_adapter: ProxyModelAdapter) -> None:
        """Test that get_stub raises error if stub creation fails."""
        with patch.object(proxy_adapter, "_get_channel"):
            proxy_adapter.stub = None

            with pytest.raises(RuntimeError, match="Failed to create gRPC stub"):
                proxy_adapter._get_stub()


class TestProxyModelAdapterAliasResolution:
    """Test server-side alias resolution in ProxyModelAdapter."""

    def test_resolve_alias_using_global_mappings(
        self, proxy_adapter: ProxyModelAdapter, mock_server_info: Mock
    ) -> None:
        """Test alias resolution using global server alias mappings."""
        result = proxy_adapter._resolve_model_alias_from_server(
            "claude-4-sonnet", mock_server_info
        )
        assert result == "anthropic/claude-sonnet-4-0"

    def test_resolve_alias_using_model_specific_aliases(
        self, proxy_adapter: ProxyModelAdapter, mock_server_info: Mock
    ) -> None:
        """Test alias resolution using model-specific aliases."""
        # Remove global mapping to test model-specific resolution
        mock_server_info.model_aliases = {}

        result = proxy_adapter._resolve_model_alias_from_server(
            "claude-4", mock_server_info
        )
        assert result == "anthropic/claude-sonnet-4-0"

    def test_resolve_alias_using_legacy_fallback(
        self, proxy_adapter: ProxyModelAdapter, mock_server_info: Mock
    ) -> None:
        """Test alias resolution using legacy fallback when server doesn't
        provide aliases."""
        # Remove both global and model-specific aliases
        mock_server_info.model_aliases = {}
        for model in mock_server_info.available_models:
            model.aliases = []

        result = proxy_adapter._resolve_model_alias_from_server(
            "claude-3-opus", mock_server_info
        )
        assert result == "anthropic/claude-3-opus-latest"

    def test_alias_resolution_no_match(
        self, proxy_adapter: ProxyModelAdapter, mock_server_info: Mock
    ) -> None:
        """Test alias resolution when no match is found."""
        result = proxy_adapter._resolve_model_alias_from_server(
            "nonexistent-model", mock_server_info
        )
        assert result is None

    def test_direct_model_name_not_resolved(
        self, proxy_adapter: ProxyModelAdapter, mock_server_info: Mock
    ) -> None:
        """Test that direct model names don't need resolution."""
        # This should not be called for direct model names, but test behavior
        result = proxy_adapter._resolve_model_alias_from_server(
            "gpt-4o", mock_server_info
        )
        # Should return None since gpt-4o is available directly and doesn't
        # need alias resolution
        assert result is None

    @patch("vibectl.proxy_model_adapter.time.monotonic")
    def test_server_info_caching(
        self, mock_time: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test that server info is cached properly."""
        mock_time.return_value = 100.0

        # Mock the gRPC call
        mock_response = Mock()
        mock_response.server_version = "0.6.2"  # Provide actual string version

        with patch.object(proxy_adapter, "_get_stub") as mock_get_stub:
            mock_stub = Mock()
            mock_stub.GetServerInfo.return_value = mock_response
            mock_get_stub.return_value = mock_stub

            # First call should fetch from server
            result1 = proxy_adapter._get_server_info()
            assert result1 == mock_response
            assert mock_stub.GetServerInfo.call_count == 1

            # Second call within cache TTL should use cache
            mock_time.return_value = 110.0  # Within 300s TTL
            result2 = proxy_adapter._get_server_info()
            assert result2 == mock_response
            assert mock_stub.GetServerInfo.call_count == 1  # No additional call

            # Third call after cache expiry should fetch again
            mock_time.return_value = 500.0  # Beyond 300s TTL
            result3 = proxy_adapter._get_server_info()
            assert result3 == mock_response
            assert mock_stub.GetServerInfo.call_count == 2  # Additional call

    def test_server_info_force_refresh(self, proxy_adapter: ProxyModelAdapter) -> None:
        """Test that force_refresh bypasses cache."""
        mock_response = Mock()
        mock_response.server_version = "0.6.2"  # Provide actual string version

        with patch.object(proxy_adapter, "_get_stub") as mock_get_stub:
            mock_stub = Mock()
            mock_stub.GetServerInfo.return_value = mock_response
            mock_get_stub.return_value = mock_stub

            # First call to populate cache
            proxy_adapter._get_server_info()
            assert mock_stub.GetServerInfo.call_count == 1

            # Force refresh should bypass cache
            proxy_adapter._get_server_info(force_refresh=True)
            assert mock_stub.GetServerInfo.call_count == 2

    def test_server_info_grpc_error_with_cache(
        self, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test server info handling when gRPC error occurs but cache exists."""
        # Set up cached data with stale cache time
        mock_cached_response = Mock()
        proxy_adapter._server_info_cache = mock_cached_response
        # Set cache time to old value so cache is considered stale/expired
        import time

        proxy_adapter._server_info_cache_time = (
            time.monotonic() - proxy_adapter._server_info_cache_ttl - 1
        )

        with patch.object(proxy_adapter, "_get_stub") as mock_get_stub:
            mock_stub = Mock()

            # Create a real gRPC error that can be raised
            class TestRpcError(grpc.RpcError):
                def code(self) -> grpc.StatusCode:
                    return grpc.StatusCode.UNAVAILABLE

                def details(self) -> str:
                    return "Connection failed"

            mock_stub.GetServerInfo.side_effect = TestRpcError()
            mock_get_stub.return_value = mock_stub

            with patch("vibectl.proxy_model_adapter.logger") as mock_logger:
                result = proxy_adapter._get_server_info()

                assert result == mock_cached_response
                mock_logger.warning.assert_called_once_with(
                    "Using stale cached server info due to communication error"
                )

    def test_server_info_grpc_error_without_cache(
        self, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test server info handling when gRPC error occurs and no cache exists."""
        with patch.object(proxy_adapter, "_get_stub") as mock_get_stub:
            mock_stub = Mock()

            # Create a real gRPC error that can be raised
            class TestRpcError(grpc.RpcError):
                def code(self) -> grpc.StatusCode:
                    return grpc.StatusCode.UNAVAILABLE

                def details(self) -> str:
                    return "Connection failed"

            mock_stub.GetServerInfo.side_effect = TestRpcError()
            mock_get_stub.return_value = mock_stub

            with pytest.raises(grpc.RpcError):
                proxy_adapter._get_server_info()

    def test_refresh_server_info_clears_model_cache(
        self, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test that refreshing server info clears the model cache."""
        # Add something to model cache
        mock_model = Mock()
        proxy_adapter._model_cache["test-model"] = mock_model

        with patch.object(proxy_adapter, "_get_server_info") as mock_get_info:
            proxy_adapter.refresh_server_info()

            # Verify model cache was cleared
            assert len(proxy_adapter._model_cache) == 0
            mock_get_info.assert_called_once_with(force_refresh=True)

    def test_close_clears_caches(self, proxy_adapter: ProxyModelAdapter) -> None:
        """Test that close() clears all caches."""
        # Set up some cached data
        proxy_adapter._model_cache["test"] = Mock()
        proxy_adapter._server_info_cache = Mock()
        proxy_adapter._server_info_cache_time = 123.0

        proxy_adapter.close()

        # Verify caches were cleared
        assert len(proxy_adapter._model_cache) == 0
        assert proxy_adapter._server_info_cache is None
        assert proxy_adapter._server_info_cache_time == 0.0

    @patch("vibectl.proxy_model_adapter.logger")
    def test_logging_for_alias_resolution(
        self,
        mock_logger: Mock,
        proxy_adapter: ProxyModelAdapter,
        mock_server_info: Mock,
    ) -> None:
        """Test that alias resolution logs appropriately."""
        proxy_adapter._resolve_model_alias_from_server(
            "claude-4-sonnet", mock_server_info
        )
        # Verify that debug logging happened
        mock_logger.debug.assert_called()

    def test_legacy_fallback_minimal_mappings(
        self, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test legacy alias fallback with minimal available models."""
        available_models = ["anthropic/claude-3-opus-latest", "gpt-4o"]

        # Test exact match
        result = proxy_adapter._resolve_model_alias_legacy_fallback(
            "claude-3-opus", available_models
        )
        assert result == "anthropic/claude-3-opus-latest"

        # Test no match
        result = proxy_adapter._resolve_model_alias_legacy_fallback(
            "nonexistent", available_models
        )
        assert result is None


class TestProxyModelAdapterGetModelErrorHandling:
    """Test error handling in ProxyModelAdapter.get_model()."""

    @patch("vibectl.proxy_model_adapter.logger")
    def test_get_model_invalid_model_raises_value_error(
        self,
        mock_logger: Mock,
        proxy_adapter: ProxyModelAdapter,
        mock_server_info: Mock,
    ) -> None:
        """Test that get_model raises ValueError for invalid model names."""
        with (
            patch.object(
                proxy_adapter, "_get_server_info", return_value=mock_server_info
            ),
            pytest.raises(
                ValueError, match="Model 'invalid-model' not available on proxy server"
            ),
        ):
            proxy_adapter.get_model("invalid-model")

    @patch("vibectl.proxy_model_adapter.logger")
    def test_get_model_grpc_error_raises_value_error(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test that get_model handles gRPC errors correctly."""
        grpc_error = grpc.RpcError()
        with (
            patch.object(proxy_adapter, "_get_stub", side_effect=grpc_error),
            pytest.raises(ValueError, match="Failed to connect to proxy server"),
        ):
            proxy_adapter.get_model("test-model")

    @patch("vibectl.proxy_model_adapter.logger")
    def test_get_model_general_exception_raises_value_error(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test that get_model handles general exceptions correctly."""
        with (
            patch.object(
                proxy_adapter, "_get_server_info", side_effect=Exception("Test error")
            ),
            pytest.raises(ValueError, match="Failed to get model 'test-model'"),
        ):
            proxy_adapter.get_model("test-model")


class TestProxyModelAdapterMetricsConversion:
    """Test metrics conversion in ProxyModelAdapter."""

    def test_convert_metrics_with_valid_data(
        self, proxy_adapter: ProxyModelAdapter, mock_pb_metrics: Mock
    ) -> None:
        """Test _convert_metrics with valid protobuf metrics."""
        result = proxy_adapter._convert_metrics(mock_pb_metrics)

        assert result is not None
        assert result.token_input == 100
        assert result.token_output == 50
        assert result.latency_ms == 250.0
        assert result.total_processing_duration_ms == 250.0
        assert result.call_count == 1
        assert result.cost_usd == 0.0075

    def test_convert_metrics_with_none_returns_none(
        self, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test _convert_metrics returns None when input is None."""
        result = proxy_adapter._convert_metrics(None)
        assert result is None

    def test_convert_metrics_with_missing_fields(
        self, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test _convert_metrics with missing optional fields."""
        mock_metrics = Mock()
        mock_metrics.HasField.side_effect = lambda field: field == "input_tokens"
        mock_metrics.input_tokens = 50
        mock_metrics.duration_ms = 300.0

        result = proxy_adapter._convert_metrics(mock_metrics)

        assert result is not None
        assert result.token_input == 50
        assert result.token_output == 0  # Default for missing field
        assert result.latency_ms == 300.0
        assert result.cost_usd is None  # Default for missing cost


class TestProxyModelAdapterExecuteRequest:
    """Test execute request creation in ProxyModelAdapter."""

    @patch("vibectl.proxy_model_adapter.llm_proxy_pb2")
    @patch("vibectl.proxy_model_adapter.uuid.uuid4")
    def test_create_execute_request_basic(
        self, mock_uuid: Mock, mock_pb2: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test _create_execute_request with basic parameters."""
        mock_uuid.return_value = uuid.UUID("12345678-1234-5678-9012-123456789012")
        mock_request = Mock()
        mock_pb2.ExecuteRequest.return_value = mock_request

        model = ProxyModelWrapper("test-model", proxy_adapter)
        system_fragments = create_system_fragments(["You are a helpful assistant"])
        user_fragments = create_user_fragments(["Hello", "world"])

        result = proxy_adapter._create_execute_request(
            model, system_fragments, user_fragments
        )

        assert result == mock_request
        mock_request.request_id = "12345678-1234-5678-9012-123456789012"
        mock_request.model_name = "test-model"
        mock_request.system_fragments.extend.assert_called_once_with(system_fragments)
        mock_request.user_fragments.extend.assert_called_once_with(user_fragments)

    @patch("vibectl.proxy_model_adapter.llm_proxy_pb2")
    @patch("vibectl.proxy_model_adapter.logger")
    def test_create_execute_request_with_response_model(
        self, mock_logger: Mock, mock_pb2: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test _create_execute_request with response model schema."""
        mock_request = Mock()
        mock_pb2.ExecuteRequest.return_value = mock_request

        model = ProxyModelWrapper("test-model", proxy_adapter)

        result = proxy_adapter._create_execute_request(
            model,
            create_system_fragments([]),
            create_user_fragments([]),
            SampleResponseModel,
        )

        assert result == mock_request
        # Verify that response_model_schema was set with JSON schema
        assert hasattr(mock_request, "response_model_schema")

    @patch("vibectl.proxy_model_adapter.llm_proxy_pb2")
    @patch("vibectl.proxy_model_adapter.logger")
    def test_create_execute_request_invalid_model_type(
        self, mock_logger: Mock, mock_pb2: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test _create_execute_request with invalid model type."""
        with pytest.raises(ValueError, match="Expected ProxyModelWrapper"):
            proxy_adapter._create_execute_request(
                "invalid-model", create_system_fragments([]), create_user_fragments([])
            )

    @patch("vibectl.proxy_model_adapter.llm_proxy_pb2")
    @patch("vibectl.proxy_model_adapter.logger")
    def test_create_execute_request_response_model_serialization_error(
        self, mock_logger: Mock, mock_pb2: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test _create_execute_request handles response model serialization errors."""
        mock_request = Mock()
        mock_pb2.ExecuteRequest.return_value = mock_request

        # Create a mock response model that raises an error during schema generation
        mock_response_model = Mock()
        mock_response_model.model_json_schema.side_effect = Exception("Schema error")

        model = ProxyModelWrapper("test-model", proxy_adapter)

        # Should not raise exception, but should log warning
        result = proxy_adapter._create_execute_request(
            model,
            create_system_fragments([]),
            create_user_fragments([]),
            mock_response_model,
        )

        assert result == mock_request
        mock_logger.warning.assert_called_once()


class TestProxyModelAdapterExecute:
    """Test the execute method in ProxyModelAdapter."""

    @patch("vibectl.proxy_model_adapter.logger")
    async def test_execute_success(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter, mock_pb_metrics: Mock
    ) -> None:
        """Test successful execute call."""
        # Setup mocks
        mock_stub = Mock()
        mock_response = Mock()
        mock_success = Mock()
        mock_success.response_text = "Test response"
        mock_success.actual_model_used = "actual-model"
        mock_success.metrics = mock_pb_metrics
        mock_response.HasField.side_effect = lambda field: field == "success"
        mock_response.success = mock_success
        mock_response.request_id = "test-request-id"

        # Setup the execute method to return our mock response
        def mock_execute_call(request: Any, timeout: Any, metadata: Any) -> Any:
            return mock_response

        mock_stub.Execute = mock_execute_call

        with (
            patch.object(proxy_adapter, "_get_stub", return_value=mock_stub),
            patch.object(proxy_adapter, "_create_execute_request"),
            patch.object(proxy_adapter, "_get_metadata", return_value=[]),
        ):
            model = ProxyModelWrapper("test-model", proxy_adapter)

            result, metrics = await proxy_adapter.execute(
                model,
                create_system_fragments(["system"]),
                create_user_fragments(["user"]),
            )

            assert result == "Test response"
            assert metrics is not None
            assert metrics.token_input == 100

    @patch("vibectl.proxy_model_adapter.logger")
    async def test_execute_server_error(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test execute with server error response."""
        mock_stub = Mock()
        mock_response = Mock()
        mock_error = Mock()
        mock_error.error_code = "INTERNAL_ERROR"
        mock_error.error_message = "Server error"
        mock_error.HasField.side_effect = lambda field: field == "error_details"
        mock_error.error_details = "Additional details"
        mock_response.HasField.side_effect = lambda field: field == "error"
        mock_response.error = mock_error
        mock_response.request_id = "test-request-id"

        def mock_execute_call(request: Any, timeout: Any, metadata: Any) -> Any:
            return mock_response

        mock_stub.Execute = mock_execute_call

        with (
            patch.object(proxy_adapter, "_get_stub", return_value=mock_stub),
            patch.object(proxy_adapter, "_create_execute_request"),
            patch.object(proxy_adapter, "_get_metadata", return_value=[]),
        ):
            model = ProxyModelWrapper("test-model", proxy_adapter)

            with pytest.raises(
                ValueError,
                match="Proxy server error \\(INTERNAL_ERROR\\): "
                "Server error - Additional details",
            ):
                await proxy_adapter.execute(
                    model,
                    create_system_fragments(["system"]),
                    create_user_fragments(["user"]),
                )

    @patch("vibectl.proxy_model_adapter.logger")
    async def test_execute_invalid_response(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test execute with invalid response format."""
        mock_stub = Mock()
        mock_response = Mock()
        mock_response.HasField.return_value = False  # No success or error field

        def mock_execute_call(request: Any, timeout: Any, metadata: Any) -> Any:
            return mock_response

        mock_stub.Execute = mock_execute_call

        with (
            patch.object(proxy_adapter, "_get_stub", return_value=mock_stub),
            patch.object(proxy_adapter, "_create_execute_request"),
            patch.object(proxy_adapter, "_get_metadata", return_value=[]),
        ):
            model = ProxyModelWrapper("test-model", proxy_adapter)

            with pytest.raises(ValueError, match="Invalid response from proxy server"):
                await proxy_adapter.execute(
                    model,
                    create_system_fragments(["system"]),
                    create_user_fragments(["user"]),
                )

    @patch("vibectl.proxy_model_adapter.logger")
    async def test_execute_grpc_error(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test execute with gRPC error."""
        grpc_error = grpc.RpcError()

        with patch.object(proxy_adapter, "_get_stub", side_effect=grpc_error):
            model = ProxyModelWrapper("test-model", proxy_adapter)

            with pytest.raises(ValueError, match="Failed to execute request"):
                await proxy_adapter.execute(
                    model,
                    create_system_fragments(["system"]),
                    create_user_fragments(["user"]),
                )

    @patch("vibectl.proxy_model_adapter.logger")
    async def test_execute_general_exception(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test execute with general exception."""
        with patch.object(
            proxy_adapter, "_get_stub", side_effect=Exception("Test error")
        ):
            model = ProxyModelWrapper("test-model", proxy_adapter)

            with pytest.raises(ValueError, match="Proxy execution failed"):
                await proxy_adapter.execute(
                    model,
                    create_system_fragments(["system"]),
                    create_user_fragments(["user"]),
                )

    async def test_execute_and_log_metrics_delegates_to_execute(
        self, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test that execute_and_log_metrics delegates to execute."""
        model = ProxyModelWrapper("test-model", proxy_adapter)
        expected_result = ("response", None)

        with patch.object(
            proxy_adapter, "execute", return_value=expected_result
        ) as mock_execute:
            result = await proxy_adapter.execute_and_log_metrics(
                model,
                create_system_fragments(["system"]),
                create_user_fragments(["user"]),
                SampleResponseModel,
            )

            assert result == expected_result
            mock_execute.assert_called_once_with(
                model,
                create_system_fragments(["system"]),
                create_user_fragments(["user"]),
                SampleResponseModel,
            )


class TestProxyModelAdapterStreamExecute:
    """Test streaming execution methods in ProxyModelAdapter."""

    @patch("vibectl.proxy_model_adapter.logger")
    async def test_stream_execute_success(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test successful stream_execute call."""
        # Create mock chunks
        mock_chunk1 = Mock()
        mock_chunk1.HasField.side_effect = lambda field: field == "text_chunk"
        mock_chunk1.text_chunk = "Hello"

        mock_chunk2 = Mock()
        mock_chunk2.HasField.side_effect = lambda field: field == "text_chunk"
        mock_chunk2.text_chunk = " world"

        mock_complete = Mock()
        mock_complete.HasField.side_effect = lambda field: field == "complete"
        mock_complete.complete.actual_model_used = "actual-model"
        mock_complete.request_id = "test-request-id"

        mock_stream = [mock_chunk1, mock_chunk2, mock_complete]

        def mock_stream_execute_call(request: Any, timeout: Any, metadata: Any) -> Any:
            return iter(mock_stream)

        with patch.object(proxy_adapter, "_get_stub") as mock_get_stub:
            mock_stub = Mock()
            mock_stub.StreamExecute = mock_stream_execute_call
            mock_get_stub.return_value = mock_stub

            with (
                patch.object(proxy_adapter, "_create_execute_request"),
                patch.object(proxy_adapter, "_get_metadata", return_value=[]),
            ):
                model = ProxyModelWrapper("test-model", proxy_adapter)

                result_chunks = []
                async for chunk in proxy_adapter.stream_execute(
                    model,
                    create_system_fragments(["system"]),
                    create_user_fragments(["user"]),
                ):
                    result_chunks.append(chunk)

                assert result_chunks == ["Hello", " world"]

    @patch("vibectl.proxy_model_adapter.logger")
    async def test_stream_execute_server_error(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test stream_execute with server error."""
        mock_error_chunk = Mock()
        mock_error = Mock()
        mock_error.error_code = "INTERNAL_ERROR"
        mock_error.error_message = "Stream error"
        mock_error.HasField.side_effect = lambda field: field == "error_details"
        mock_error.error_details = "Stream details"
        mock_error_chunk.HasField.side_effect = lambda field: field == "error"
        mock_error_chunk.error = mock_error
        mock_error_chunk.request_id = "test-request-id"

        mock_stream = [mock_error_chunk]

        def mock_stream_execute_call(request: Any, timeout: Any, metadata: Any) -> Any:
            return iter(mock_stream)

        with patch.object(proxy_adapter, "_get_stub") as mock_get_stub:
            mock_stub = Mock()
            mock_stub.StreamExecute = mock_stream_execute_call
            mock_get_stub.return_value = mock_stub

            with (
                patch.object(proxy_adapter, "_create_execute_request"),
                patch.object(proxy_adapter, "_get_metadata", return_value=[]),
            ):
                model = ProxyModelWrapper("test-model", proxy_adapter)

                with pytest.raises(
                    ValueError,
                    match="Proxy server error \\(INTERNAL_ERROR\\): "
                    "Stream error - Stream details",
                ):
                    async for _ in proxy_adapter.stream_execute(
                        model,
                        create_system_fragments(["system"]),
                        create_user_fragments(["user"]),
                    ):
                        pass

    @patch("vibectl.proxy_model_adapter.logger")
    async def test_stream_execute_grpc_error(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test stream_execute with gRPC error."""
        grpc_error = grpc.RpcError()

        with patch.object(proxy_adapter, "_get_stub", side_effect=grpc_error):
            model = ProxyModelWrapper("test-model", proxy_adapter)

            with pytest.raises(ValueError, match="Failed to stream request"):
                async for _ in proxy_adapter.stream_execute(
                    model,
                    create_system_fragments(["system"]),
                    create_user_fragments(["user"]),
                ):
                    pass

    @patch("vibectl.proxy_model_adapter.logger")
    async def test_stream_execute_and_log_metrics_success(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter, mock_pb_metrics: Mock
    ) -> None:
        """Test successful stream_execute_and_log_metrics call."""
        # Create mock chunks including metrics
        mock_chunk1 = Mock()
        mock_chunk1.HasField.side_effect = lambda field: field == "text_chunk"
        mock_chunk1.text_chunk = "Hello"

        mock_metrics_chunk = Mock()
        mock_metrics_chunk.HasField.side_effect = lambda field: field == "final_metrics"
        mock_metrics_chunk.final_metrics = mock_pb_metrics

        mock_complete = Mock()
        mock_complete.HasField.side_effect = lambda field: field == "complete"
        mock_complete.complete.actual_model_used = "actual-model"
        mock_complete.request_id = "test-request-id"

        mock_stream = [mock_chunk1, mock_metrics_chunk, mock_complete]

        def mock_stream_execute_call(request: Any, timeout: Any, metadata: Any) -> Any:
            return iter(mock_stream)

        with patch.object(proxy_adapter, "_get_stub") as mock_get_stub:
            mock_stub = Mock()
            mock_stub.StreamExecute = mock_stream_execute_call
            mock_get_stub.return_value = mock_stub

            with patch.object(
                proxy_adapter, "_create_execute_request"
            ) as mock_create_req:
                mock_request = Mock()
                mock_request.request_id = "test-request-id"
                mock_create_req.return_value = mock_request

                with patch.object(proxy_adapter, "_get_metadata", return_value=[]):
                    model = ProxyModelWrapper("test-model", proxy_adapter)

                    (
                        iterator,
                        metrics_collector,
                    ) = await proxy_adapter.stream_execute_and_log_metrics(
                        model,
                        create_system_fragments(["system"]),
                        create_user_fragments(["user"]),
                    )

                    # Consume the iterator to trigger metrics processing
                    result_chunks = []
                    async for chunk in iterator:
                        result_chunks.append(chunk)

                    assert result_chunks == ["Hello"]
                    assert isinstance(metrics_collector, ProxyStreamingMetricsCollector)
                    assert metrics_collector.request_id == "test-request-id"
                    assert metrics_collector.is_completed

    @patch("vibectl.proxy_model_adapter.logger")
    async def test_stream_execute_and_log_metrics_grpc_error(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test stream_execute_and_log_metrics with gRPC error."""
        grpc_error = grpc.RpcError()

        with patch.object(proxy_adapter, "_get_stub", side_effect=grpc_error):
            model = ProxyModelWrapper("test-model", proxy_adapter)

            with pytest.raises(
                ValueError, match="Failed to stream request with metrics"
            ):
                await proxy_adapter.stream_execute_and_log_metrics(
                    model,
                    create_system_fragments(["system"]),
                    create_user_fragments(["user"]),
                )


class TestProxyModelAdapterAsyncStreamWrapper:
    """Test the async stream wrapper in ProxyModelAdapter."""

    async def test_async_stream_wrapper_success(
        self, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test _async_stream_wrapper with successful stream."""
        mock_items = ["item1", "item2", "item3"]

        # Create a simple iterable that yields the mock items
        mock_stream = iter(mock_items)

        # Use a more straightforward approach - mock just the executor call
        async def mock_run_in_executor(executor: Any, func: Any) -> Any:
            # Directly call the function to simulate the executor
            return func()

        with patch.object(asyncio, "get_event_loop") as mock_get_loop:
            mock_loop = Mock()
            mock_loop.run_in_executor.side_effect = mock_run_in_executor
            mock_get_loop.return_value = mock_loop

            result_items = []
            async for item in proxy_adapter._async_stream_wrapper(mock_stream):
                result_items.append(item)

            assert result_items == mock_items

    async def test_async_stream_wrapper_empty_stream(
        self, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test _async_stream_wrapper with empty stream."""
        mock_stream: list[str] = []

        # Use a more straightforward approach - mock just the executor call
        async def mock_run_in_executor(executor: Any, func: Any) -> Any:
            # Directly call the function to simulate the executor
            return func()

        with patch.object(asyncio, "get_event_loop") as mock_get_loop:
            mock_loop = Mock()
            mock_loop.run_in_executor.side_effect = mock_run_in_executor
            mock_get_loop.return_value = mock_loop

            result_items = []
            async for item in proxy_adapter._async_stream_wrapper(iter(mock_stream)):
                result_items.append(item)

            assert result_items == []


class TestProxyModelAdapterValidation:
    """Test validation methods in ProxyModelAdapter."""

    def test_validate_model_key_always_returns_none(
        self, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test that validate_model_key always returns None for proxy."""
        result = proxy_adapter.validate_model_key("any-model")
        assert result is None

    @patch("vibectl.proxy_model_adapter.logger")
    def test_validate_model_name_success(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test validate_model_name with valid model."""
        with patch.object(proxy_adapter, "get_model") as mock_get_model:
            mock_get_model.return_value = ProxyModelWrapper(
                "valid-model", proxy_adapter
            )

            result = proxy_adapter.validate_model_name("valid-model")
            assert result is None

    @patch("vibectl.proxy_model_adapter.logger")
    def test_validate_model_name_invalid_model(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test validate_model_name with invalid model."""
        with patch.object(
            proxy_adapter, "get_model", side_effect=ValueError("Model not found")
        ):
            result = proxy_adapter.validate_model_name("invalid-model")
            assert result == "Model not found"

    @patch("vibectl.proxy_model_adapter.logger")
    def test_validate_model_name_unexpected_error(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test validate_model_name with unexpected error."""
        with patch.object(
            proxy_adapter, "get_model", side_effect=Exception("Unexpected error")
        ):
            result = proxy_adapter.validate_model_name("test-model")
            assert result == "Validation error: Unexpected error"
            mock_logger.error.assert_called_once()


class TestProxyModelAdapterManagement:
    """Test management methods in ProxyModelAdapter."""

    @patch("vibectl.proxy_model_adapter.logger")
    def test_refresh_server_info_success(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test successful refresh_server_info."""
        # Add some items to the model cache
        proxy_adapter._model_cache["test-model"] = ProxyModelWrapper(
            "test-model", proxy_adapter
        )

        with patch.object(proxy_adapter, "_get_server_info") as mock_get_info:
            proxy_adapter.refresh_server_info()

            mock_get_info.assert_called_once_with(force_refresh=True)
            assert len(proxy_adapter._model_cache) == 0  # Cache should be cleared
            mock_logger.info.assert_called_once()

    @patch("vibectl.proxy_model_adapter.logger")
    def test_refresh_server_info_error(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test refresh_server_info with error."""
        with patch.object(
            proxy_adapter, "_get_server_info", side_effect=Exception("Server error")
        ):
            with pytest.raises(Exception, match="Server error"):
                proxy_adapter.refresh_server_info()

            mock_logger.error.assert_called_once()

    @patch("vibectl.proxy_model_adapter.logger")
    def test_close_cleans_up_resources(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test that close() cleans up all resources."""
        # Setup some state
        mock_channel = Mock()
        proxy_adapter.channel = mock_channel
        proxy_adapter.stub = Mock()
        proxy_adapter._model_cache["test"] = ProxyModelWrapper("test", proxy_adapter)
        proxy_adapter._server_info_cache = Mock()
        proxy_adapter._server_info_cache_time = 123.45

        proxy_adapter.close()

        # Verify cleanup
        mock_channel.close.assert_called_once()
        assert proxy_adapter.channel is None
        assert proxy_adapter.stub is None
        assert len(proxy_adapter._model_cache) == 0
        assert proxy_adapter._server_info_cache is None
        assert proxy_adapter._server_info_cache_time == 0.0

    def test_close_with_no_channel(self, proxy_adapter: ProxyModelAdapter) -> None:
        """Test close() when no channel exists."""
        # Should not raise exception
        proxy_adapter.close()

        assert proxy_adapter.channel is None
        assert proxy_adapter.stub is None


class TestProxyModelAdapterContextManager:
    """Test context manager functionality in ProxyModelAdapter."""

    def test_context_manager_enter_returns_self(
        self, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test that context manager entry returns the adapter itself."""
        with proxy_adapter as adapter:
            assert adapter is proxy_adapter

    @patch("vibectl.proxy_model_adapter.logger")
    def test_context_manager_exit_calls_close(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test that context manager exit calls close()."""
        with patch.object(proxy_adapter, "close") as mock_close:
            with proxy_adapter:
                pass  # Just enter and exit
            mock_close.assert_called_once()

    def test_context_manager_full_usage(self, proxy_adapter: ProxyModelAdapter) -> None:
        """Test context manager usage with resource setup and cleanup."""
        # This test ensures the context manager pattern works correctly
        assert proxy_adapter.channel is None

        with proxy_adapter as adapter:
            assert adapter is proxy_adapter
            # Context manager should work even without actual channel creation

        # After exiting, resources should be cleaned up if they existed
        assert proxy_adapter.channel is None


class TestProxyStreamingMetricsRegressionTests:
    """
    Tests for regression issues found in streaming metrics collection.

    Background: During development, some edge cases were discovered where
    metrics collection would fail or behave unexpectedly under certain
    streaming response patterns from the server.
    """

    @patch("vibectl.proxy_model_adapter.logger")
    async def test_streaming_metrics_collection_with_correct_chunk_order(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter, mock_pb_metrics: Mock
    ) -> None:
        """Test streaming with metrics arriving in expected order."""
        # Arrange
        proxy_adapter._model_cache["test-model"] = ProxyModelWrapper(
            "test-model", proxy_adapter
        )

        def mock_stream_execute_call(request: Any, timeout: Any, metadata: Any) -> Any:
            mock_chunk1 = Mock()
            mock_chunk1.text_chunk = "Hello"
            mock_chunk1.final_metrics = None
            mock_chunk1.error = None
            mock_chunk1.complete = None

            mock_chunk2 = Mock()
            mock_chunk2.text_chunk = " world"
            mock_chunk2.final_metrics = None
            mock_chunk2.error = None
            mock_chunk2.complete = None

            mock_chunk3 = Mock()
            mock_chunk3.text_chunk = ""
            mock_chunk3.final_metrics = mock_pb_metrics
            mock_chunk3.error = None
            mock_chunk3.complete = None

            mock_complete = Mock()
            mock_complete.text_chunk = ""
            mock_complete.final_metrics = None
            mock_complete.error = None
            mock_complete.complete = Mock()
            mock_complete.complete.actual_model_used = "test-model"

            return iter([mock_chunk1, mock_chunk2, mock_chunk3, mock_complete])

        with patch.object(proxy_adapter, "_get_stub") as mock_get_stub:
            mock_stub = Mock()
            mock_stub.StreamExecute.side_effect = mock_stream_execute_call
            mock_get_stub.return_value = mock_stub

            # Act
            result, collector = await proxy_adapter.stream_execute_and_log_metrics(
                proxy_adapter._model_cache["test-model"],
                create_system_fragments(["You are a helpful assistant."]),
                create_user_fragments(["Say hello."]),
            )

            # Collect all chunks
            chunks = []
            async for chunk in result:
                chunks.append(chunk)

            # Wait for metrics collection to complete
            final_metrics = await collector.get_metrics()

            # Assert
            assert chunks == ["Hello", " world"]
            assert final_metrics is not None
            assert final_metrics.token_input == 100
            assert final_metrics.token_output == 50

    @patch("vibectl.proxy_model_adapter.logger")
    async def test_streaming_metrics_collection_with_metrics_before_complete(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter, mock_pb_metrics: Mock
    ) -> None:
        """Test streaming with metrics arriving before complete marker."""
        # Arrange
        proxy_adapter._model_cache["test-model"] = ProxyModelWrapper(
            "test-model", proxy_adapter
        )

        def mock_stream_execute_call(request: Any, timeout: Any, metadata: Any) -> Any:
            mock_chunk1 = Mock()
            mock_chunk1.text_chunk = "Response"
            mock_chunk1.final_metrics = None
            mock_chunk1.error = None
            mock_chunk1.complete = None

            mock_metrics_chunk = Mock()
            mock_metrics_chunk.text_chunk = ""
            mock_metrics_chunk.final_metrics = mock_pb_metrics
            mock_metrics_chunk.error = None
            mock_metrics_chunk.complete = None

            mock_complete = Mock()
            mock_complete.text_chunk = ""
            mock_complete.final_metrics = None
            mock_complete.error = None
            mock_complete.complete = Mock()
            mock_complete.complete.actual_model_used = "test-model"

            return iter([mock_chunk1, mock_metrics_chunk, mock_complete])

        with patch.object(proxy_adapter, "_get_stub") as mock_get_stub:
            mock_stub = Mock()
            mock_stub.StreamExecute.side_effect = mock_stream_execute_call
            mock_get_stub.return_value = mock_stub

            # Act
            result, collector = await proxy_adapter.stream_execute_and_log_metrics(
                proxy_adapter._model_cache["test-model"],
                create_system_fragments(["You are a helpful assistant."]),
                create_user_fragments(["Say hello."]),
            )

            # Collect all chunks
            chunks = []
            async for chunk in result:
                chunks.append(chunk)

            # Wait for metrics collection to complete
            final_metrics = await collector.get_metrics()

            # Assert
            assert chunks == ["Response"]
            assert final_metrics is not None
            assert final_metrics.token_input == 100
            assert final_metrics.token_output == 50

    @patch("vibectl.proxy_model_adapter.logger")
    async def test_streaming_without_final_metrics_chunk(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test streaming response that doesn't include final metrics."""
        # Arrange
        proxy_adapter._model_cache["test-model"] = ProxyModelWrapper(
            "test-model", proxy_adapter
        )

        def mock_stream_execute_call(request: Any, timeout: Any, metadata: Any) -> Any:
            mock_chunk1 = Mock()
            mock_chunk1.text_chunk = "Hello"
            mock_chunk1.final_metrics = None
            mock_chunk1.error = None
            mock_chunk1.complete = None

            mock_chunk2 = Mock()
            mock_chunk2.text_chunk = " world"
            mock_chunk2.final_metrics = None
            mock_chunk2.error = None
            mock_chunk2.complete = None

            mock_complete = Mock()
            mock_complete.text_chunk = ""
            mock_complete.final_metrics = None
            mock_complete.error = None
            mock_complete.complete = Mock()
            mock_complete.complete.actual_model_used = "test-model"

            return iter([mock_chunk1, mock_chunk2, mock_complete])

        with patch.object(proxy_adapter, "_get_stub") as mock_get_stub:
            mock_stub = Mock()
            mock_stub.StreamExecute.side_effect = mock_stream_execute_call
            mock_get_stub.return_value = mock_stub

            # Act
            result, collector = await proxy_adapter.stream_execute_and_log_metrics(
                proxy_adapter._model_cache["test-model"],
                create_system_fragments(["You are a helpful assistant."]),
                create_user_fragments(["Say hello."]),
            )

            # Collect all chunks
            chunks = []
            async for chunk in result:
                chunks.append(chunk)

            # Wait for metrics (should be None since no metrics chunk was sent)
            final_metrics = await collector.get_metrics()

            # Assert
            assert chunks == ["Hello", " world"]
            assert final_metrics is None

    @patch("vibectl.proxy_model_adapter.logger")
    async def test_streaming_multiple_text_chunks_with_metrics(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter, mock_pb_metrics: Mock
    ) -> None:
        """Test streaming with multiple text chunks followed by metrics."""
        # Arrange
        proxy_adapter._model_cache["test-model"] = ProxyModelWrapper(
            "test-model", proxy_adapter
        )

        def mock_stream_execute_call(request: Any, timeout: Any, metadata: Any) -> Any:
            # Simulate a longer streaming response with multiple chunks
            chunks = []
            for _i, text in enumerate(["Hello", " there", " friend", "!"]):
                mock_chunk = Mock()
                mock_chunk.text_chunk = text
                mock_chunk.final_metrics = None
                mock_chunk.error = None
                mock_chunk.complete = None
                chunks.append(mock_chunk)

            # Add final metrics
            mock_metrics_chunk = Mock()
            mock_metrics_chunk.text_chunk = ""
            mock_metrics_chunk.final_metrics = mock_pb_metrics
            mock_metrics_chunk.error = None
            mock_metrics_chunk.complete = None
            chunks.append(mock_metrics_chunk)

            # Add completion marker
            mock_complete = Mock()
            mock_complete.text_chunk = ""
            mock_complete.final_metrics = None
            mock_complete.error = None
            mock_complete.complete = Mock()
            mock_complete.complete.actual_model_used = "test-model"
            chunks.append(mock_complete)

            return iter(chunks)

        with patch.object(proxy_adapter, "_get_stub") as mock_get_stub:
            mock_stub = Mock()
            mock_stub.StreamExecute.side_effect = mock_stream_execute_call
            mock_get_stub.return_value = mock_stub

            # Act
            result, collector = await proxy_adapter.stream_execute_and_log_metrics(
                proxy_adapter._model_cache["test-model"],
                create_system_fragments(["You are a helpful assistant."]),
                create_user_fragments(["Say hello."]),
            )

            # Collect all chunks
            chunks = []
            async for chunk in result:
                chunks.append(chunk)

            # Wait for metrics collection to complete
            final_metrics = await collector.get_metrics()

            # Assert
            assert chunks == ["Hello", " there", " friend", "!"]
            assert final_metrics is not None
            assert final_metrics.token_input == 100
            assert final_metrics.token_output == 50


class TestProxyModelAdapterVersionCompatibility:
    """Test version compatibility checking between client and server."""

    @patch("vibectl.proxy_model_adapter.logger")
    @patch("vibectl.proxy_model_adapter.__version__", "0.6.2")
    def test_version_match_no_warning(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test that matching versions don't produce warnings."""
        # Act
        proxy_adapter._check_version_compatibility("0.6.2")

        # Assert - no warning should be logged
        mock_logger.warning.assert_not_called()

    @patch("vibectl.proxy_model_adapter.logger")
    @patch("vibectl.proxy_model_adapter.__version__", "0.6.2")
    def test_version_skew_pre_1_0_0_warns(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test that version skew in pre-1.0.0 versions produces warnings."""
        # Act
        proxy_adapter._check_version_compatibility("0.6.1")

        # Assert
        mock_logger.warning.assert_called_once()
        warning_call = mock_logger.warning.call_args
        # Check the format string and arguments separately
        format_string = warning_call[0][0]
        args = warning_call[0][1:]
        assert "Version skew detected: client v%s, server v%s" in format_string
        assert "Pre-1.0.0 versions may have compatibility issues" in format_string
        assert args == ("0.6.2", "0.6.1")

    @patch("vibectl.proxy_model_adapter.logger")
    @patch("vibectl.proxy_model_adapter.__version__", "0.7.0")
    def test_version_skew_different_minor_pre_1_0_0(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test that different minor versions in pre-1.0.0 produce warnings."""
        # Act
        proxy_adapter._check_version_compatibility("0.6.5")

        # Assert
        mock_logger.warning.assert_called_once()
        warning_call = mock_logger.warning.call_args
        # Check the format string and arguments separately
        format_string = warning_call[0][0]
        args = warning_call[0][1:]
        assert "Version skew detected: client v%s, server v%s" in format_string
        assert args == ("0.7.0", "0.6.5")

    @patch("vibectl.proxy_model_adapter.logger")
    @patch("vibectl.proxy_model_adapter.__version__", "1.2.3")
    @patch("vibectl.proxy_model_adapter.check_version_compatibility")
    def test_version_skew_post_1_0_0_uses_semantic_versioning(
        self,
        mock_check_compat: Mock,
        mock_logger: Mock,
        proxy_adapter: ProxyModelAdapter,
    ) -> None:
        """Test that post-1.0.0 versions use semantic versioning compatibility check."""
        # Arrange
        mock_check_compat.return_value = (False, "Version mismatch")

        # Act
        proxy_adapter._check_version_compatibility("1.2.0")

        # Assert
        mock_check_compat.assert_called_once_with("1.2.3", "==1.2.0")
        mock_logger.warning.assert_called_once()
        warning_call = mock_logger.warning.call_args
        # Check the format string and arguments separately
        format_string = warning_call[0][0]
        args = warning_call[0][1:]
        assert (
            "Version difference detected: client v%s, server v%s. %s" in format_string
        )
        assert args == ("1.2.3", "1.2.0", "Version mismatch")

    @patch("vibectl.proxy_model_adapter.logger")
    @patch("vibectl.proxy_model_adapter.__version__", "1.2.3")
    @patch("vibectl.proxy_model_adapter.check_version_compatibility")
    def test_version_compatible_post_1_0_0_no_warning(
        self,
        mock_check_compat: Mock,
        mock_logger: Mock,
        proxy_adapter: ProxyModelAdapter,
    ) -> None:
        """Test that compatible post-1.0.0 versions don't produce warnings."""
        # Arrange
        mock_check_compat.return_value = (True, "")

        # Act
        proxy_adapter._check_version_compatibility("1.2.3")

        # Assert - when versions are identical, check_version_compatibility
        # is not called because the method exits early with no warnings
        mock_check_compat.assert_not_called()
        mock_logger.warning.assert_not_called()

    @patch("vibectl.proxy_model_adapter.logger")
    @patch("vibectl.proxy_model_adapter.__version__", "0.6.2")
    def test_version_parsing_error_handled_gracefully(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test that version parsing errors are handled gracefully."""
        # Act
        proxy_adapter._check_version_compatibility("invalid.version.format")

        # Assert
        mock_logger.warning.assert_called_once()
        warning_call = mock_logger.warning.call_args
        # Check the format string and arguments separately
        format_string = warning_call[0][0]
        args = warning_call[0][1:]
        assert (
            "Version format issue: client v%s, server v%s. Error: %s" in format_string
        )
        assert args[0] == "0.6.2"
        assert args[1] == "invalid.version.format"
        # args[2] will be the error message string, which varies by Python version

    @patch("vibectl.proxy_model_adapter.logger")
    @patch("vibectl.proxy_model_adapter.__version__", "0.6.2")
    def test_version_without_dots_handled(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test that server versions without dots are handled correctly."""
        # Act
        proxy_adapter._check_version_compatibility("1")

        # Assert
        mock_logger.warning.assert_called_once()
        warning_call = mock_logger.warning.call_args
        # Check the format string and arguments separately
        format_string = warning_call[0][0]
        args = warning_call[0][1:]
        assert "Version skew detected: client v%s, server v%s" in format_string
        assert args == ("0.6.2", "1")

    @patch("vibectl.proxy_model_adapter.logger")
    @patch("vibectl.proxy_model_adapter.__version__", "1.0.0")
    def test_client_1_0_0_server_pre_1_0_0_warns(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test warning when client is 1.0.0+ but server is pre-1.0.0."""
        # Act
        proxy_adapter._check_version_compatibility("0.9.0")

        # Assert
        mock_logger.warning.assert_called_once()
        warning_call = mock_logger.warning.call_args
        # Check the format string and arguments separately
        format_string = warning_call[0][0]
        args = warning_call[0][1:]
        assert "Version skew detected: client v%s, server v%s" in format_string
        assert "Pre-1.0.0 versions may have compatibility issues" in format_string
        assert args == ("1.0.0", "0.9.0")

    @patch("vibectl.proxy_model_adapter.logger")
    @patch("vibectl.proxy_model_adapter.__version__", "0.9.0")
    def test_client_pre_1_0_0_server_1_0_0_warns(
        self, mock_logger: Mock, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test warning when client is pre-1.0.0 but server is 1.0.0+."""
        # Act
        proxy_adapter._check_version_compatibility("1.0.0")

        # Assert
        mock_logger.warning.assert_called_once()
        warning_call = mock_logger.warning.call_args
        # Check the format string and arguments separately
        format_string = warning_call[0][0]
        args = warning_call[0][1:]
        assert "Version skew detected: client v%s, server v%s" in format_string
        assert "Pre-1.0.0 versions may have compatibility issues" in format_string
        assert args == ("0.9.0", "1.0.0")

    @patch("vibectl.proxy_model_adapter.logger")
    def test_version_check_called_in_get_server_info(
        self,
        mock_logger: Mock,
        proxy_adapter: ProxyModelAdapter,
        mock_server_info: Mock,
    ) -> None:
        """Test that version checking is integrated into the _get_server_info flow."""
        # Arrange
        mock_server_info.server_version = "0.6.1"

        with (
            patch.object(proxy_adapter, "_get_stub") as mock_get_stub,
            patch("vibectl.proxy_model_adapter.__version__", "0.6.2"),
        ):
            mock_stub = Mock()
            mock_stub.GetServerInfo.return_value = mock_server_info
            mock_get_stub.return_value = mock_stub

            # Act
            proxy_adapter._get_server_info()

            # Assert - version check should have been called and produced a warning
            mock_logger.warning.assert_called()
            warning_call = mock_logger.warning.call_args
            # Check the format string and arguments separately
            format_string = warning_call[0][0]
            args = warning_call[0][1:]
            assert "Version skew detected: client v%s, server v%s" in format_string
            assert args[0] == "0.6.2"
            assert args[1] == "0.6.1"
