"""Tests for prompt templates."""

from unittest.mock import Mock, patch

from vibectl.prompt import get_formatting_instructions


def test_get_formatting_instructions_without_custom_instructions() -> None:
    """Test formatting instructions without custom instructions."""
    mock_config = Mock()
    mock_config.get.return_value = None

    with patch("vibectl.prompt.Config", return_value=mock_config):
        instructions = get_formatting_instructions()

        # Check standard content
        assert "Format your response using rich.Console() markup syntax" in instructions
        assert "Current date and time is" in instructions

        # Ensure no custom instructions section
        assert "Custom instructions:" not in instructions


def test_get_formatting_instructions_with_custom_instructions() -> None:
    """Test formatting instructions with custom instructions."""
    mock_config = Mock()
    mock_config.get.return_value = "Use a ton of emojis!"

    with patch("vibectl.prompt.Config", return_value=mock_config):
        instructions = get_formatting_instructions()

        # Check standard content
        assert "Format your response using rich.Console() markup syntax" in instructions
        assert "Current date and time is" in instructions

        # Check custom instructions are included
        assert "Custom instructions:" in instructions
        assert "Use a ton of emojis!" in instructions
