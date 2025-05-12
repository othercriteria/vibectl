"""Tests for model key management functionality."""

import os
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from unittest.mock import Mock, patch

import pytest

from tests.test_config import MockConfig  # Use MockConfig instead of real Config
from vibectl.model_adapter import (
    LLMMetrics,
    LLMModelAdapter,
    ModelEnvironment,
    validate_model_key_on_startup,
)


class TestModelKeyConfig:
    """Tests for model key configuration functionality."""

    def test_get_model_key_from_environment(self) -> None:
        """Test getting a model key from environment variable."""
        with patch.dict(
            os.environ, {"VIBECTL_OPENAI_API_KEY": "test-openai-key"}, clear=True
        ):
            config = MockConfig()
            key = config.get_model_key("openai")
            assert key == "test-openai-key"

    def test_get_model_key_from_file_env(self) -> None:
        """Test getting a model key from file specified in environment variable."""
        with NamedTemporaryFile(mode="w", delete=False) as temp_file:
            temp_file.write("test-anthropic-key-from-file")
            temp_file.flush()

            try:
                with patch.dict(
                    os.environ,
                    {"VIBECTL_ANTHROPIC_API_KEY_FILE": temp_file.name},
                    clear=True,
                ):
                    config = MockConfig()
                    key = config.get_model_key("anthropic")
                    assert key == "test-anthropic-key-from-file"
            finally:
                # Clean up temp file
                Path(temp_file.name).unlink(missing_ok=True)

    def test_get_model_key_from_config(self) -> None:
        """Test getting a model key from configuration."""
        config = MockConfig()
        config.set_model_key("openai", "test-openai-key-from-config")
        key = config.get_model_key("openai")
        assert key == "test-openai-key-from-config"

    def test_get_model_key_from_config_file(self) -> None:
        """Test getting a model key from configuration key file."""
        with TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)

            # Create a key file
            key_file = config_dir / "anthropic-key.txt"
            key_file.write_text("test-anthropic-key-from-config-file")

            config = MockConfig()
            config.set_model_key_file("anthropic", str(key_file))
            key = config.get_model_key("anthropic")
            assert key == "test-anthropic-key-from-config-file"

    def test_get_model_key_from_legacy_env(self) -> None:
        """Test getting a model key from legacy environment variable."""
        with patch.dict(
            os.environ, {"OPENAI_API_KEY": "test-openai-key-legacy"}, clear=True
        ):
            config = MockConfig()
            # Don't set any config values, only use env var
            config._config["model_keys"] = {}
            config._config["model_key_files"] = {}
            key = config.get_model_key("openai")
            assert key == "test-openai-key-legacy", (
                f"Expected 'test-openai-key-legacy', got '{key}'"
            )

    def test_precedence_order(self) -> None:
        """Test precedence order of key sources."""
        with TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)

            # Create a key file for config
            config_key_file = config_dir / "anthropic-key.txt"
            config_key_file.write_text("test-key-from-config-file")

            # Create a key file for env var
            with NamedTemporaryFile(mode="w", delete=False) as env_key_file:
                env_key_file.write("test-key-from-env-file")
                env_key_file.flush()

                try:
                    # Set up everything to test precedence
                    config = MockConfig()
                    config.set_model_key("anthropic", "test-key-from-config")
                    config.set_model_key_file("anthropic", str(config_key_file))

                    # Test with all options set, VIBECTL_ANTHROPIC_API_KEY should win
                    with patch.dict(
                        os.environ,
                        {
                            "VIBECTL_ANTHROPIC_API_KEY": "test-key-from-env",
                            "VIBECTL_ANTHROPIC_API_KEY_FILE": env_key_file.name,
                            "ANTHROPIC_API_KEY": "legacy-key",
                        },
                        clear=True,
                    ):
                        key = config.get_model_key("anthropic")
                        assert key == "test-key-from-env"

                    # Remove VIBECTL_ANTHROPIC_API_KEY
                    # VIBECTL_ANTHROPIC_API_KEY_FILE should win
                    with patch.dict(
                        os.environ,
                        {
                            "VIBECTL_ANTHROPIC_API_KEY_FILE": env_key_file.name,
                            "ANTHROPIC_API_KEY": "legacy-key",
                        },
                        clear=True,
                    ):
                        key = config.get_model_key("anthropic")
                        assert key == "test-key-from-env-file"

                    # Remove VIBECTL_ANTHROPIC_API_KEY_FILE, config key should win
                    with patch.dict(
                        os.environ, {"ANTHROPIC_API_KEY": "legacy-key"}, clear=True
                    ):
                        key = config.get_model_key("anthropic")
                        assert key == "test-key-from-config"

                    # Test with only config key file and legacy env var
                    config._config["model_keys"]["anthropic"] = None
                    with patch.dict(
                        os.environ, {"ANTHROPIC_API_KEY": "legacy-key"}, clear=True
                    ):
                        key = config.get_model_key("anthropic")
                        assert key == "test-key-from-config-file"

                    # Test with only legacy env var
                    config._config["model_key_files"]["anthropic"] = None
                    with patch.dict(
                        os.environ, {"ANTHROPIC_API_KEY": "legacy-key"}, clear=True
                    ):
                        key = config.get_model_key("anthropic")
                        assert key == "legacy-key"
                finally:
                    # Clean up temp file
                    Path(env_key_file.name).unlink(missing_ok=True)

    def test_invalid_provider(self) -> None:
        """Test getting a key for an invalid provider."""
        config = MockConfig()
        key = config.get_model_key("invalid")
        assert key is None

    def test_set_model_key_invalid_provider(self) -> None:
        """Test setting a key for an invalid provider."""
        config = MockConfig()
        with pytest.raises(ValueError, match="Invalid model provider"):
            config.set_model_key("invalid", "key")

    def test_set_model_key_file_invalid_provider(self) -> None:
        """Test setting a key file for an invalid provider."""
        config = MockConfig()
        with pytest.raises(ValueError, match="Invalid model provider"):
            config.set_model_key_file("invalid", "/path/to/key")

    def test_set_model_key_file_nonexistent_file(self) -> None:
        """Test setting a key file that doesn't exist."""
        config = MockConfig()
        with pytest.raises(ValueError, match="Key file does not exist"):
            config.set_model_key_file("openai", "/nonexistent/path")


