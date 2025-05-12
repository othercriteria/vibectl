"""Tests for model adapter."""

import os
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
from pydantic import BaseModel

from vibectl.model_adapter import (
    LLMMetrics,
    LLMModelAdapter,
    ModelAdapter,
    ModelEnvironment,
    ModelResponse,
    get_model_adapter,
    reset_model_adapter,
    set_model_adapter,
)


class TestModelAdapter:
    """Tests for model adapter functions."""

    def setup_method(self) -> None:
        """Reset adapter between tests."""
        reset_model_adapter()

    def test_get_model_adapter(self) -> None:
        """Test get_model_adapter creates a single instance."""
        adapter1 = get_model_adapter()
        adapter2 = get_model_adapter()
        assert adapter1 is adapter2
        assert isinstance(adapter1, LLMModelAdapter)

    def test_set_model_adapter(self) -> None:
        """Test setting a custom adapter."""
        mock_adapter = Mock(spec=ModelAdapter)
        set_model_adapter(mock_adapter)
        adapter = get_model_adapter()
        assert adapter is mock_adapter

    def test_reset_model_adapter(self) -> None:
        """Test resetting the adapter."""
        adapter1 = get_model_adapter()
        reset_model_adapter()
        adapter2 = get_model_adapter()
        assert adapter1 is not adapter2


