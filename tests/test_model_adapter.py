"""Tests for model adapter."""

import os
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
from pydantic import BaseModel

from vibectl.model_adapter import (
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
        mock_llm.get_model.return_value = mock_model

        # Execute
        adapter = LLMModelAdapter()
        model = adapter.get_model("test-model")

        # Verify
        assert model is mock_model
        mock_llm.get_model.assert_called_once_with("test-model")

    @patch("vibectl.model_adapter.llm")
    def test_get_model_caching(self, mock_llm: MagicMock) -> None:
        """Test model caching."""
        # Setup
        mock_model = Mock()
        mock_llm.get_model.return_value = mock_model

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
        mock_llm.get_model.side_effect = Exception("Model error")

        # Execute and verify
        adapter = LLMModelAdapter()
        with pytest.raises(ValueError) as exc_info:
            adapter.get_model("test-model")

        assert "Failed to get model 'test-model'" in str(exc_info.value)
        mock_llm.get_model.assert_called_once_with("test-model")

    @patch("vibectl.model_adapter.llm")
    def test_execute(self, mock_llm: MagicMock) -> None:
        """Test executing a prompt on a model."""
        # Setup
        mock_model = Mock()
        mock_response = Mock()
        # Explicitly make .text a callable mock
        mock_response.text = Mock(return_value="Test response")
        mock_model.prompt.return_value = mock_response

        # Execute
        adapter = LLMModelAdapter()
        response = adapter.execute(mock_model, "Test prompt")

        # Verify
        assert response == "Test response"
        mock_model.prompt.assert_called_once_with("Test prompt", schema=None)

    @patch("vibectl.model_adapter.llm")
    def test_execute_string_response(self, mock_llm: MagicMock) -> None:
        """Test handling string responses."""
        # Setup
        mock_model = Mock()
        mock_model.prompt.return_value = "Test response"

        # Execute
        adapter = LLMModelAdapter()
        response = adapter.execute(mock_model, "Test prompt")

        # Verify
        assert response == "Test response"
        mock_model.prompt.assert_called_once_with("Test prompt", schema=None)

    @patch("vibectl.model_adapter.llm")
    def test_execute_error(self, mock_llm: MagicMock) -> None:
        """Test error handling during execution."""
        # Setup
        mock_model = Mock()
        mock_model.prompt.side_effect = Exception("Test error")

        # Execute
        adapter = LLMModelAdapter()
        with pytest.raises(ValueError) as exc_info:
            adapter.execute(mock_model, "Test prompt")

        # Verify
        assert "Error executing prompt: Test error" in str(exc_info.value)
        mock_model.prompt.assert_called_once_with("Test prompt", schema=None)

    @patch("vibectl.model_adapter.llm")
    def test_execute_with_type_casting(self, mock_llm: MagicMock) -> None:
        """Test type casting behavior in the execute method.

        This tests the adapter's ability to properly handle and cast
        responses from the model that have a text() method returning
        different types.
        """
        # Setup
        mock_model = Mock()

        # Create mock responses with text() methods returning different types
        mock_response_int = Mock()
        # Explicitly make .text a callable mock
        mock_response_int.text = Mock(return_value=42)

        mock_response_float = Mock()
        # Explicitly make .text a callable mock
        mock_response_float.text = Mock(return_value=3.14)

        mock_response_bool = Mock()
        # Explicitly make .text a callable mock
        mock_response_bool.text = Mock(return_value=True)

        mock_response_none = Mock()
        # Explicitly make .text a callable mock
        mock_response_none.text = Mock(return_value=None)

        # Test each response type
        adapter = LLMModelAdapter()

        # Test integer response
        mock_model.prompt.return_value = mock_response_int
        response_int = adapter.execute(mock_model, "Integer prompt")
        assert response_int == 42

        # Test float response
        mock_model.prompt.return_value = mock_response_float
        response_float = adapter.execute(mock_model, "Float prompt")
        assert response_float == 3.14

        # Test boolean response
        mock_model.prompt.return_value = mock_response_bool
        response_bool = adapter.execute(mock_model, "Boolean prompt")
        assert response_bool is True

        # Test None response
        mock_model.prompt.return_value = mock_response_none
        response_none = adapter.execute(mock_model, "None prompt")
        assert response_none is None

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
        ) -> str:
            raise NotImplementedError()

        def validate_model_key(self, model_name: str) -> str | None:
            raise NotImplementedError()

    adapter = DummyAdapter()
    with pytest.raises(NotImplementedError):
        adapter.get_model("foo")
    with pytest.raises(NotImplementedError):
        adapter.execute(None, "bar")
    with pytest.raises(NotImplementedError):
        adapter.validate_model_key("baz")


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