class TestModelAdapterWithKeys:
    """Tests for LLMModelAdapter with key management."""

    def test_determine_provider_from_model(self) -> None:
        """Test determining provider from model name."""
        adapter = LLMModelAdapter(MockConfig())

        assert adapter._determine_provider_from_model("gpt-4") == "openai"
        assert adapter._determine_provider_from_model("gpt-3.5-turbo") == "openai"
        assert (
            adapter._determine_provider_from_model("claude-3.7-sonnet") == "anthropic"
        )
        assert adapter._determine_provider_from_model("claude-3.7-opus") == "anthropic"
        assert adapter._determine_provider_from_model("ollama:llama3") == "ollama"
        assert adapter._determine_provider_from_model("unknown-model") is None

    @patch("vibectl.model_adapter.llm")
    def test_environment_setup_for_model(self, mock_llm: Mock) -> None:
        """Test environment setup for model."""
        # Create mock model
        mock_model = Mock()
        mock_llm.get_model.return_value = mock_model

        # Create config with API key
        config = MockConfig()

        # Setup adapter
        adapter = LLMModelAdapter(config)

        # Test with OpenAI model
        original_env = dict(os.environ)
        try:
            # Start with a clean environment
            os.environ.clear()

            with patch.object(config, "get_model_key", return_value="test-openai-key"):
                # Get model
                model = adapter.get_model("gpt-4")

                # Verify API key not leaked into environment after call
                assert "OPENAI_API_KEY" not in os.environ, (
                    f"Environment contains: {list(os.environ.keys())}"
                )

                # Verify model was returned
                assert model is mock_model

                # Verify LLM was called with correct model name
                mock_llm.get_model.assert_called_with("gpt-4")
        finally:
            # Restore original environment
            os.environ.clear()
            os.environ.update(original_env)

    @patch("vibectl.model_adapter.llm")
    def test_api_key_error_message(self, mock_llm: Mock) -> None:
        """Test error message when API key is missing."""
        # Setup LLM to raise an exception
        mock_llm.get_model.side_effect = Exception("API key required")

        # Create config with no API key
        config = MockConfig()

        # Setup adapter with a mock that returns None for API key
        adapter = LLMModelAdapter(config)

        # Test error message
        with patch.object(config, "get_model_key", return_value=None):
            with pytest.raises(ValueError) as exc_info:
                adapter.get_model("gpt-4")

            # Check that the error message mentions API key and how to set it
            error_msg = str(exc_info.value)
            assert "API key for openai not found" in error_msg
            assert "VIBECTL_OPENAI_API_KEY" in error_msg
            assert "model_keys.openai" in error_msg

    @patch("vibectl.model_adapter.llm")
    def test_execute_preserves_environment(self, mock_llm: Mock) -> None:
        """Test that execute preserves the environment."""
        # Setup mock model and response
        mock_model = Mock()
        mock_response = Mock()
        # Explicitly make .text a callable mock
        mock_response.text = Mock(return_value="Test response")
        mock_model.prompt.return_value = mock_response

        # Create config
        config = MockConfig()

        # Setup adapter
        adapter = LLMModelAdapter(config)

        # Save original environment
        original_env = dict(os.environ)
        try:
            # Start with a clean environment plus one variable
            os.environ.clear()
            os.environ["ORIGINAL_VAR"] = "original-value"

            # Combine nested with statements for ruff SIM117
            with (
                patch.object(config, "get_model_key", return_value="test-openai-key"),
                patch.object(adapter, "get_model", return_value=mock_model),
            ):
                # Execute
                response_text, metrics = adapter.execute(mock_model, "Test prompt")

                # Verify response
                assert response_text == "Test response"
                assert isinstance(
                    metrics, LLMMetrics
                )  # Check metrics object is returned

            # Verify environment variable is still there (the core of this test)
            assert "ORIGINAL_VAR" in os.environ
            assert os.environ["ORIGINAL_VAR"] == "original-value"
        finally:
            # Restore original environment
            os.environ.clear()
            os.environ.update(original_env)