class TestLLMModelAdapter:
    """Tests for LLMModelAdapter."""

    @patch("vibectl.model_adapter.llm")
    def test_get_model(self, mock_llm: MagicMock) -> None:
        """Test getting a model."""
        # Setup
        mock_model = Mock()
        mock_response = Mock(spec=ModelResponse)
        mock_response.text.return_value = "Test response"
        mock_model.prompt.return_value = mock_response
        # Add model_id to the mock model
        mock_model.model_id = "test-model-basic"
        # Set the return value for the patched llm.get_model
        mock_llm.get_model.return_value = mock_model

        # Execute
        adapter = LLMModelAdapter()
        model = adapter.get_model("test-model")

        # Verify
        assert (
            model is mock_llm.get_model.return_value
        )  # Check against the patched return value
        mock_llm.get_model.assert_called_once_with("test-model")

    @patch("vibectl.model_adapter.llm")
    def test_get_model_caching(self, mock_llm: MagicMock) -> None:
        """Test model caching."""
        # Setup
        mock_model = Mock()
        mock_response = Mock(spec=ModelResponse)
        mock_response.text.return_value = "Test response"
        mock_model.prompt.return_value = mock_response
        # Add model_id to the mock model
        mock_model.model_id = "test-model-basic"

        # Execute
        adapter = LLMModelAdapter()
        model1 = adapter.get_model("test-model")
        model2 = adapter.get_model("test-model")

        # Verify
        assert model1 is model2
        mock_llm.get_model.assert_called_once_with("test-model")

    @patch("vibectl.model_adapter.llm")
    def test_get_model_error(self, mock_llm: MagicMock) -> None:
        """Test error handling when getting a model."""
        # Setup
        # mock_model = Mock() # No need to mock the model instance itself
        # mock_response = Mock(spec=ModelResponse)
        # mock_response.text.return_value = "Test response"
        # Set side_effect on the llm.get_model call
        mock_llm.get_model.side_effect = Exception("Test error getting model")

        # Execute and verify
        adapter = LLMModelAdapter()
        with pytest.raises(ValueError, match="Test error getting model") as exc_info:
            adapter.get_model("test-model")

        assert "Failed to get model 'test-model'" in str(exc_info.value)
        mock_llm.get_model.assert_called_once_with("test-model")

    @patch("vibectl.model_adapter.llm")
    def test_execute(self, mock_llm: MagicMock) -> None:
        """Test executing a prompt on a model."""
        # Setup
        mock_model = Mock()
        mock_response = Mock(spec=ModelResponse)
        mock_response.text.return_value = "Test response"
        mock_model.prompt.return_value = mock_response
        # Add model_id to the mock model
        mock_model.model_id = "test-model-basic"

        # Execute
        adapter = LLMModelAdapter()
        response_text, metrics = adapter.execute(mock_model, "Test prompt")

        # Verify response
        assert response_text == "Test response"
        assert isinstance(metrics, LLMMetrics)
        assert metrics.call_count == 1
        assert metrics.latency_ms > 0
        # Add assertions for token counts if they become available
        mock_model.prompt.assert_called_once_with("Test prompt")

    @patch("vibectl.model_adapter.llm")
    def test_execute_string_response(self, mock_llm: MagicMock) -> None:
        """Test handling string responses."""
        # Setup
        mock_model = Mock()
        mock_response = Mock(spec=ModelResponse)
        mock_response.text.return_value = "Test response"
        mock_model.prompt.return_value = mock_response
        # Add model_id to the mock model
        mock_model.model_id = "test-model-basic"

        # Execute
        adapter = LLMModelAdapter()
        response_text, metrics = adapter.execute(mock_model, "Test prompt")

        # Verify response
        assert response_text == "Test response"
        assert isinstance(metrics, LLMMetrics)
        assert metrics.call_count == 1
        assert metrics.latency_ms > 0
        mock_model.prompt.assert_called_once_with("Test prompt")

    @patch("vibectl.model_adapter.llm")
    def test_execute_error(self, mock_llm: MagicMock) -> None:
        """Test error handling during execution."""
        # Setup
        mock_model = Mock()
        mock_response = Mock(spec=ModelResponse)
        mock_response.text.return_value = "Test response"
        # Set side_effect on the prompt method of the model mock
        mock_model.prompt.side_effect = Exception("Test error")
        # Add model_id to the mock model
        mock_model.model_id = "test-model-error"

        # Execute and verify
        adapter = LLMModelAdapter()
        # Expect ValueError with the specific wrapped message
        with pytest.raises(ValueError, match="LLM Execution Error: Test error"):
            adapter.execute(mock_model, "Test prompt")

        mock_model.prompt.assert_called_once_with("Test prompt")

    @patch("vibectl.model_adapter.llm")
    def test_execute_with_type_casting(self, mock_llm: MagicMock) -> None:
        """Test type casting behavior in the execute method.

        This tests the adapter's ability to properly handle and cast
        responses from the model that have a text() method returning
        different types.
        """
        # Setup
        mock_model = Mock()
        # Add model_id to the mock model
        mock_model.model_id = "test-model-type-casting"

        # Mock responses with different types, ensuring they return ModelResponse
        mock_response_int = Mock(spec=ModelResponse)
        mock_response_int.text.return_value = "42"
        mock_response_float = Mock(spec=ModelResponse)
        mock_response_float.text.return_value = "3.14"
        mock_response_bool = Mock(spec=ModelResponse)
        mock_response_bool.text.return_value = "True"
        mock_response_none = Mock(spec=ModelResponse)
        mock_response_none.text.return_value = "None"

        # Test each response type
        adapter = LLMModelAdapter()

        # Test integer response
        mock_model.prompt.return_value = mock_response_int
        response_text, metrics = adapter.execute(mock_model, "Integer prompt")
        assert response_text == "42"  # Should be the string representation
        assert isinstance(metrics, LLMMetrics)
        assert metrics.call_count == 1
        assert metrics.latency_ms > 0

        # Test float response
        mock_model.prompt.return_value = mock_response_float
        response_text, metrics = adapter.execute(mock_model, "Float prompt")
        assert response_text == "3.14"  # Should be the string representation
        assert isinstance(metrics, LLMMetrics)
        assert metrics.call_count == 1
        assert metrics.latency_ms > 0

        # Test boolean response
        mock_model.prompt.return_value = mock_response_bool
        response_text, metrics = adapter.execute(mock_model, "Boolean prompt")
        assert response_text == "True"  # Should be the string representation
        assert isinstance(metrics, LLMMetrics)
        assert metrics.call_count == 1
        assert metrics.latency_ms > 0

        # Test None response
        mock_model.prompt.return_value = mock_response_none
        response_text, metrics = adapter.execute(mock_model, "None prompt")
        assert response_text == "None"  # Should be the string representation
        assert isinstance(metrics, LLMMetrics)
        assert metrics.call_count == 1
        assert metrics.latency_ms > 0

        # Verify all prompt calls
        assert mock_model.prompt.call_count == 4


def test_model_response_protocol_runtime_check() -> None:
    class DummyResponse:
        def text(self) -> str:
            return "foo"

    resp = DummyResponse()
    assert isinstance(resp, ModelResponse)


