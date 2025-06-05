"""
Tests for the LLM Proxy Server gRPC service implementation.

This module tests the LLMProxyServicer class including:
- Execute endpoint (non-streaming)
- StreamExecute endpoint (streaming)
- GetServerInfo endpoint
- Model resolution and validation
- Token usage metrics
- Error handling scenarios
"""

from typing import Any
from unittest.mock import Mock, patch

import pytest

from vibectl.proto import llm_proxy_pb2  # type: ignore[attr-defined]
from vibectl.server.llm_proxy import LLMProxyServicer


class TestLLMProxyServicerInitialization:
    """Test initialization of LLMProxyServicer."""

    def test_init_with_default_model(self) -> None:
        """Test LLMProxyServicer initialization with default model."""
        servicer = LLMProxyServicer(default_model="test-model")
        assert servicer.default_model == "test-model"
        assert servicer.config == {}

    def test_init_with_config(self) -> None:
        """Test LLMProxyServicer initialization with config."""
        config = {"model_aliases": {"alias1": "model1"}}
        servicer = LLMProxyServicer(config=config)
        assert servicer.default_model is None
        assert servicer.config == config

    def test_init_with_default_model_and_config(self) -> None:
        """Test LLMProxyServicer initialization with both default model and config."""
        config = {"model_aliases": {"alias1": "model1"}}
        servicer = LLMProxyServicer(default_model="test-model", config=config)
        assert servicer.default_model == "test-model"
        assert servicer.config == config


