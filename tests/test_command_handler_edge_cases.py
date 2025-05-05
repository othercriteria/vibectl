"""Tests for command_handler.py's handling of edge cases and extreme inputs.

This module tests edge cases, extreme inputs, and error conditions to ensure
the command handler is robust against unexpected or malformed inputs.
"""

from collections.abc import Generator
from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.command_handler import (
    _handle_command_confirmation,
)


@pytest.fixture
def mock_get_adapter_patch() -> Generator[MagicMock, None, None]:
    """Mock the get_model_adapter function. Yields the mocked adapter instance."""
    with patch("vibectl.command_handler.get_model_adapter") as mock_patch:
        mock_adapter_instance = MagicMock()
        mock_model_instance = Mock()
        mock_adapter_instance.get_model.return_value = mock_model_instance
        mock_adapter_instance.execute = MagicMock()
        mock_patch.return_value = mock_adapter_instance
        yield mock_adapter_instance


@pytest.fixture
def mock_console() -> Generator[MagicMock, None, None]:
    """Mock console manager for edge case tests."""
    with patch("vibectl.command_handler.console_manager") as mock:
        yield mock


@pytest.fixture
def mock_execute_command() -> Generator[MagicMock, None, None]:
    """Mock _execute_command for edge case tests."""
    with patch("vibectl.command_handler._execute_command") as mock:
        yield mock


@pytest.fixture
def mock_include_memory() -> Generator[MagicMock, None, None]:
    """Mock include_memory_in_prompt."""
    with patch("vibectl.memory.include_memory_in_prompt") as mock:
        # Default behavior: return prompt unmodified
        mock.side_effect = lambda prompt, **kwargs: prompt
        yield mock


@pytest.fixture
def mock_click_prompt() -> Generator[MagicMock, None, None]:
    """Mock click.prompt."""
    with patch("click.prompt") as mock:
        yield mock


@pytest.fixture
def mock_memory_helpers() -> Generator[dict[str, MagicMock], None, None]:
    """Mocks memory helpers (get_memory, set_memory, update_memory, prompt)."""
    # Patch get_memory in both locations it's imported/used
    with (
        patch("vibectl.command_handler.get_memory") as mock_get_ch,
        patch.object(
            _handle_command_confirmation, "get_memory", create=True
        ) as mock_get_local,
        patch("vibectl.command_handler.set_memory") as mock_set,
        patch("vibectl.command_handler.update_memory") as mock_update,
        patch("vibectl.command_handler.memory_fuzzy_update_prompt") as mock_prompt_func,
    ):  # Patch where it's called
        # Configure mocks
        mock_get_ch.return_value = "Initial memory content (ch)."
        mock_get_local.return_value = "Initial memory content (local)."
        mock_prompt_func.return_value = "Generated fuzzy update prompt."

        # Combine get mocks if needed or keep separate?
        # For simplicity, let's yield both - tests can use the relevant one.

        yield {
            "get_ch": mock_get_ch,  # Called by _handle_fuzzy_memory_update
            "get_local": mock_get_local,  # ('m' option)
            "set": mock_set,
            "update": mock_update,
            "prompt_func": mock_prompt_func,
            # Removed adapter mock
        }


# --- Test Cases for Vibe Processing Error Handling --- #

# Add other edge case tests here, e.g., for:
# - Invalid user input to prompts
# - Extremely long output causing Vibe errors
# - Malformed config files
# - Race conditions (if applicable)
