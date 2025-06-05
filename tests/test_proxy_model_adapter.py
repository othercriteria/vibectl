"""Tests for ProxyModelAdapter server-side alias resolution.

This module tests the ProxyModelAdapter's new server-side alias resolution
capabilities, replacing the previous hardcoded client-side approach.
"""

from unittest.mock import Mock, patch

import pytest

from vibectl.proxy_model_adapter import ProxyModelAdapter


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
        with patch.object(proxy_adapter, "_get_stub") as mock_stub:
            mock_response = Mock()
            mock_stub.return_value.GetServerInfo.return_value = mock_response

            # First call should fetch from server
            result1 = proxy_adapter._get_server_info()
            assert result1 == mock_response
            assert mock_stub.return_value.GetServerInfo.call_count == 1

            # Second call within TTL should use cache
            mock_time.return_value = 200.0  # Still within 300s TTL
            result2 = proxy_adapter._get_server_info()
            assert result2 == mock_response
            # No additional call
            assert mock_stub.return_value.GetServerInfo.call_count == 1

            # Third call after TTL should fetch again
            mock_time.return_value = 500.0  # Beyond 300s TTL
            result3 = proxy_adapter._get_server_info()
            assert result3 == mock_response
            # Additional call
            assert mock_stub.return_value.GetServerInfo.call_count == 2

    def test_server_info_force_refresh(self, proxy_adapter: ProxyModelAdapter) -> None:
        """Test that force_refresh bypasses cache."""
        with patch.object(proxy_adapter, "_get_stub") as mock_stub:
            mock_response = Mock()
            mock_stub.return_value.GetServerInfo.return_value = mock_response

            # First call to populate cache
            proxy_adapter._get_server_info()
            assert mock_stub.return_value.GetServerInfo.call_count == 1

            # Force refresh should bypass cache
            proxy_adapter._get_server_info(force_refresh=True)
            assert mock_stub.return_value.GetServerInfo.call_count == 2

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
        # Test global mapping resolution logging
        proxy_adapter._resolve_model_alias_from_server(
            "claude-4-sonnet", mock_server_info
        )
        mock_logger.debug.assert_called_with(
            "Resolved alias '%s' to '%s' using server mappings",
            "claude-4-sonnet",
            "anthropic/claude-sonnet-4-0",
        )

        # Test model-specific alias logging
        mock_logger.debug.reset_mock()
        mock_server_info.model_aliases = {}  # Remove global mappings
        proxy_adapter._resolve_model_alias_from_server("claude-4", mock_server_info)
        mock_logger.debug.assert_called_with(
            "Resolved alias '%s' to '%s' using model-specific aliases",
            "claude-4",
            "anthropic/claude-sonnet-4-0",
        )

    def test_legacy_fallback_minimal_mappings(
        self, proxy_adapter: ProxyModelAdapter
    ) -> None:
        """Test that legacy fallback only includes essential mappings."""
        available_models = [
            "anthropic/claude-sonnet-4-0",
            "anthropic/claude-3-5-sonnet-latest",
            "anthropic/claude-3-opus-latest",
        ]

        # Test that only essential mappings are available
        result = proxy_adapter._resolve_model_alias_legacy_fallback(
            "claude-4-sonnet", available_models
        )
        assert result == "anthropic/claude-sonnet-4-0"

        result = proxy_adapter._resolve_model_alias_legacy_fallback(
            "claude-3.5-sonnet", available_models
        )
        assert result == "anthropic/claude-3-5-sonnet-latest"

        result = proxy_adapter._resolve_model_alias_legacy_fallback(
            "claude-3-opus", available_models
        )
        assert result == "anthropic/claude-3-opus-latest"

        # Test that non-essential mappings are not available
        result = proxy_adapter._resolve_model_alias_legacy_fallback(
            "claude-3.7-sonnet", available_models
        )
        assert result is None

        result = proxy_adapter._resolve_model_alias_legacy_fallback(
            "gpt-4", available_models
        )
        assert result is None