class TestLLMProxyServicerExecute:
    """Test the Execute method (non-streaming)."""

    @patch("vibectl.server.llm_proxy.llm")
    def test_execute_with_specified_model_success(self, mock_llm: Mock) -> None:
        """Test successful Execute with specified model."""
        # Arrange
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "Test response"
        mock_response.usage = {"prompt_tokens": 10, "completion_tokens": 20}
        mock_model.prompt.return_value = mock_response
        mock_llm.get_model.return_value = mock_model

        servicer = LLMProxyServicer()
        request = llm_proxy_pb2.ExecuteRequest(  # type: ignore[attr-defined]
            request_id="test-123",
            model_name="test-model",
            system_fragments=["System prompt"],
            user_fragments=["User prompt"],
        )
        context = Mock()

        # Act
        response = servicer.Execute(request, context)

        # Assert
        assert response.request_id == "test-123"
        assert response.success is not None
        assert response.success.response_text == "Test response"
        assert response.success.actual_model_used == "test-model"
        assert response.success.metrics.input_tokens == 10
        assert response.success.metrics.output_tokens == 20
        assert (
            response.success.metrics.duration_ms >= 0
        )  # Allow for very fast execution

        mock_llm.get_model.assert_called_once_with("test-model")
        mock_model.prompt.assert_called_once_with("System prompt\n\nUser prompt")

    @patch("vibectl.server.llm_proxy.llm")
    def test_execute_with_default_model_success(self, mock_llm: Mock) -> None:
        """Test successful Execute with default model when none specified."""
        # Arrange
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "Default model response"
        mock_response.usage = {"prompt_tokens": 5, "completion_tokens": 15}
        mock_model.prompt.return_value = mock_response
        mock_llm.get_model.return_value = mock_model

        servicer = LLMProxyServicer(default_model="default-model")
        request = llm_proxy_pb2.ExecuteRequest(  # type: ignore[attr-defined]
            request_id="test-456",
            user_fragments=["User prompt only"],
        )
        context = Mock()

        # Act
        response = servicer.Execute(request, context)

        # Assert
        assert response.request_id == "test-456"
        assert response.success is not None
        assert response.success.response_text == "Default model response"
        assert response.success.actual_model_used == "default-model"

        mock_llm.get_model.assert_called_once_with("default-model")
        mock_model.prompt.assert_called_once_with("User prompt only")

    @patch("vibectl.server.llm_proxy.uuid")
    @patch("vibectl.server.llm_proxy.llm")
    def test_execute_generates_request_id_when_missing(
        self, mock_llm: Mock, mock_uuid: Mock
    ) -> None:
        """Test that Execute generates request ID when not provided."""
        # Arrange
        mock_uuid.uuid4.return_value = "generated-uuid"
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "Response"
        mock_response.usage = {}
        mock_model.prompt.return_value = mock_response
        mock_llm.get_model.return_value = mock_model

        servicer = LLMProxyServicer(default_model="test-model")
        request = llm_proxy_pb2.ExecuteRequest(user_fragments=["Test"])  # type: ignore[attr-defined]
        context = Mock()

        # Act
        response = servicer.Execute(request, context)

        # Assert
        assert response.request_id == "generated-uuid"
        mock_uuid.uuid4.assert_called_once()

    def test_execute_no_model_specified_no_default(self) -> None:
        """Test Execute fails when no model specified and no default."""
        # Arrange
        servicer = LLMProxyServicer()
        request = llm_proxy_pb2.ExecuteRequest(  # type: ignore[attr-defined]
            request_id="test-789",
            user_fragments=["User prompt"],
        )
        context = Mock()

        # Act
        response = servicer.Execute(request, context)

        # Assert
        assert response.request_id == "test-789"
        assert response.error is not None
        assert response.error.error_code == "NO_MODEL"
        assert "No model specified" in response.error.error_message

    @patch("vibectl.server.llm_proxy.llm")
    def test_execute_model_not_found(self, mock_llm: Mock) -> None:
        """Test Execute fails when specified model is not found."""
        # Arrange
        mock_llm.get_model.return_value = None

        servicer = LLMProxyServicer()
        request = llm_proxy_pb2.ExecuteRequest(  # type: ignore[attr-defined]
            request_id="test-999",
            model_name="nonexistent-model",
            user_fragments=["Test"],
        )
        context = Mock()

        # Act
        response = servicer.Execute(request, context)

        # Assert
        assert response.request_id == "test-999"
        assert response.error is not None
        assert response.error.error_code == "MODEL_NOT_FOUND"
        assert "Model 'nonexistent-model' not found" in response.error.error_message

    @patch("vibectl.server.llm_proxy.llm")
    def test_execute_token_usage_with_callable_usage(self, mock_llm: Mock) -> None:
        """Test Execute handles callable usage data."""
        # Arrange
        usage_data = {"prompt_tokens": 30, "completion_tokens": 40}
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "Response with callable usage"
        mock_response.usage = Mock(return_value=usage_data)  # Callable usage
        mock_model.prompt.return_value = mock_response
        mock_llm.get_model.return_value = mock_model

        servicer = LLMProxyServicer(default_model="test-model")
        request = llm_proxy_pb2.ExecuteRequest(user_fragments=["Test"])  # type: ignore[attr-defined]
        context = Mock()

        # Act
        response = servicer.Execute(request, context)

        # Assert
        assert response.success.metrics.input_tokens == 30
        assert response.success.metrics.output_tokens == 40

    @patch("vibectl.server.llm_proxy.llm")
    def test_execute_token_usage_with_object_attributes(self, mock_llm: Mock) -> None:
        """Test Execute handles usage data as object attributes."""

        # Arrange
        class MockUsage:
            def __init__(self) -> None:
                self.prompt_tokens = 25
                self.completion_tokens = 35

        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "Response with object usage"
        mock_response.usage = MockUsage()
        mock_model.prompt.return_value = mock_response
        mock_llm.get_model.return_value = mock_model

        servicer = LLMProxyServicer(default_model="test-model")
        request = llm_proxy_pb2.ExecuteRequest(user_fragments=["Test"])  # type: ignore[attr-defined]
        context = Mock()

        # Act
        response = servicer.Execute(request, context)

        # Assert
        assert response.success is not None
        # The implementation tries to access via dict first, then falls
        # back to estimation
        # Since MockUsage doesn't have the dict interface, it will estimate tokens
        assert response.success.metrics.input_tokens > 0  # Should be estimated
        assert response.success.metrics.output_tokens > 0  # Should be estimated

    @patch("vibectl.server.llm_proxy.llm")
    def test_execute_token_usage_estimation_fallback(self, mock_llm: Mock) -> None:
        """Test Execute estimates token usage when data is unavailable."""
        # Arrange
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "Response with no usage data"
        mock_response.usage = None  # No usage data available
        mock_model.prompt.return_value = mock_response
        mock_llm.get_model.return_value = mock_model

        servicer = LLMProxyServicer(default_model="test-model")
        request = llm_proxy_pb2.ExecuteRequest(user_fragments=["Test prompt"])  # type: ignore[attr-defined]
        context = Mock()

        # Act
        response = servicer.Execute(request, context)

        # Assert - should fall back to estimation
        assert response.success is not None
        assert response.success.metrics.input_tokens > 0  # Estimated
        assert response.success.metrics.output_tokens > 0  # Estimated

    @patch("vibectl.server.llm_proxy.llm")
    def test_execute_token_usage_error_handling(self, mock_llm: Mock) -> None:
        """Test Execute handles errors in token usage extraction gracefully."""
        # Arrange
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "Response"
        # Usage throws exception when accessed
        mock_response.usage = Mock(side_effect=Exception("Usage error"))
        mock_model.prompt.return_value = mock_response
        mock_llm.get_model.return_value = mock_model

        servicer = LLMProxyServicer(default_model="test-model")
        request = llm_proxy_pb2.ExecuteRequest(user_fragments=["Test"])  # type: ignore[attr-defined]
        context = Mock()

        # Act
        response = servicer.Execute(request, context)

        # Assert - should fall back to estimation
        assert response.success is not None
        assert response.success.metrics.input_tokens > 0
        assert response.success.metrics.output_tokens > 0

    @patch("vibectl.server.llm_proxy.llm")
    def test_execute_exception_handling(self, mock_llm: Mock) -> None:
        """Test Execute handles LLM exceptions gracefully."""
        # Arrange
        mock_llm.get_model.side_effect = Exception("LLM service error")

        servicer = LLMProxyServicer()
        request = llm_proxy_pb2.ExecuteRequest(  # type: ignore[attr-defined]
            request_id="test-error",
            model_name="test-model",
            user_fragments=["Test"],
        )
        context = Mock()

        # Act
        response = servicer.Execute(request, context)

        # Assert
        assert response.request_id == "test-error"
        assert response.error is not None
        assert response.error.error_code == "EXECUTION_FAILED"
        assert "LLM service error" in response.error.error_message


