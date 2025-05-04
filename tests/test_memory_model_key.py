"""Tests for memory integration with model key management.

This module tests how memory functions handle API keys when interacting with models.
"""

import os
from collections.abc import Generator
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from pydantic import BaseModel

from vibectl.config import Config
from vibectl.memory import update_memory
from vibectl.model_adapter import (
    ModelAdapter,
    set_model_adapter,
)


@pytest.fixture
def test_config() -> Generator[Config, None, None]:
    """Create a test configuration with a temporary directory."""
    # Create a temporary config directory
    test_dir = Path("/tmp/vibectl-test-" + os.urandom(4).hex())
    test_dir.mkdir(parents=True, exist_ok=True)

    # Initialize config with test directory
    config = Config(base_dir=test_dir)

    # Ensure memory is enabled
    config.set("memory_enabled", True)

    # Return the config for use in tests
    yield config


def test_memory_with_anthropic_api_key(test_config: Config) -> None:
    """Test memory correctly uses Anthropic API key during updates."""
    # Set a mock API key in the config
    test_config.set_model_key("anthropic", "test-anthropic-key")

    # Track environment variables that are set
    set_env_vars: dict[str, str] = {}

    # Create a more realistic model adapter mock
    class MockLLMAdapter(ModelAdapter):
        """Mock adapter that simulates environment variable handling
        like the real adapter."""

        def get_model(self, model_name: str) -> Mock:
            """Get a model with environment setup."""
            # Determine provider like the real adapter
            provider = None
            if model_name.startswith("claude-"):
                provider = "anthropic"
            elif model_name.startswith("gpt-"):
                provider = "openai"

            # Set environment if provider is recognized
            if provider:
                key = test_config.get_model_key(provider)
                if key:
                    # Simulate environment setting
                    env_var = f"{provider.upper()}_API_KEY"
                    os.environ[env_var] = key

            # Return mock model
            mock_model = Mock()
            return mock_model

        def execute(
            self,
            model: Mock,
            prompt_text: str,
            response_model: type[BaseModel] | None = None,
        ) -> str:
            """Execute with environment capture."""
            # Capture API key from environment
            set_env_vars["ANTHROPIC_API_KEY"] = os.environ.get("ANTHROPIC_API_KEY", "")

            # Simulate cleanup (like the real adapter)
            if "ANTHROPIC_API_KEY" in os.environ:
                del os.environ["ANTHROPIC_API_KEY"]

            return "Updated memory content"

        def validate_model_key(self, model_name: str) -> str | None:
            """Mock implementation of validate_model_key."""
            return None

        def validate_model_name(self, model_name: str) -> str | None:
            """Mock implementation for the new abstract method."""
            return None

    # Create our adapter instance
    mock_adapter = MockLLMAdapter()
    set_model_adapter(mock_adapter)

    # Apply the mocked adapter
    with patch("vibectl.memory.get_model_adapter", return_value=mock_adapter):
        # Call update_memory with a Claude model
        update_memory(
            command="kubectl get pods",
            command_output="No resources found",
            vibe_output="No pods found",
            # Claude model should use Anthropic key
            model_name="claude-3.7-sonnet",
            config=test_config,
        )

    # Verify that the adapter attempted to use our test key
    assert set_env_vars.get("ANTHROPIC_API_KEY") == "test-anthropic-key"

    # Verify the API key is not leaked in the environment after the function returns
    assert os.environ.get("ANTHROPIC_API_KEY") != "test-anthropic-key"


