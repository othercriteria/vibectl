"""Tests for memory management functionality.

The memory.py module provides functions to manage the memory feature,
allowing vibectl to maintain context across commands.
"""

from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest

from vibectl.config import Config
from vibectl.memory import (
    clear_memory,
    disable_memory,
    enable_memory,
    get_memory,
    include_memory_in_prompt,
    is_memory_enabled,
    set_memory,
    update_memory,
)


@patch("vibectl.memory.Config")
def test_get_memory(mock_config_class: Mock) -> None:
    """Test retrieving memory from config."""
    # Setup mock
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_config.get.return_value = "Test memory content"

    # Execute
    result = get_memory()

    # Assert
    assert result == "Test memory content"
    mock_config.get.assert_called_once_with("memory", "")


@patch("vibectl.memory.Config")
def test_get_memory_with_config(mock_config_class: Mock) -> None:
    """Test retrieving memory with provided config."""
    # Setup
    mock_config = Mock()
    mock_config.get.return_value = "Test memory content"

    # Execute
    result = get_memory(mock_config)

    # Assert
    assert result == "Test memory content"
    mock_config.get.assert_called_once_with("memory", "")
    mock_config_class.assert_not_called()


@patch("vibectl.memory.Config")
def test_is_memory_enabled(mock_config_class: Mock) -> None:
    """Test checking if memory is enabled."""
    # Setup mock
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_config.get.return_value = True

    # Execute
    result = is_memory_enabled()

    # Assert
    assert result is True
    mock_config.get.assert_called_once_with("memory_enabled", True)


@patch("vibectl.memory.Config")
def test_is_memory_enabled_with_config(mock_config_class: Mock) -> None:
    """Test checking if memory is enabled with provided config."""
    # Setup
    mock_config = Mock()
    mock_config.get.return_value = False

    # Execute
    result = is_memory_enabled(mock_config)

    # Assert
    assert result is False
    mock_config.get.assert_called_once_with("memory_enabled", True)
    mock_config_class.assert_not_called()


@patch("vibectl.memory.Config")
def test_set_memory(mock_config_class: Mock) -> None:
    """Test setting memory in config."""
    # Setup mock
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    # Return an integer for memory_max_chars to avoid type error
    mock_config.get.return_value = 500

    # Execute
    set_memory("New memory content")

    # Assert
    mock_config.set.assert_called_once_with("memory", "New memory content")
    mock_config.save.assert_called_once()


@patch("vibectl.memory.Config")
def test_set_memory_truncation(mock_config_class: Mock) -> None:
    """Test memory content truncation when it exceeds max length."""
    # Setup
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_config.get.return_value = 5  # max_chars
    memory_text = "This is too long"

    # Execute
    set_memory(memory_text)

    # Assert
    mock_config.set.assert_called_once_with("memory", "This ")
    mock_config.save.assert_called_once()


@patch("vibectl.memory.Config")
def test_enable_memory(mock_config_class: Mock) -> None:
    """Test enabling memory in config."""
    # Setup mock
    mock_config = Mock()
    mock_config_class.return_value = mock_config

    # Execute
    enable_memory()

    # Assert
    mock_config.set.assert_called_once_with("memory_enabled", True)
    mock_config.save.assert_called_once()


@patch("vibectl.memory.Config")
def test_disable_memory(mock_config_class: Mock) -> None:
    """Test disabling memory in config."""
    # Setup mock
    mock_config = Mock()
    mock_config_class.return_value = mock_config

    # Execute
    disable_memory()

    # Assert
    mock_config.set.assert_called_once_with("memory_enabled", False)
    mock_config.save.assert_called_once()


@pytest.mark.fast
@patch("vibectl.memory.Config")
def test_clear_memory(mock_config_class: Mock) -> None:
    """Test clearing memory content."""
    # Setup mock
    mock_config = Mock()
    mock_config_class.return_value = mock_config

    # Execute
    clear_memory()

    # Assert
    mock_config.set.assert_called_once_with("memory", "")
    mock_config.save.assert_called_once()