class TestLLMProxyServicerStreamExecute:
    """Test the StreamExecute method (streaming)."""

    @patch("vibectl.server.llm_proxy.llm")
    def test_stream_execute_with_streaming_model(self, mock_llm: Mock) -> None:
        """Test StreamExecute with a model that supports streaming."""
        # Arrange
        mock_model = Mock()

        # Create mock streaming chunks that support iteration
        chunk1 = Mock()
        chunk1.text = Mock(return_value="First chunk")
        chunk2 = Mock()
        chunk2.text = Mock(return_value="Second chunk")
        chunk3 = Mock()
        chunk3.text = Mock(return_value="Final chunk")

        # Mock response that is iterable (supports streaming)
        mock_response = Mock()
        mock_response.__iter__ = Mock(
            return_value=iter(["First chunk", "Second chunk", "Final chunk"])
        )
        mock_response.usage = {"prompt_tokens": 10, "completion_tokens": 20}

        mock_model.prompt.return_value = mock_response
        mock_llm.get_model.return_value = mock_model

        servicer = LLMProxyServicer(default_model="streaming-model")
        request = llm_proxy_pb2.ExecuteRequest(  # type: ignore[attr-defined]
            request_id="stream-test",
            user_fragments=["Stream test"],
        )
        context = Mock()

        # Act
        responses = list(servicer.StreamExecute(request, context))

        # Assert
        # Should have 3 text chunks + 1 completion + 1 metrics = 5 total chunks
        assert len(responses) == 5
        assert all(resp.request_id == "stream-test" for resp in responses)

        # Check the text chunks
        text_responses = [
            resp
            for resp in responses
            if hasattr(resp, "text_chunk") and resp.text_chunk
        ]
        assert len(text_responses) == 3
        assert text_responses[0].text_chunk == "First chunk"
        assert text_responses[1].text_chunk == "Second chunk"
        assert text_responses[2].text_chunk == "Final chunk"

    @patch("vibectl.server.llm_proxy.llm")
    def test_stream_execute_with_non_streaming_model_simulated(
        self, mock_llm: Mock
    ) -> None:
        """Test StreamExecute with non-streaming model using simulated streaming."""
        # Arrange
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = (
            "Non-streaming response text that should be chunked"
        )
        mock_response.usage = {"prompt_tokens": 10, "completion_tokens": 20}

        # Mock response that is NOT iterable (doesn't support streaming)
        mock_response.__iter__ = Mock(side_effect=TypeError("Response is not iterable"))

        mock_model.prompt.return_value = mock_response
        mock_llm.get_model.return_value = mock_model

        servicer = LLMProxyServicer(default_model="non-streaming-model")
        request = llm_proxy_pb2.ExecuteRequest(  # type: ignore[attr-defined]
            request_id="fallback-test",
            user_fragments=["Fallback test"],
        )
        context = Mock()

        # Act
        responses = list(servicer.StreamExecute(request, context))

        # Assert - Should simulate streaming by chunking the response
        assert len(responses) >= 3  # At least some text chunks + completion + metrics
        assert all(resp.request_id == "fallback-test" for resp in responses)

        # Get all text chunks and concatenate them
        text_chunks = [
            resp.text_chunk
            for resp in responses
            if hasattr(resp, "text_chunk") and resp.text_chunk
        ]
        full_text = "".join(text_chunks)
        assert full_text == "Non-streaming response text that should be chunked"

    @patch("vibectl.server.llm_proxy.llm")
    def test_stream_execute_complete_fallback_on_streaming_error(
        self, mock_llm: Mock
    ) -> None:
        """Test StreamExecute falls back to complete response on streaming errors."""
        # Arrange
        mock_model = Mock()

        # First call to prompt() fails during streaming
        def first_prompt_call(*args: Any) -> Any:
            mock_response = Mock()
            mock_response.__iter__ = Mock(side_effect=Exception("Streaming error"))
            return mock_response

        # Second call to prompt() in fallback succeeds
        def second_prompt_call(*args: Any) -> Any:
            mock_response = Mock()
            mock_response.text.return_value = "Fallback response after error"
            mock_response.usage = {}
            return mock_response

        mock_model.prompt.side_effect = [first_prompt_call(), second_prompt_call()]
        mock_llm.get_model.return_value = mock_model

        servicer = LLMProxyServicer(default_model="error-model")
        request = llm_proxy_pb2.ExecuteRequest(  # type: ignore[attr-defined]
            request_id="error-test",
            user_fragments=["Error test"],
        )
        context = Mock()

        # Act
        responses = list(servicer.StreamExecute(request, context))

        # Assert - Should fall back and stream the complete response
        assert len(responses) >= 3  # Text chunks + completion + metrics
        assert all(resp.request_id == "error-test" for resp in responses)

        # Should contain fallback text in chunks
        text_chunks = [
            resp.text_chunk
            for resp in responses
            if hasattr(resp, "text_chunk") and resp.text_chunk
        ]
        full_text = "".join(text_chunks)
        assert full_text == "Fallback response after error"

    @patch("vibectl.server.llm_proxy.uuid")
    @patch("vibectl.server.llm_proxy.llm")
    def test_stream_execute_generates_request_id_when_missing(
        self, mock_llm: Mock, mock_uuid: Mock
    ) -> None:
        """Test that StreamExecute generates request ID when not provided."""
        # Arrange
        mock_uuid.uuid4.return_value = "generated-stream-uuid"
        mock_model = Mock()
        mock_response = Mock()
        mock_response.__iter__ = Mock(
            return_value=iter([Mock(text=lambda: "Generated ID chunk")])
        )
        mock_model.prompt.return_value = mock_response
        mock_llm.get_model.return_value = mock_model

        servicer = LLMProxyServicer(default_model="test-model")
        request = llm_proxy_pb2.ExecuteRequest(user_fragments=["Test"])  # type: ignore[attr-defined]
        context = Mock()

        # Act
        responses = list(servicer.StreamExecute(request, context))

        # Assert
        assert len(responses) >= 1
        assert all(resp.request_id == "generated-stream-uuid" for resp in responses)
        mock_uuid.uuid4.assert_called_once()

    def test_stream_execute_no_model_specified_no_default(self) -> None:
        """Test StreamExecute fails when no model specified and no default."""
        # Arrange
        servicer = LLMProxyServicer()
        request = llm_proxy_pb2.ExecuteRequest(  # type: ignore[attr-defined]
            request_id="stream-no-model",
            user_fragments=["User prompt"],
        )
        context = Mock()

        # Act
        responses = list(servicer.StreamExecute(request, context))

        # Assert
        assert len(responses) == 1
        assert responses[0].request_id == "stream-no-model"
        assert responses[0].error is not None
        assert responses[0].error.error_code == "NO_MODEL"
        assert "No model specified" in responses[0].error.error_message

    @patch("vibectl.server.llm_proxy.llm")
    def test_stream_execute_model_not_found(self, mock_llm: Mock) -> None:
        """Test StreamExecute fails when specified model is not found."""
        # Arrange
        mock_llm.get_model.return_value = None

        servicer = LLMProxyServicer()
        request = llm_proxy_pb2.ExecuteRequest(  # type: ignore[attr-defined]
            request_id="stream-not-found",
            model_name="nonexistent-model",
            user_fragments=["Test"],
        )
        context = Mock()

        # Act
        responses = list(servicer.StreamExecute(request, context))

        # Assert
        assert len(responses) == 1
        assert responses[0].request_id == "stream-not-found"
        assert responses[0].error is not None
        assert responses[0].error.error_code == "MODEL_NOT_FOUND"
        assert "Model 'nonexistent-model' not found" in responses[0].error.error_message

    @patch("vibectl.server.llm_proxy.llm")
    def test_stream_execute_exception_handling(self, mock_llm: Mock) -> None:
        """Test StreamExecute handles LLM exceptions gracefully."""
        # Arrange
        mock_llm.get_model.side_effect = Exception("Stream LLM error")

        servicer = LLMProxyServicer()
        request = llm_proxy_pb2.ExecuteRequest(  # type: ignore[attr-defined]
            request_id="stream-error",
            model_name="test-model",
            user_fragments=["Test"],
        )
        context = Mock()

        # Act
        responses = list(servicer.StreamExecute(request, context))

        # Assert
        assert len(responses) == 1
        assert responses[0].request_id == "stream-error"
        assert responses[0].error is not None
        assert responses[0].error.error_code == "EXECUTION_FAILED"
        assert "Stream LLM error" in responses[0].error.error_message