def test_model_adapter_abc_methods() -> None:
    class DummyAdapter(ModelAdapter):
        def get_model(self, model_name: str) -> str:
            raise NotImplementedError()

        def execute(
            self,
            model: Any,
            prompt_text: str,
            response_model: type[BaseModel] | None = None,
        ) -> tuple[str, LLMMetrics | None]:
            # Dummy implementation returning text and None for metrics
            return f"Executed {prompt_text} on {model}", None

        def validate_model_key(self, model_name: str) -> str | None:
            raise NotImplementedError()

        def validate_model_name(self, model_name: str) -> str | None:
            return None

        def execute_and_log_metrics(
            self,
            model: Any,
            prompt_text: str,
            response_model: type[BaseModel] | None = None,
        ) -> str:
            # Dummy implementation calls execute and returns only the text part
            response_text, _metrics = self.execute(model, prompt_text, response_model)
            return response_text

    adapter = DummyAdapter()
    with pytest.raises(NotImplementedError):
        adapter.get_model("foo")
    with pytest.raises(NotImplementedError):
        adapter.validate_model_key("foo")


def test_validate_model_key_unknown_provider() -> None:
    adapter = LLMModelAdapter()
    msg = adapter.validate_model_key("unknown-model")
    assert isinstance(msg, str) and "Unknown model provider" in msg


def test_validate_model_key_ollama() -> None:
    adapter = LLMModelAdapter()
    # Should return None for ollama
    assert adapter.validate_model_key("ollama:foo") is None


def test_validate_model_key_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = LLMModelAdapter()
    monkeypatch.setattr(adapter.config, "get_model_key", lambda provider: None)
    msg = adapter.validate_model_key("gpt-3.5-turbo")
    assert isinstance(msg, str) and "No API key found" in msg


