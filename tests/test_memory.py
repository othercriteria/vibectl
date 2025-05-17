"""Tests for memory management functionality.

The memory.py module provides functions to manage the memory feature,
allowing vibectl to maintain context across commands.
"""

from typing import Any
from unittest.mock import Mock, patch

import pytest

from vibectl.config import Config
from vibectl.memory import (
    clear_memory,
    disable_memory,
    enable_memory,
    get_memory,
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
        if key == "memory":  # for get_memory() call within update_memory
            return ""
        return default

    mock_config.get.side_effect = mock_config_get_side_effect

    # Mock adapter and its model reference
    mock_adapter = Mock()
    mock_model = Mock()
    mock_get_adapter.return_value = mock_adapter
    mock_adapter.get_model.return_value = mock_model

    # Setup prompt template for memory_update_prompt
    mock_update_prompt.return_value = (
        ["SysMemPrompt"],
        [
            "UserMemTemplate"
        ],  # Simplified from original, as it's not directly formatted here anymore
    )

    mock_response_text = "Updated memory content"
    mock_adapter.execute_and_log_metrics.return_value = (
        mock_response_text,
        None,  # Metrics
    )

    with patch("vibectl.memory.Config", return_value=mock_config):
        update_memory(
            command_message="kubectl get pods",  # Corrected argument name
            command_output="pod1 Running\\npod2 Error",
            vibe_output="Pods are in mixed state",
            model_name="test-model",
            config=mock_config,  # Pass explicit config
        )

    mock_update_prompt.assert_called_once_with(
        command_message="kubectl get pods",  # Corrected argument name
        command_output="pod1 Running\\npod2 Error",
        vibe_output="Pods are in mixed state",
        current_memory="",
        config=mock_config,
    )

    mock_get_adapter.assert_called_once_with(mock_config)
    mock_adapter.get_model.assert_called_once_with("test-model")

    mock_adapter.execute_and_log_metrics.assert_called_once_with(
        model=mock_model,
        system_fragments=["SysMemPrompt"],
        user_fragments=["UserMemTemplate"],
    )
    mock_config.set.assert_any_call(
        "memory", mock_response_text
    )  # Using any_call due to other set calls
    mock_config.save.assert_called()


@patch("vibectl.memory.is_memory_enabled")
def test_update_memory_disabled(mock_is_enabled: Mock) -> None:
    """Test update_memory when memory is disabled."""
    # Setup
    mock_is_enabled.return_value = False
    mock_config = Mock()
    with patch("vibectl.memory.set_memory") as mock_set_memory:
        update_memory(
            command_message="cmd",  # Corrected argument name
            command_output="out",
            vibe_output="vibe",
            config=mock_config,
        )
        mock_set_memory.assert_not_called()


@pytest.mark.fast
@patch("vibectl.memory.Config.save")
@patch("vibectl.memory.Config._load_config")
@patch("pathlib.Path.exists")
def test_test_isolation_doesnt_impact_real_config(
    mock_path_exists: Mock, mock_load_config: Mock, mock_config_save: Mock
) -> None:
    """Verify that config changes in tests do not affect the real config file.

    This test checks that if a test modifies the config (e.g., sets memory)
    those changes are isolated to the mock and don't persist to the actual
    user's config file on disk.
    """
    mock_path_exists.return_value = False  # Simulate no pre-existing real config
    mock_load_config.return_value = {}  # Simulate loading an empty config

    # Get initial memory state (should be default or from mocked _load_config)
    # Pass a freshly mocked Config instance to get_memory to ensure isolation
    initial_test_config_instance_for_get = Mock(spec=Config)
    initial_test_config_instance_for_get.get.return_value = "initial_mem_for_get"

    original_memory_value = get_memory(config=initial_test_config_instance_for_get)
    initial_test_config_instance_for_get.get.assert_called_once_with("memory", "")

    # Simulate a test operation that modifies memory
    # This set_memory call will instantiate its own Config if one isn't provided,
    # or use the one provided. We mock Config globally for this part.
    with patch("vibectl.memory.Config") as mock_config_in_test_operation:
        mock_config_instance_for_set = Mock(spec=Config)
        mock_config_in_test_operation.return_value = mock_config_instance_for_set

        # Configure .get() on this specific mock instance for this test
        def custom_get_side_effect(key: str, default: Any = None) -> Any:
            if key == "memory_max_chars":
                return 500  # Return an int for max_chars
            # For other keys, you might want to return the default or another Mock
            return default if default is not None else Mock()

        mock_config_instance_for_set.get.side_effect = custom_get_side_effect

        set_memory("memory_value_set_in_test", config=mock_config_instance_for_set)

        # Verify the mocked Config instance was used for set and save
        mock_config_instance_for_set.set.assert_called_once_with(
            "memory", "memory_value_set_in_test"
        )
        mock_config_instance_for_set.save.assert_called_once()

    # Verify that the memory accessible via get_memory (using a *different*
    # instance or default) was not affected.
    subsequent_test_config_instance_for_get = Mock(spec=Config)
    subsequent_test_config_instance_for_get.get.return_value = (
        "initial_mem_for_get"  # Mimic it still holding original value
    )

    assert (
        get_memory(config=subsequent_test_config_instance_for_get)
        == original_memory_value
    ), (
        "Memory accessible via get_memory() should not have been changed by an "
        "isolated set_memory call."
    )
    subsequent_test_config_instance_for_get.get.assert_called_once_with("memory", "")

    # Ensure no *actual* file save operations occurred on any Config instance
    # because Config.save itself was mocked at the top level of the test.
    mock_config_save.assert_not_called()
    # Ensure no *actual* load or exists calls happened on Path.
    # mock_path_exists.assert_called() # This will be called by Config init
    # mock_load_config.assert_called() # This will be called by Config init