class TestLLMProxyServicerGetServerInfo:
    """Test the GetServerInfo method."""

    @patch("vibectl.server.llm_proxy.llm")
    def test_get_server_info_success(self, mock_llm: Mock) -> None:
        """Test successful GetServerInfo with model aliases."""
        # Arrange
        # Create mock model objects for get_models()
        model1 = Mock()
        model1.model_id = "model1"
        model1.display_name = "Model 1"
        model1.provider = "test-provider"

        model2 = Mock()
        model2.model_id = "model2"
        model2.display_name = "Model 2"
        model2.provider = "test-provider"

        alias1 = Mock()
        alias1.model_id = "alias1"
        alias1.display_name = "Alias 1"
        alias1.provider = "test-provider"

        # Mock get_models to return list of model objects
        mock_llm.get_models.return_value = [model1, model2, alias1]

        # Mock the dynamic alias discovery method (used in _get_dynamic_model_aliases)
        mock_llm.get_models_with_aliases.side_effect = Exception("Not implemented")

        config = {
            "model_aliases": {"custom-alias": "model1", "another-alias": "model2"}
        }
        servicer = LLMProxyServicer(default_model="model1", config=config)
        request = llm_proxy_pb2.GetServerInfoRequest()  # type: ignore[attr-defined]
        context = Mock()

        # Act
        response = servicer.GetServerInfo(request, context)

        # Assert
        assert response.default_model == "model1"
        assert response.server_name == "vibectl-llm-proxy"

        # Should include the configured aliases
        assert "custom-alias" in response.model_aliases
        assert response.model_aliases["custom-alias"] == "model1"
        assert "another-alias" in response.model_aliases
        assert response.model_aliases["another-alias"] == "model2"

        # Should include models in the available_models list
        assert len(response.available_models) == 3
        model_ids = [model.model_id for model in response.available_models]
        assert "model1" in model_ids
        assert "model2" in model_ids
        assert "alias1" in model_ids

    @patch("vibectl.server.llm_proxy.llm")
    def test_get_server_info_with_model_missing_attributes(
        self, mock_llm: Mock
    ) -> None:
        """Test GetServerInfo handles models missing expected attributes."""
        # Arrange
        model_complete = Mock()
        model_complete.model_id = "complete_model"
        model_complete.display_name = "Complete Model"
        model_complete.provider = "test-provider"

        model_no_display = Mock()
        model_no_display.model_id = "model_no_display"
        # No display_name, should fall back to model_id
        model_no_display.provider = "test-provider"
        # Ensure getattr returns a string, not a Mock
        del model_no_display.display_name

        model_no_provider = Mock()
        model_no_provider.model_id = "model_no_provider"
        model_no_provider.display_name = "Model No Provider"
        # No provider, should fall back to "unknown"
        # Ensure getattr returns a string, not a Mock
        del model_no_provider.provider

        mock_llm.get_models.return_value = [
            model_complete,
            model_no_display,
            model_no_provider,
        ]
        mock_llm.get_models_with_aliases.side_effect = Exception("Not implemented")

        servicer = LLMProxyServicer()
        request = llm_proxy_pb2.GetServerInfoRequest()  # type: ignore[attr-defined]
        context = Mock()

        # Act
        response = servicer.GetServerInfo(request, context)

        # Assert - Should handle missing attributes gracefully using getattr fallbacks
        assert response.default_model == ""
        assert len(response.available_models) == 3

        # Check that models are included despite missing attributes
        model_ids = [model.model_id for model in response.available_models]
        assert "complete_model" in model_ids
        assert "model_no_display" in model_ids
        assert "model_no_provider" in model_ids

        # Check the fallback values
        model_dict = {model.model_id: model for model in response.available_models}

        # Complete model should have its attributes
        complete_model_info = model_dict["complete_model"]
        assert complete_model_info.display_name == "Complete Model"
        assert complete_model_info.provider == "test-provider"

        # Model without display_name should fall back to model_id
        no_display_model_info = model_dict["model_no_display"]
        assert no_display_model_info.display_name == "model_no_display"
        assert no_display_model_info.provider == "test-provider"

        # Model without provider should fall back to "unknown"
        no_provider_model_info = model_dict["model_no_provider"]
        assert no_provider_model_info.display_name == "Model No Provider"
        assert no_provider_model_info.provider == "unknown"

    @patch("vibectl.server.llm_proxy.llm")
    def test_get_server_info_dynamic_alias_discovery_error(
        self, mock_llm: Mock
    ) -> None:
        """Test GetServerInfo handles errors during dynamic alias discovery."""
        # Arrange
        model1 = Mock()
        model1.model_id = "static-model"
        model1.display_name = "Static Model"
        model1.provider = "test-provider"

        mock_llm.get_models.return_value = [model1]
        mock_llm.get_models_with_aliases.side_effect = Exception("Cannot fetch models")

        config = {"model_aliases": {"static-alias": "static-model"}}
        servicer = LLMProxyServicer(default_model="default", config=config)
        request = llm_proxy_pb2.GetServerInfoRequest()  # type: ignore[attr-defined]
        context = Mock()

        # Act
        response = servicer.GetServerInfo(request, context)

        # Assert - Should return configured aliases despite dynamic discovery failure
        assert response.default_model == "default"
        assert "static-alias" in response.model_aliases
        assert response.model_aliases["static-alias"] == "static-model"

    @patch("vibectl.server.llm_proxy.llm")
    def test_get_server_info_exception_handling(self, mock_llm: Mock) -> None:
        """Test GetServerInfo handles general exceptions gracefully."""
        # Arrange
        mock_llm.get_models.side_effect = Exception("Unexpected error")
        mock_llm.get_models_with_aliases.side_effect = Exception("Unexpected error")

        servicer = LLMProxyServicer()
        request = llm_proxy_pb2.GetServerInfoRequest()  # type: ignore[attr-defined]
        context = Mock()

        # Act & Assert - Should raise the exception as per implementation
        with pytest.raises(Exception, match="Unexpected error"):
            servicer.GetServerInfo(request, context)