@patch("vibectl.memory.memory_update_prompt")
@patch("vibectl.memory.get_model_adapter")
def test_update_memory(mock_get_adapter: Mock, mock_update_prompt: Mock) -> None:
    """Test memory update with command and response."""
    # Setup mocks
    mock_config = Mock()

    # Configure mock_config.get to return specific values based on the key
    def mock_config_get_side_effect(key: str, default: Any = None) -> Any:
        if key == "memory_enabled":
            return True
        if key == "memory_max_chars":
            return 500  # Sufficiently large limit
        return default

    mock_config.get.side_effect = mock_config_get_side_effect

    # Mock adapter and its model reference
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model

    # Setup prompt template
    mock_update_prompt.return_value = "Test memory update prompt"

    # Setup model response to be a tuple (text, metrics)
    mock_response_text = "Updated memory content"
    mock_adapter.execute_and_log_metrics.return_value = (
        mock_response_text,
        None,  # Metrics can be None for this test
    )

    # Create a spy on set_memory to verify what's actually being passed
    with (
        patch("vibectl.memory.Config", return_value=mock_config),
    ):
        # Call update_memory
        update_memory(
            command="kubectl get pods",
            command_output="pod1 Running\npod2 Error",
            vibe_output="Pods are in mixed state",
            model_name="test-model",
        )

    # Verify the prompt was created
    mock_update_prompt.assert_called_once_with(
        "kubectl get pods",
        "pod1 Running\npod2 Error",
        "Pods are in mixed state",
        mock_config,
    )

    # Verify the adapter was used correctly
    mock_get_adapter.assert_called_once()
    mock_adapter.get_model.assert_called_once_with("test-model")
    mock_adapter.execute_and_log_metrics.assert_called_once()

    # Verify memory was updated via the mock_config object
    # The real set_memory calls cfg.set()
    mock_config.set.assert_called_once_with("memory", mock_response_text)
    mock_config.save.assert_called_once()  # Also verify save was called


@patch("vibectl.memory.is_memory_enabled")
def test_update_memory_disabled(mock_is_enabled: Mock) -> None:
    """Test update_memory when memory is disabled."""
    # Setup
    mock_is_enabled.return_value = False

    # Execute
    update_memory("command", "output", "vibe_output")

    # Assert
    mock_is_enabled.assert_called_once()


@patch("vibectl.memory.is_memory_enabled")
@patch("vibectl.memory.get_memory")
def test_include_memory_in_prompt_disabled(
    mock_get_memory: Mock, mock_is_enabled: Mock
) -> None:
    """Test include_memory_in_prompt when memory is disabled."""
    # Setup
    mock_is_enabled.return_value = False
    prompt_template = "Test prompt"

    # Execute
    result = include_memory_in_prompt(prompt_template)

    # Assert
    assert result == prompt_template
    mock_is_enabled.assert_called_once()
    mock_get_memory.assert_not_called()


@patch("vibectl.memory.is_memory_enabled")
@patch("vibectl.memory.get_memory")
def test_include_memory_in_prompt_empty(
    mock_get_memory: Mock, mock_is_enabled: Mock
) -> None:
    """Test include_memory_in_prompt when memory is empty."""
    # Setup
    mock_is_enabled.return_value = True
    mock_get_memory.return_value = ""
    prompt_template = "Test prompt"

    # Execute
    result = include_memory_in_prompt(prompt_template)

    # Assert
    assert result == prompt_template
    mock_is_enabled.assert_called_once()
    mock_get_memory.assert_called_once()


@patch("vibectl.memory.is_memory_enabled")
@patch("vibectl.memory.get_memory")
def test_include_memory_in_prompt_with_important(
    mock_get_memory: Mock, mock_is_enabled: Mock
) -> None:
    """Test include_memory_in_prompt with 'Important:' marker."""
    # Setup
    mock_is_enabled.return_value = True
    mock_get_memory.return_value = "Test memory"
    prompt_template = "Some text\nImportant:\nMore text"
    expected = "Some text\n\nMemory context:\nTest memory\n\nImportant:\nMore text"

    # Execute
    result = include_memory_in_prompt(prompt_template)

    # Assert
    assert result == expected
    mock_is_enabled.assert_called_once()
    mock_get_memory.assert_called_once()


@patch("vibectl.memory.is_memory_enabled")
@patch("vibectl.memory.get_memory")
def test_include_memory_in_prompt_with_example_format(
    mock_get_memory: Mock, mock_is_enabled: Mock
) -> None:
    """Test include_memory_in_prompt with 'Example format:' marker."""
    # Setup
    mock_is_enabled.return_value = True
    mock_get_memory.return_value = "Test memory"
    prompt_template = "Some text\nExample format:\nMore text"
    expected = "Some text\n\nMemory context:\nTest memory\n\nExample format:\nMore text"

    # Execute
    result = include_memory_in_prompt(prompt_template)

    # Assert
    assert result == expected


