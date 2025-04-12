"""Debug tests for model adapter environment handling.

This module contains tests to debug and diagnose issues with
how the model adapter handles API keys and environment variables.
"""

import os
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vibectl.config import Config
from vibectl.model_adapter import LLMModelAdapter


@pytest.fixture
def test_config() -> Generator[Config, None, None]:
    """Create a test configuration with a temporary directory."""
    # Create a temporary config directory
    test_dir = Path("/tmp/vibectl-test-debug-" + os.urandom(4).hex())
    test_dir.mkdir(parents=True, exist_ok=True)

    # Initialize config with test directory
    config = Config(base_dir=test_dir)

    # Return the config for use in tests
    yield config


def test_debug_environment_restore(test_config: Config) -> None:
    """Debug test to verify environment variables are properly restored."""
    # Track changes to environment
    env_changes: dict[str, str | None] = {"before": None, "during": None, "after": None}

    # Save original environment state
    original_env = os.environ.get("ANTHROPIC_API_KEY")
    env_changes["before"] = original_env

    # Set up mock LLM model
    mock_model = MagicMock()

    def track_env(*args: str, **kwargs: str) -> MagicMock:
        """Capture environment during execution."""
        env_changes["during"] = os.environ.get("ANTHROPIC_API_KEY")
        return mock_model

    # Create adapter with mocked llm.get_model
    with patch("llm.get_model", side_effect=track_env):
        # Set a test key in the config
        test_config.set_model_key("anthropic", "debug-test-key")

        # Create a model adapter instance
        adapter = LLMModelAdapter(test_config)

        # Get a Claude model which should set the ANTHROPIC_API_KEY
        try:
            adapter.get_model("claude-3.7-sonnet")
        except Exception:
            # Ignore any exceptions, we just want to check environment handling
            pass

    # Check environment after adapter operation
    env_changes["after"] = os.environ.get("ANTHROPIC_API_KEY")

    # Print debug information
    print("\nEnvironment variable tracking:")
    print(f"  Before adapter: {env_changes['before']}")
    print(f"  During adapter: {env_changes['during']}")
    print(f"  After adapter:  {env_changes['after']}")

    # Assert environment was properly restored
    assert env_changes["before"] == env_changes["after"]
    assert env_changes["during"] == "debug-test-key"


def test_debug_environment_isolation(test_config: Config) -> None:
    """Debug test to verify environment isolation between adapter instances."""
    # Create two model adapters with different configs
    config1 = test_config
    config2 = Config(base_dir=test_config.config_dir)

    # Set different API keys in each config
    config1.set_model_key("anthropic", "test-key-1")
    config2.set_model_key("anthropic", "test-key-2")

    # Track which keys were used
    keys_used: dict[str, str | None] = {
        "adapter1": None,
        "adapter2": None,
    }

    # Mock for first adapter
    mock_model1 = MagicMock()

    def track_env1(*args: str, **kwargs: str) -> MagicMock:
        keys_used["adapter1"] = os.environ.get("ANTHROPIC_API_KEY")
        return mock_model1

    # Mock for second adapter
    mock_model2 = MagicMock()

    def track_env2(*args: str, **kwargs: str) -> MagicMock:
        keys_used["adapter2"] = os.environ.get("ANTHROPIC_API_KEY")
        return mock_model2

    # Test the first adapter
    with patch("llm.get_model", side_effect=track_env1):
        adapter1 = LLMModelAdapter(config1)
        try:
            adapter1.get_model("claude-3.7-sonnet")
        except Exception:
            pass

    # Test the second adapter
    with patch("llm.get_model", side_effect=track_env2):
        adapter2 = LLMModelAdapter(config2)
        try:
            adapter2.get_model("claude-3.7-sonnet")
        except Exception:
            pass

    # Print debug information
    print("\nEnvironment isolation test:")
    print(f"  Adapter 1 used key: {keys_used['adapter1']}")
    print(f"  Adapter 2 used key: {keys_used['adapter2']}")

    # Verify each adapter used its own key
    assert keys_used["adapter1"] == "test-key-1"
    assert keys_used["adapter2"] == "test-key-2"


def test_debug_adapter_execute_environment(test_config: Config) -> None:
    """Debug test for how adapter.execute handles the environment."""
    # Set API key in config
    test_config.set_model_key("anthropic", "execute-test-key")

    # Create a model adapter
    adapter = LLMModelAdapter(test_config)

    # Track environment states
    env_states: dict[str, str | None] = {
        "before_get_model": os.environ.get("ANTHROPIC_API_KEY"),
        "during_get_model": None,
        "after_get_model": None,
        "during_execute": None,
        "after_execute": None,
    }

    # Create mock for model
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text.return_value = "Test response"
    mock_model.prompt.return_value = mock_response
    mock_model.name = "claude-3.7-sonnet"

    # Mock llm.get_model to track environment
    def track_get_model_env(*args: str, **kwargs: str) -> MagicMock:
        env_states["during_get_model"] = os.environ.get("ANTHROPIC_API_KEY")
        return mock_model

    # Mock prompt to track environment
    def track_execute_env(prompt_text: str) -> MagicMock:
        env_states["during_execute"] = os.environ.get("ANTHROPIC_API_KEY")
        return mock_response

    # Apply mocks
    with patch("llm.get_model", side_effect=track_get_model_env):
        # Get model
        model = adapter.get_model("claude-3.7-sonnet")

        # Check environment after get_model
        env_states["after_get_model"] = os.environ.get("ANTHROPIC_API_KEY")

        # Mock model.prompt
        mock_model.prompt = track_execute_env

        # Execute with model
        adapter.execute(model, "Test prompt")

        # Check environment after execute
        env_states["after_execute"] = os.environ.get("ANTHROPIC_API_KEY")

    # Print debug info
    print("\nDebug API Key Environment State:")
    for stage, value in env_states.items():
        print(f"  {stage}: {value}")

    # Verify environment was handled correctly in each stage
    assert env_states["before_get_model"] != "execute-test-key"
    assert env_states["during_get_model"] == "execute-test-key"
    assert env_states["after_get_model"] != "execute-test-key"
    assert env_states["during_execute"] == "execute-test-key"
    assert env_states["after_execute"] != "execute-test-key"