def test_memory_with_openai_api_key(test_config: Config) -> None:
    """Test memory correctly uses OpenAI API key during updates."""
    # Set a mock API key in the config
    test_config.set_model_key("openai", "test-openai-key")

    # Track environment variables that are set
    set_env_vars: dict[str, str] = {}

    # Create a more realistic model adapter mock
    class MockLLMAdapter(ModelAdapter):
        """Mock adapter that simulates environment variable handling
        like the real adapter."""

        def get_model(self, model_name: str) -> Mock:
            """Get a model with environment setup."""
            # Determine provider like the real adapter
            provider = None
            if model_name.startswith("claude-"):
                provider = "anthropic"
            elif model_name.startswith("gpt-"):
                provider = "openai"

            # Set environment if provider is recognized
            if provider:
                key = test_config.get_model_key(provider)
                if key:
                    # Simulate environment setting
                    env_var = f"{provider.upper()}_API_KEY"
                    os.environ[env_var] = key

            # Return mock model
            mock_model = Mock()
            return mock_model

        def execute(
            self,
            model: Mock,
            prompt_text: str,
            response_model: type[BaseModel] | None = None,
        ) -> str:
            """Execute with environment capture."""
            # Capture API key from environment
            set_env_vars["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY", "")

            # Simulate cleanup (like the real adapter)
            if "OPENAI_API_KEY" in os.environ:
                del os.environ["OPENAI_API_KEY"]

            return "Updated memory content"

        def validate_model_key(self, model_name: str) -> str | None:
            """Mock implementation of validate_model_key."""
            return None

        def validate_model_name(self, model_name: str) -> str | None:
            """Mock implementation for the new abstract method."""
            return None

    # Create our adapter instance
    mock_adapter = MockLLMAdapter()
    set_model_adapter(mock_adapter)

    # Apply the mocked adapter
    with patch("vibectl.memory.get_model_adapter", return_value=mock_adapter):
        # Call update_memory with a GPT model
        update_memory(
            command="kubectl get pods",
            command_output="No resources found",
            vibe_output="No pods found",
            model_name="gpt-4",  # GPT model should use OpenAI key
            config=test_config,
        )

    # Verify that the adapter attempted to use our test key
    assert set_env_vars.get("OPENAI_API_KEY") == "test-openai-key"

    # Verify the API key is not leaked in the environment after the function returns
    assert os.environ.get("OPENAI_API_KEY") != "test-openai-key"


def test_memory_update_missing_api_key(test_config: Config) -> None:
    """Test memory update behavior when API key is missing."""
    # Create a mock adapter that simulates a missing API key error
    mock_adapter = Mock(spec=ModelAdapter)
    mock_model = Mock()

    # Configure the adapter to raise an appropriate error
    mock_adapter.get_model.return_value = mock_model
    mock_adapter.execute.side_effect = ValueError(
        "Failed to get model 'claude-3.7-sonnet': API key for anthropic not found."
    )

    # Apply the mocked adapter
    with (
        patch("vibectl.memory.get_model_adapter", return_value=mock_adapter),
        pytest.raises(ValueError) as excinfo,
    ):
        # Call update_memory with a model that requires an API key
        update_memory(
            command="kubectl get pods",
            command_output="No resources found",
            vibe_output="No pods found",
            model_name="claude-3.7-sonnet",
            config=test_config,
        )

    # Verify the error message contains information about the missing API key
    assert "API key for anthropic not found" in str(excinfo.value)


def test_memory_update_with_environment_key(test_config: Config) -> None:
    """Test memory update when key is provided via environment."""
    # Save original environment
    original_env = os.environ.get("ANTHROPIC_API_KEY")

    try:
        # Set environment variable with test key
        os.environ["ANTHROPIC_API_KEY"] = "env-test-key"

        # Track which key was actually used
        used_key: list[str | None] = [None]

        # Create a mock adapter that uses the environment
        mock_adapter = Mock(spec=ModelAdapter)
        mock_model = Mock()

        def verify_env(*args: str, **kwargs: str) -> str:
            """Capture the API key during execution."""
            used_key[0] = os.environ.get("ANTHROPIC_API_KEY")
            return "Updated memory from environment key"

        mock_adapter.get_model.return_value = mock_model
        mock_adapter.execute.side_effect = verify_env

        # Apply the mocked adapter
        with patch("vibectl.memory.get_model_adapter", return_value=mock_adapter):
            # Call update_memory
            update_memory(
                command="kubectl get pods",
                command_output="output",
                vibe_output="vibe",
                model_name="claude-3.7-sonnet",
                config=test_config,
            )

        # Verify the environment key was used
        assert used_key[0] == "env-test-key"

    finally:
        # Restore original environment
        if original_env is not None:
            os.environ["ANTHROPIC_API_KEY"] = original_env
        else:
            os.environ.pop("ANTHROPIC_API_KEY", None)