class TestLLMProxyServicerPrivateMethods:
    """Test private helper methods of LLMProxyServicer."""

    @patch("vibectl.server.llm_proxy.llm")
    def test_get_dynamic_model_aliases_success(self, mock_llm: Mock) -> None:
        """Test _get_dynamic_model_aliases extracts aliases correctly."""
        # Arrange
        # Mock the get_models_with_aliases method (the actual method called)
        mock_model_with_aliases_1 = Mock()
        mock_model_with_aliases_1.model.model_id = "gpt-4"
        mock_model_with_aliases_1.aliases = ["gpt4", "openai-gpt4"]

        mock_model_with_aliases_2 = Mock()
        mock_model_with_aliases_2.model.model_id = "claude"
        mock_model_with_aliases_2.aliases = ["claude-v1", "anthropic-claude"]

        mock_llm.get_models_with_aliases.return_value = [
            mock_model_with_aliases_1,
            mock_model_with_aliases_2,
        ]

        servicer = LLMProxyServicer()

        # Act
        aliases = servicer._get_dynamic_model_aliases()

        # Assert
        assert len(aliases) == 4  # Two aliases for each model
        assert aliases["gpt4"] == "gpt-4"
        assert aliases["openai-gpt4"] == "gpt-4"
        assert aliases["claude-v1"] == "claude"
        assert aliases["anthropic-claude"] == "claude"

    @patch("vibectl.server.llm_proxy.llm")
    def test_get_dynamic_model_aliases_error(self, mock_llm: Mock) -> None:
        """Test _get_dynamic_model_aliases handles errors gracefully."""
        # Arrange
        mock_llm.get_models_with_aliases.side_effect = Exception(
            "Model discovery failed"
        )

        servicer = LLMProxyServicer()

        # Act
        aliases = servicer._get_dynamic_model_aliases()

        # Assert
        assert aliases == {}  # Should return empty dict on error