@patch("vibectl.memory.is_memory_enabled")
@patch("vibectl.memory.get_memory")
def test_include_memory_in_prompt_with_callable(
    mock_get_memory: Mock, mock_is_enabled: Mock
) -> None:
    """Test include_memory_in_prompt with callable prompt template."""
    # Setup
    mock_is_enabled.return_value = True
    mock_get_memory.return_value = "Test memory"

    def prompt_callable() -> str:
        return "Some text\nExample format:\nMore text"

    expected = "Some text\n\nMemory context:\nTest memory\n\nExample format:\nMore text"

    # Execute
    result = include_memory_in_prompt(prompt_callable)

    # Assert
    assert result == expected


@patch("vibectl.memory.is_memory_enabled")
@patch("vibectl.memory.get_memory")
def test_include_memory_in_prompt_no_marker(
    mock_get_memory: Mock, mock_is_enabled: Mock
) -> None:
    """Test include_memory_in_prompt when no marker is found in prompt."""
    # Setup
    mock_is_enabled.return_value = True
    mock_get_memory.return_value = "Memory content"
    prompt_template = "This is a prompt with no specific marker for memory insertion."

    # Execute
    result = include_memory_in_prompt(prompt_template)

    # Assert
    assert "Memory context:\nMemory content" in result
    assert result.endswith(prompt_template)
    mock_is_enabled.assert_called_once()
    mock_get_memory.assert_called_once()


@patch("vibectl.memory.is_memory_enabled")
@patch("vibectl.memory.get_memory")
def test_include_memory_in_prompt_with_example_inputs(
    mock_get_memory: Mock, mock_is_enabled: Mock
) -> None:
    """Test include_memory_in_prompt with the 'Example inputs' marker."""
    # Setup
    mock_is_enabled.return_value = True
    mock_get_memory.return_value = "Memory content"
    prompt_template = """Prompt intro.

Example inputs and outputs:
Input: x
Output: y"""

    # Execute
    result = include_memory_in_prompt(prompt_template)

    # Assert
    assert "Memory context:\nMemory content" in result
    assert "Example inputs and outputs:" in result
    mock_is_enabled.assert_called_once()
    mock_get_memory.assert_called_once()


def test_test_isolation_doesnt_impact_real_config() -> None:
    """Test that tests use isolated config.

    This test verifies that the config system correctly isolates test environments.
    """
    import os

    # Save the current environment variable
    original_env = os.environ.get("VIBECTL_CONFIG_DIR")

    try:
        # Setup test config directory with more mocks
        with (
            patch("vibectl.config.Path.home") as mock_home,
            patch("vibectl.config.Path.mkdir") as mock_mkdir,
            patch("vibectl.config.Path.exists") as mock_exists,
            patch("vibectl.config.Config._load_config") as mock_load_config,
        ):
            # Mock home directory to a test location
            mock_home.return_value = Path("/mock/home")
            # Prevent actual mkdir operations
            mock_mkdir.return_value = None
            # Pretend the config file exists
            mock_exists.return_value = True
            # Prevent actual file loading
            mock_load_config.return_value = None

            # Create first config instance with test environment
            os.environ["VIBECTL_CONFIG_DIR"] = "/mock/test-config"
            test_config = Config()
            assert test_config.config_dir == Path("/mock/test-config")
            assert "test" in str(test_config.config_dir)

            # Clear the environment variable to check real config behavior
            del os.environ["VIBECTL_CONFIG_DIR"]

            # Create second config instance without test environment
            real_config = Config()
            # Verify different paths
            assert real_config.config_dir == Path("/mock/home/.vibectl")
            assert test_config.config_dir != real_config.config_dir

            # Verify the two configs have different memory values
            test_config._config["memory"] = "test memory"
            assert test_config.get("memory") == "test memory"
            # Verify real config has different memory value
            assert real_config.get("memory") != "test memory"
    finally:
        # Restore original environment
        if original_env:
            os.environ["VIBECTL_CONFIG_DIR"] = original_env
        elif "VIBECTL_CONFIG_DIR" in os.environ:
            del os.environ["VIBECTL_CONFIG_DIR"]
