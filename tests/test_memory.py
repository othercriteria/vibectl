"""Tests for the memory module.

This module tests the memory management functionality of vibectl.
"""

from unittest.mock import Mock, patch

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
    # Setup
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
    # Setup
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
    """Test setting memory content."""
    # Setup
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_config.get.return_value = 300  # max_chars is big enough for the test string
    memory_text = "Test memory content"

    # Execute
    set_memory(memory_text)

    # Assert
    mock_config.get.assert_called_once_with("memory_max_chars", 300)
    mock_config.set.assert_called_once_with("memory", memory_text)
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
    """Test enabling memory updates."""
    # Setup
    mock_config = Mock()
    mock_config_class.return_value = mock_config

    # Execute
    enable_memory()

    # Assert
    mock_config.set.assert_called_once_with("memory_enabled", True)
    mock_config.save.assert_called_once()


@patch("vibectl.memory.Config")
def test_disable_memory(mock_config_class: Mock) -> None:
    """Test disabling memory updates."""
    # Setup
    mock_config = Mock()
    mock_config_class.return_value = mock_config

    # Execute
    disable_memory()

    # Assert
    mock_config.set.assert_called_once_with("memory_enabled", False)
    mock_config.save.assert_called_once()


@patch("vibectl.memory.Config")
def test_clear_memory(mock_config_class: Mock) -> None:
    """Test clearing memory content."""
    # Setup
    mock_config = Mock()
    mock_config_class.return_value = mock_config

    # Execute
    clear_memory()

    # Assert
    mock_config.set.assert_called_once_with("memory", "")
    mock_config.save.assert_called_once()


@patch("vibectl.memory.llm.get_model")
@patch("vibectl.memory.is_memory_enabled")
@patch("vibectl.memory.get_memory")
@patch("vibectl.memory.set_memory")
@patch("vibectl.memory.Config")
def test_update_memory(
    mock_config_class: Mock,
    mock_set_memory: Mock,
    mock_get_memory: Mock,
    mock_is_enabled: Mock,
    mock_get_model: Mock,
) -> None:
    """Test updating memory based on command output."""
    # Setup
    mock_config = Mock()
    mock_config_class.return_value = mock_config
    mock_config.get.return_value = 300  # max_chars

    mock_is_enabled.return_value = True
    mock_get_memory.return_value = "Previous memory"

    mock_model = Mock()
    mock_get_model.return_value = mock_model
    mock_response = Mock()
    mock_response.text.return_value = "Updated memory"
    mock_model.prompt.return_value = mock_response

    # Execute
    update_memory("kubectl get pods", "pod1 Running", "1 pod running", "test-model")

    # Assert
    mock_is_enabled.assert_called_once()
    mock_get_memory.assert_called_once()
    mock_model.prompt.assert_called_once()
    mock_set_memory.assert_called_once_with("Updated memory", mock_config)


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
    """Test include_memory_in_prompt with no insertion marker."""
    # Setup
    mock_is_enabled.return_value = True
    mock_get_memory.return_value = "Test memory"
    prompt_template = "Some text without markers"

    # Memory section should be added at the beginning
    expected = "\nMemory context:\nTest memory\n\nSome text without markers"

    # Execute
    result = include_memory_in_prompt(prompt_template)

    # Assert
    assert result == expected


@patch("vibectl.memory.is_memory_enabled")
@patch("vibectl.memory.get_memory")
def test_include_memory_in_prompt_with_example_inputs(
    mock_get_memory: Mock, mock_is_enabled: Mock
) -> None:
    """Test include_memory_in_prompt with 'Example inputs and outputs:' marker."""
    # Setup
    mock_is_enabled.return_value = True
    mock_get_memory.return_value = "Test memory"
    prompt_template = "Some text\nExample inputs and outputs:\nMore text"
    expected = "Some text\n\nMemory context:\nTest memory\n\nExample inputs and outputs:\nMore text"

    # Execute
    result = include_memory_in_prompt(prompt_template)

    # Assert
    assert result == expected
    mock_is_enabled.assert_called_once()
    mock_get_memory.assert_called_once()