class TestLLMProxyServicerIntegration:
    """Integration tests for LLMProxyServicer combining multiple features."""

    @patch("vibectl.server.llm_proxy.time")
    @patch("vibectl.server.llm_proxy.llm")
    def test_metrics_timing_accuracy(self, mock_llm: Mock, mock_time: Mock) -> None:
        """Test that metrics timing is calculated accurately."""
        # Arrange
        start_time = 1000.0
        end_time = 1002.5  # 2.5 seconds later
        timestamp = 1000
        mock_time.time.side_effect = [
            start_time,
            end_time,
            timestamp,
        ]  # start, duration calc, timestamp

        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "Timed response"
        mock_response.usage = {"prompt_tokens": 100, "completion_tokens": 200}
        mock_model.prompt.return_value = mock_response
        mock_llm.get_model.return_value = mock_model

        servicer = LLMProxyServicer(default_model="test-model")
        request = llm_proxy_pb2.ExecuteRequest(user_fragments=["Test timing"])  # type: ignore[attr-defined]
        context = Mock()

        # Act
        response = servicer.Execute(request, context)

        # Assert
        assert response.success is not None
        # Should be approximately 2500ms (2.5 seconds)
        assert 2499 <= response.success.metrics.duration_ms <= 2501

    @patch("vibectl.server.llm_proxy.llm")
    def test_prompt_construction_with_system_and_user_fragments(
        self, mock_llm: Mock
    ) -> None:
        """Test that system and user fragments are properly combined."""
        # Arrange
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "Combined response"
        mock_response.usage = {}
        mock_model.prompt.return_value = mock_response
        mock_llm.get_model.return_value = mock_model

        servicer = LLMProxyServicer(default_model="test-model")
        request = llm_proxy_pb2.ExecuteRequest(  # type: ignore[attr-defined]
            system_fragments=["System part 1", "System part 2"],
            user_fragments=["User part 1", "User part 2"],
        )
        context = Mock()

        # Act
        servicer.Execute(request, context)

        # Assert
        expected_prompt = "System part 1\n\nSystem part 2\n\nUser part 1\n\nUser part 2"
        mock_model.prompt.assert_called_once_with(expected_prompt)