def test_validate_model_key_invalid_format(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = LLMModelAdapter()
    # Provide a long key that doesn't start with sk-
    monkeypatch.setattr(adapter.config, "get_model_key", lambda provider: "x" * 30)
    msg = adapter.validate_model_key("gpt-3.5-turbo")
    assert isinstance(msg, str) and "API key format looks invalid" in msg


def test_validate_model_key_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = LLMModelAdapter()
    monkeypatch.setattr(adapter.config, "get_model_key", lambda provider: "sk-abc123")
    assert adapter.validate_model_key("gpt-3.5-turbo") is None


def test_model_environment_all_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    # Unknown provider: should do nothing
    config = Mock()
    env = ModelEnvironment("foo-bar", config)
    assert env.provider is None
    env.__enter__()  # __enter__ returns None, no need to assert
    # Known provider, no key
    config.get_model_key.return_value = None
    env = ModelEnvironment("gpt-3.5-turbo", config)
    # No key, so nothing set
    env.__enter__()
    # Known provider, with key, no original env
    config.get_model_key.return_value = "test-key"
    env = ModelEnvironment("gpt-3.5-turbo", config)
    # Remove env var if present
    os.environ.pop("OPENAI_API_KEY", None)
    env.__enter__()
    assert os.environ["OPENAI_API_KEY"] == "test-key"
    env.__exit__(None, None, None)
    assert "OPENAI_API_KEY" not in os.environ
    # Known provider, with key, with original env
    os.environ["OPENAI_API_KEY"] = "orig-key"
    config.get_model_key.return_value = "test-key"
    env = ModelEnvironment("gpt-3.5-turbo", config)
    env.__enter__()
    assert os.environ["OPENAI_API_KEY"] == "test-key"
    env.__exit__(None, None, None)
    assert os.environ["OPENAI_API_KEY"] == "orig-key"


def test_get_model_ollama_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ollama models should not require an API key, even if none is set."""
    from vibectl.model_adapter import LLMModelAdapter

    adapter = LLMModelAdapter()
    # Patch llm.get_model to return a dummy model
    monkeypatch.setattr("vibectl.model_adapter.llm.get_model", lambda name: object())
    # Should not raise
    adapter.get_model("ollama:tinyllama")


def test_get_model_ollama_with_dummy_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ollama models should not error if a dummy API key is set."""
    from vibectl.model_adapter import LLMModelAdapter

    adapter = LLMModelAdapter()
    # Patch config.get_model_key to return a dummy key for ollama
    monkeypatch.setattr(
        adapter.config,
        "get_model_key",
        lambda provider: "dummy" if provider == "ollama" else None,
    )
    # Patch llm.get_model to return a dummy model
    monkeypatch.setattr("vibectl.model_adapter.llm.get_model", lambda name: object())
    # Should not raise
    adapter.get_model("ollama:tinyllama")


class TestLLMModelAdapterSchemaFallback:
    """Tests specifically for the schema fallback logic in LLMModelAdapter."""

    class MockResponse:
        def __init__(self, text_content: str):
            self._text = text_content

        def text(self) -> str:
            return self._text

    class DummySchema(BaseModel):
        field: str

    @patch("vibectl.model_adapter.llm")
    def test_execute_schema_unsupported_fallback(self, mock_llm: MagicMock) -> None:
        """Test execute falls back when model.prompt raises schema-related
        AttributeError."""
        # Setup
        mock_model = Mock()
        mock_model.model_id = "test-fallback-model"  # Add model_id for logging
        # Mock prompt to raise AttributeError for 'schema' on the first call
        # and return a valid response on the second (fallback) call
        mock_fallback_response = self.MockResponse("Fallback response text")
        mock_model.prompt.side_effect = [
            AttributeError("'Model' object has no attribute 'schema'"),
            mock_fallback_response,  # Return value for the second call
        ]

        # Execute
        adapter = LLMModelAdapter()
        response_text, metrics = adapter.execute(
            mock_model, "Test prompt", response_model=self.DummySchema
        )

        # Verify
        assert response_text == "Fallback response text"
        # Check prompt was called twice: first with schema, then without
        assert mock_model.prompt.call_count == 2
        # First call with schema (expecting the generated dictionary)
        mock_model.prompt.assert_any_call(
            "Test prompt", schema=self.DummySchema.model_json_schema()
        )
        # Second call without schema (fallback)
        mock_model.prompt.assert_any_call("Test prompt")

    @patch("vibectl.model_adapter.llm")
    def test_execute_schema_supported(self, mock_llm: MagicMock) -> None:
        """Test execute works normally when schema is supported."""
        # Setup
        mock_model = Mock()
        mock_model.model_id = "test-schema-model"  # Add model_id
        mock_response = Mock(spec=ModelResponse)
        mock_response.text.return_value = '{"field": "value"}'
        mock_model.prompt.return_value = mock_response

        # Execute
        adapter = LLMModelAdapter()
        response_text, metrics = adapter.execute(
            mock_model, "Test prompt", response_model=self.DummySchema
        )

        # Verify
        assert response_text == '{"field": "value"}'
        # Check prompt was called once with the generated schema dictionary
        mock_model.prompt.assert_called_once_with(
            "Test prompt",
            schema=self.DummySchema.model_json_schema(),  # Expect dict
        )

    @patch("vibectl.model_adapter.llm")
    def test_execute_unrelated_attribute_error(self, mock_llm: MagicMock) -> None:
        """Test execute re-raises AttributeError if it's not schema-related."""
        # Setup
        mock_model = Mock()
        mock_model.model_id = "test-attr-err-model"  # Add model_id
        unrelated_error = AttributeError("Some other attribute is missing")
        mock_model.prompt.side_effect = unrelated_error

        # Execute and verify
        adapter = LLMModelAdapter()
        # Expect ValueError with the wrapped message
        with pytest.raises(
            ValueError, match="LLM Execution Error: Some other attribute is missing"
        ):
            adapter.execute(mock_model, "Test prompt", response_model=self.DummySchema)

        # Check prompt was called once (and failed) with the generated schema dictionary
        mock_model.prompt.assert_called_once_with(
            "Test prompt",
            schema=self.DummySchema.model_json_schema(),  # Expect dict
        )


class TestModelEnvironment:
    """Tests for ModelEnvironment."""

    def test_enter_unknown_provider(self) -> None:
        """Test __enter__ does nothing for unknown provider."""
        original_env = dict(os.environ)
        try:
            os.environ.clear()  # Start clean
            config = Mock()
            env = ModelEnvironment("unknown-model", config)
            with env:  # Enter the context
                # Check that no relevant env vars were set
                assert "OPENAI_API_KEY" not in os.environ
                assert "ANTHROPIC_API_KEY" not in os.environ
                assert "OLLAMA_API_KEY" not in os.environ
            # Exit should also leave env clean
            assert not os.environ
        finally:
            os.environ.clear()
            os.environ.update(original_env)

    def test_enter_ollama_provider(self) -> None:
        """Test __enter__ does nothing for ollama provider."""
        original_env = dict(os.environ)
        try:
            os.environ.clear()  # Start clean
            config = Mock()
            # Mock the get_model_key method to simulate having a key
            config.get_model_key.return_value = "dummy-ollama-key"
            env = ModelEnvironment("ollama:llama3", config)
            with env:  # Enter the context
                # Check that no relevant env vars were set
                assert "OPENAI_API_KEY" not in os.environ
                assert "ANTHROPIC_API_KEY" not in os.environ
                assert "OLLAMA_API_KEY" not in os.environ
            # Exit should also leave env clean
            assert not os.environ
        finally:
            os.environ.clear()
            os.environ.update(original_env)
