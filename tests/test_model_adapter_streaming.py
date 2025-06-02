"""Tests for streaming functionality in model adapter."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from vibectl.model_adapter import (
    LLMModelAdapter,
    StreamingMetricsCollector,
)
from vibectl.types import (
    Fragment,
    LLMMetrics,
    SystemFragments,
    UserFragments,
)


class TestStreamingMetricsCollector:
    """Tests for StreamingMetricsCollector class."""

    def test_initial_state(self) -> None:
        """Test initial state of StreamingMetricsCollector."""
        collector = StreamingMetricsCollector()
        assert not collector.is_completed
        assert not collector._completed

    async def test_get_metrics_before_completion(self) -> None:
        """Test get_metrics returns None before completion."""
        collector = StreamingMetricsCollector()
        metrics = await collector.get_metrics()
        assert metrics is None

    async def test_get_metrics_after_completion(self) -> None:
        """Test get_metrics returns metrics after completion."""
        collector = StreamingMetricsCollector()
        test_metrics = LLMMetrics(
            latency_ms=100.0,
            total_processing_duration_ms=500.0,
            token_input=10,
            token_output=20,
            call_count=1,
        )

        # Mark as completed
        collector._mark_completed(test_metrics)

        assert collector.is_completed
        metrics = await collector.get_metrics()
        assert metrics == test_metrics

    def test_mark_completed(self) -> None:
        """Test internal _mark_completed method."""
        collector = StreamingMetricsCollector()
        test_metrics = LLMMetrics(
            latency_ms=50.0,
            total_processing_duration_ms=200.0,
            token_input=5,
            token_output=15,
            call_count=1,
        )

        collector._mark_completed(test_metrics)

        assert collector.is_completed
        assert collector._completed
        assert collector._metrics == test_metrics


class TestLLMModelAdapterStreaming:
    """Tests for streaming functionality in LLMModelAdapter."""

    def setup_method(self) -> None:
        """Setup for each test."""
        self.adapter = LLMModelAdapter()

    @patch("vibectl.model_adapter.ModelEnvironment")
    async def test_stream_execute_success(self, mock_env: MagicMock) -> None:
        """Test successful streaming execution."""
        # Setup mock model
        mock_model = Mock()
        mock_model.model_id = "test-streaming-model"

        # Mock response object that is iterable
        mock_response = Mock()
        mock_response.__iter__ = Mock(return_value=iter(["chunk1", "chunk2", "chunk3"]))
        mock_model.prompt.return_value = mock_response

        # Setup fragments
        system_fragments = SystemFragments([Fragment("System prompt")])
        user_fragments = UserFragments([Fragment("User prompt")])

        # Execute streaming
        chunks = []
        async for chunk in self.adapter.stream_execute(
            mock_model, system_fragments, user_fragments
        ):
            chunks.append(chunk)

        # Verify
        assert chunks == ["chunk1", "chunk2", "chunk3"]
        mock_model.prompt.assert_called_once()
        call_kwargs = mock_model.prompt.call_args[1]
        assert call_kwargs["system"] == "System prompt"
        assert call_kwargs["prompt"] == "User prompt"

    @patch("vibectl.model_adapter.ModelEnvironment")
    async def test_stream_execute_with_error(self, mock_env: MagicMock) -> None:
        """Test streaming execution with error."""
        # Setup mock model that raises an error
        mock_model = Mock()
        mock_model.model_id = "test-streaming-model"
        mock_model.prompt.side_effect = Exception("Streaming error")

        # Setup fragments
        system_fragments = SystemFragments([])
        user_fragments = UserFragments([Fragment("User prompt")])

        # Execute and verify error
        with pytest.raises(ValueError, match="LLM Streaming Execution Error"):
            async for _ in self.adapter.stream_execute(
                mock_model, system_fragments, user_fragments
            ):
                pass  # Should not reach here

    @patch("vibectl.model_adapter.ModelEnvironment")
    async def test_stream_execute_type_error(self, mock_env: MagicMock) -> None:
        """Test streaming execution with TypeError (non-iterable response)."""
        # Setup mock model with non-iterable response
        mock_model = Mock()
        mock_model.model_id = "test-streaming-model"

        # Mock response that is not iterable
        mock_response = Mock()
        mock_response.__iter__ = Mock(side_effect=TypeError("Not iterable"))
        mock_model.prompt.return_value = mock_response

        # Setup fragments
        system_fragments = SystemFragments([])
        user_fragments = UserFragments([Fragment("User prompt")])

        # Execute and verify TypeError handling
        with pytest.raises(ValueError, match="LLM streaming iteration error"):
            async for _ in self.adapter.stream_execute(
                mock_model, system_fragments, user_fragments
            ):
                pass  # Should not reach here

    @patch("vibectl.model_adapter.time.monotonic")
    @patch.object(LLMModelAdapter, "stream_execute")
    async def test_stream_execute_and_log_metrics_success(
        self, mock_stream_execute: AsyncMock, mock_time: MagicMock
    ) -> None:
        """Test stream_execute_and_log_metrics with successful streaming."""
        # Setup time mocking for metrics
        mock_time.side_effect = [0.0, 0.1, 0.5]  # start, first_chunk, end

        # Setup mock model
        mock_model = Mock()
        mock_model.model_id = "test-metrics-model"

        # Mock stream_execute to return chunks
        async def mock_stream_generator() -> AsyncIterator[str]:
            yield "chunk1"
            yield "chunk2"
            yield "chunk3"

        mock_stream_execute.return_value = mock_stream_generator()

        # Setup fragments
        system_fragments = SystemFragments([Fragment("System prompt")])
        user_fragments = UserFragments([Fragment("User prompt")])

        # Execute streaming with metrics
        (
            stream_iterator,
            metrics_collector,
        ) = await self.adapter.stream_execute_and_log_metrics(
            mock_model, system_fragments, user_fragments
        )

        # Consume the stream
        chunks = []
        async for chunk in stream_iterator:
            chunks.append(chunk)

        # Verify chunks
        assert chunks == ["chunk1", "chunk2", "chunk3"]

        # Verify metrics
        assert metrics_collector.is_completed
        final_metrics = await metrics_collector.get_metrics()
        assert final_metrics is not None
        assert final_metrics.latency_ms == 100.0  # (0.1 - 0.0) * 1000
        assert final_metrics.total_processing_duration_ms == 500.0  # (0.5 - 0.0) * 1000
        assert final_metrics.call_count == 1
        assert final_metrics.token_input > 0  # Estimated from input
        assert final_metrics.token_output > 0  # Estimated from output

    @patch("vibectl.model_adapter.time.monotonic")
    @patch.object(LLMModelAdapter, "stream_execute")
    async def test_stream_execute_and_log_metrics_with_error(
        self, mock_stream_execute: AsyncMock, mock_time: MagicMock
    ) -> None:
        """Test stream_execute_and_log_metrics with streaming error."""
        # Setup time mocking
        mock_time.side_effect = [0.0, 0.2]  # start, error_time

        # Setup mock model
        mock_model = Mock()
        mock_model.model_id = "test-error-model"

        # Mock stream_execute to raise an error
        async def failing_stream() -> AsyncIterator[str]:
            raise ValueError("Stream error")
            yield  # This will never be reached

        mock_stream_execute.return_value = failing_stream()

        # Setup fragments
        system_fragments = SystemFragments([])
        user_fragments = UserFragments([Fragment("User prompt")])

        # Execute stream_execute_and_log_metrics
        (
            stream_iterator,
            metrics_collector,
        ) = await self.adapter.stream_execute_and_log_metrics(
            mock_model, system_fragments, user_fragments
        )

        # The error should be raised when we consume the stream
        with pytest.raises(ValueError, match="Stream error"):
            chunks = []
            async for chunk in stream_iterator:
                chunks.append(chunk)

    async def test_stream_execute_and_log_metrics_token_estimation(self) -> None:
        """Test token estimation logic in streaming metrics."""

        # Test the token estimation function used internally
        def estimate_tokens(text: str) -> int:
            return max(1, len(text) // 4)

        # Test various text lengths
        assert estimate_tokens("") == 1  # Minimum 1 token
        assert estimate_tokens("short") == 1  # 5 chars -> 1 token
        assert estimate_tokens("this is a longer text") == 5  # 22 chars -> 5 tokens
        assert estimate_tokens("a" * 20) == 5  # 20 chars -> 5 tokens

    @patch("vibectl.model_adapter.ModelEnvironment")
    async def test_stream_execute_empty_fragments(self, mock_env: MagicMock) -> None:
        """Test streaming execution with empty fragments."""
        # Setup mock model
        mock_model = Mock()
        mock_model.model_id = "test-empty-model"

        # Mock response object
        mock_response = Mock()
        mock_response.__iter__ = Mock(return_value=iter(["response"]))
        mock_model.prompt.return_value = mock_response

        # Setup empty fragments
        system_fragments = SystemFragments([])
        user_fragments = UserFragments([])

        # Execute streaming
        chunks = []
        async for chunk in self.adapter.stream_execute(
            mock_model, system_fragments, user_fragments
        ):
            chunks.append(chunk)

        # Verify
        assert chunks == ["response"]
        mock_model.prompt.assert_called_once()
        call_kwargs = mock_model.prompt.call_args[1]
        # Should have empty prompt when no user fragments
        assert call_kwargs["prompt"] == ""

    @patch("vibectl.model_adapter.ModelEnvironment")
    async def test_stream_execute_multiple_system_fragments(
        self, mock_env: MagicMock
    ) -> None:
        """Test streaming execution with multiple system fragments."""
        # Setup mock model
        mock_model = Mock()
        mock_model.model_id = "test-multi-system-model"

        # Mock response object
        mock_response = Mock()
        mock_response.__iter__ = Mock(return_value=iter(["response"]))
        mock_model.prompt.return_value = mock_response

        # Setup multiple system fragments
        system_fragments = SystemFragments(
            [Fragment("System 1"), Fragment("System 2"), Fragment("System 3")]
        )
        user_fragments = UserFragments([Fragment("User input")])

        # Execute streaming
        chunks = []
        async for chunk in self.adapter.stream_execute(
            mock_model, system_fragments, user_fragments
        ):
            chunks.append(chunk)

        # Verify
        assert chunks == ["response"]
        mock_model.prompt.assert_called_once()
        call_kwargs = mock_model.prompt.call_args[1]
        # System fragments should be joined with double newlines
        assert call_kwargs["system"] == "System 1\n\nSystem 2\n\nSystem 3"
        assert call_kwargs["prompt"] == "User input"

    @patch("vibectl.model_adapter.ModelEnvironment")
    async def test_stream_execute_multiple_user_fragments(
        self, mock_env: MagicMock
    ) -> None:
        """Test streaming execution with multiple user fragments."""
        # Setup mock model
        mock_model = Mock()
        mock_model.model_id = "test-multi-user-model"

        # Mock response object
        mock_response = Mock()
        mock_response.__iter__ = Mock(return_value=iter(["response"]))
        mock_model.prompt.return_value = mock_response

        # Setup multiple user fragments
        system_fragments = SystemFragments([Fragment("System prompt")])
        user_fragments = UserFragments(
            [Fragment("Fragment 1"), Fragment("Fragment 2"), Fragment("Fragment 3")]
        )

        # Execute streaming
        chunks = []
        async for chunk in self.adapter.stream_execute(
            mock_model, system_fragments, user_fragments
        ):
            chunks.append(chunk)

        # Verify
        assert chunks == ["response"]
        mock_model.prompt.assert_called_once()
        call_kwargs = mock_model.prompt.call_args[1]
        assert call_kwargs["system"] == "System prompt"
        # User fragments should be joined with double newlines
        assert call_kwargs["prompt"] == "Fragment 1\n\nFragment 2\n\nFragment 3"

    async def test_stream_execute_and_log_metrics_empty_stream(self) -> None:
        """Test metrics collection with empty stream."""
        # Setup mock model
        mock_model = Mock()
        mock_model.model_id = "test-empty-stream-model"

        # Mock stream_execute to return empty stream
        async def empty_stream() -> AsyncIterator[str]:
            return
            yield  # This will never be reached

        with patch.object(self.adapter, "stream_execute", return_value=empty_stream()):
            # Execute streaming with metrics
            (
                stream_iterator,
                metrics_collector,
            ) = await self.adapter.stream_execute_and_log_metrics(
                mock_model, SystemFragments([]), UserFragments([])
            )

            # Consume the empty stream
            chunks = []
            async for chunk in stream_iterator:
                chunks.append(chunk)

            # Verify empty stream
            assert chunks == []

            # Verify metrics are still collected
            assert metrics_collector.is_completed
            final_metrics = await metrics_collector.get_metrics()
            assert final_metrics is not None
            assert final_metrics.token_output == 1  # Minimum 1 token for empty string