class TestModelEnvironmentContextManager:
    """Tests for the ModelEnvironment context manager."""

    def test_context_manager_sets_and_restores_environment(self) -> None:
        """Test that context manager sets and restores environment variables."""
        # Create a mock config
        config = MockConfig()
        config.set_model_key("openai", "test-openai-key")

        # Save original environment
        original_env = dict(os.environ)

        try:
            # Clear environment and test context manager
            os.environ.clear()

            # First verify the key is not in the environment
            assert "OPENAI_API_KEY" not in os.environ

            # Use the context manager
            with ModelEnvironment("gpt-4", config):
                # Key should be set inside the with block
                assert "OPENAI_API_KEY" in os.environ
                assert os.environ["OPENAI_API_KEY"] == "test-openai-key"

            # Key should be cleaned up after the with block
            assert "OPENAI_API_KEY" not in os.environ

        finally:
            # Restore original environment
            os.environ.clear()
            os.environ.update(original_env)

    def test_context_manager_with_preexisting_env_var(self) -> None:
        """Test that context manager properly restores preexisting env vars."""
        # Create a mock config
        config = MockConfig()
        config.set_model_key("openai", "test-openai-key-from-config")

        # Save original environment
        original_env = dict(os.environ)

        try:
            # Set up environment with existing key
            os.environ.clear()
            os.environ["OPENAI_API_KEY"] = "original-key-value"

            # Use the context manager
            with ModelEnvironment("gpt-4", config):
                # Key should be overwritten inside the with block
                assert os.environ["OPENAI_API_KEY"] == "test-openai-key-from-config"

            # Original key should be restored after the with block
            assert os.environ["OPENAI_API_KEY"] == "original-key-value"

        finally:
            # Restore original environment
            os.environ.clear()
            os.environ.update(original_env)

    def test_context_manager_with_exception(self) -> None:
        """Test that context manager restores environment even if exception occurs."""
        # Create a mock config
        config = MockConfig()
        config.set_model_key("anthropic", "test-anthropic-key")

        # Save original environment
        original_env = dict(os.environ)

        try:
            # Clear environment and test context manager
            os.environ.clear()

            # Try to use the context manager with an exception
            try:
                with ModelEnvironment("claude-3.7-sonnet", config):
                    assert "ANTHROPIC_API_KEY" in os.environ
                    assert os.environ["ANTHROPIC_API_KEY"] == "test-anthropic-key"
                    raise ValueError("Test exception")
            except ValueError:
                # Exception should propagate but environment should be cleaned up
                pass

            # Key should be cleaned up despite the exception
            assert "ANTHROPIC_API_KEY" not in os.environ

        finally:
            # Restore original environment
            os.environ.clear()
            os.environ.update(original_env)


