"""Tests for model adapter."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.model_adapter import (
    LLMModelAdapter,
    ModelAdapter,
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
        mock_response.text.return_value = "Test response"
        mock_model.prompt.return_value = mock_response

        # Execute
        adapter = LLMModelAdapter()
        response = adapter.execute(mock_model, "Test prompt")

        # Verify
        assert response == "Test response"
        mock_model.prompt.assert_called_once_with("Test prompt")
        mock_response.text.assert_called_once()

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
        mock_model.prompt.assert_called_once_with("Test prompt")

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
        assert "Error during model execution" in str(exc_info.value)
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
        
        # Create mock responses with text() methods returning different types
        mock_response_int = Mock()
        mock_response_int.text.return_value = 42
        
        mock_response_float = Mock()
        mock_response_float.text.return_value = 3.14
        
        mock_response_bool = Mock()
        mock_response_bool.text.return_value = True
        
        mock_response_none = Mock()
        mock_response_none.text.return_value = None
        
        # Test each response type
        adapter = LLMModelAdapter()
        
        # Test integer response
        mock_model.prompt.return_value = mock_response_int
        response_int = adapter.execute(mock_model, "Integer prompt")
        assert response_int == 42  # The adapter returns the actual value, not a string conversion
        
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