class TestModelKeyValidation:
    """Tests for model key validation functionality."""

    def test_validate_model_key_missing_key(self) -> None:
        """Test validation when key is missing."""
        config = MockConfig()
        # Ensure we don't have a default key
        config._config["model_keys"] = {"openai": None}
        # Patch environment to ensure no API key is set
        with patch.dict(
            os.environ, {"VIBECTL_OPENAI_API_KEY": "", "OPENAI_API_KEY": ""}, clear=True
        ):
            adapter = LLMModelAdapter(config)
            # Test with no key configured
            warning = adapter.validate_model_key("gpt-4")
            assert warning is not None
            assert "No API key found for openai" in warning
            assert "VIBECTL_OPENAI_API_KEY" in warning

    def test_validate_model_key_with_valid_key(self) -> None:
        """Test validation with a valid key."""
        config = MockConfig()
        config.set_model_key("openai", "sk-1234567890abcdefghijklmnopqrstuvwxyz")
        adapter = LLMModelAdapter(config)

        # Test with valid key format
        warning = adapter.validate_model_key("gpt-4")
        assert warning is None

    def test_validate_model_key_with_invalid_format(self) -> None:
        """Test validation with an invalid key format."""
        config = MockConfig()
        # The validation logic is warning = NOT(key.startswith("sk-") OR len(key) < 20)
        # So we need a key that doesn't start with sk- AND is NOT less than 20 chars
        config.set_model_key(
            "anthropic", "invalid-key-that-is-exactly-twenty-chars-long"
        )
        adapter = LLMModelAdapter(config)

        # Now the key doesn't start with sk- AND is long (>20 chars)
        # So warning should be given
        warning = adapter.validate_model_key("claude-3.7-sonnet")
        assert warning is not None
        assert "format looks invalid" in warning

        # But if key is short (<20 chars), no warning even if it doesn't start with sk-
        config.set_model_key("anthropic", "short-key")
        warning = adapter.validate_model_key("claude-3.7-sonnet")
        assert warning is None

        # And if it starts with sk-, no warning even if it's long
        config.set_model_key(
            "anthropic", "sk-valid-key-that-is-exactly-thirty-chars-long"
        )
        warning = adapter.validate_model_key("claude-3.7-sonnet")
        assert warning is None

    def test_validate_model_key_with_ollama(self) -> None:
        """Test validation with Ollama model."""
        config = MockConfig()
        adapter = LLMModelAdapter(config)

        # Ollama typically doesn't need a key for local usage
        warning = adapter.validate_model_key("ollama:llama3")
        assert warning is None

    def test_validate_model_key_unknown_provider(self) -> None:
        """Test validation with unknown provider."""
        config = MockConfig()
        adapter = LLMModelAdapter(config)

        # Test with unknown model name
        warning = adapter.validate_model_key("unknown-model")
        assert warning is not None
        assert "Unknown model provider" in warning

    @patch("vibectl.model_adapter.get_model_adapter")
    def test_validate_model_key_on_startup(self, mock_get_adapter: Mock) -> None:
        """Test the startup validation function."""
        # Create mock adapter
        mock_adapter = Mock()
        mock_adapter.validate_model_key.return_value = "Test warning"
        mock_get_adapter.return_value = mock_adapter

        # Run validation
        warning = validate_model_key_on_startup("test-model")
        assert warning == "Test warning"

        # Verify adapter methods were called correctly
        mock_get_adapter.assert_called_once()
        mock_adapter.validate_model_key.assert_called_once_with("test-model")
