"""
Tests for the console management module.
"""

import io
import unittest
from unittest.mock import patch

from vibectl.console import ConsoleManager


class TestConsoleManager(unittest.TestCase):
    """Test cases for the ConsoleManager class."""

    def setUp(self) -> None:
        """Set up test fixtures before each test method."""
        self.console_manager = ConsoleManager()

    def test_print(self) -> None:
        """Test the print method."""
        with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            self.console_manager.print("Test message")
            # Rich adds styling, so we just check if the message appears in output
            self.assertIn("Test message", fake_stdout.getvalue())

    def test_print_raw(self) -> None:
        """Test the print_raw method."""
        with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            self.console_manager.print_raw("Raw message")
            # For raw output, it should be exactly as provided
            self.assertIn("Raw message", fake_stdout.getvalue())

    def test_print_error(self) -> None:
        """Test the print_error method."""
        with patch("sys.stderr", new=io.StringIO()) as fake_stderr:
            self.console_manager.print_error("Error message")
            # Rich formats errors, so we just check if the message appears
            self.assertIn("Error message", fake_stderr.getvalue())

    def test_print_warning(self) -> None:
        """Test the print_warning method."""
        with patch("sys.stderr", new=io.StringIO()) as fake_stderr:
            self.console_manager.print_warning("Warning message")
            self.assertIn("Warning message", fake_stderr.getvalue())

    def test_print_note(self) -> None:
        """Test the print_note method."""
        with patch("sys.stderr", new=io.StringIO()) as fake_stderr:
            self.console_manager.print_note("Note message")
            self.assertIn("Note message", fake_stderr.getvalue())

    def test_print_note_with_error(self) -> None:
        """Test the print_note method with an error."""
        with patch("sys.stderr", new=io.StringIO()) as fake_stderr:
            test_error = ValueError("Test error")
            self.console_manager.print_note("Note message", error=test_error)
            self.assertIn("Note message", fake_stderr.getvalue())
            self.assertIn("Test error", fake_stderr.getvalue())

    def test_print_vibe(self) -> None:
        """Test the print_vibe method."""
        with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            self.console_manager.print_vibe("Vibe summary")
            self.assertIn("Vibe summary", fake_stdout.getvalue())

    def test_print_no_output_warning(self) -> None:
        """Test the print_no_output_warning method."""
        with patch("sys.stderr", new=io.StringIO()) as fake_stderr:
            self.console_manager.print_no_output_warning()
            self.assertIn("Neither raw output nor vibe output", fake_stderr.getvalue())

    def test_print_truncation_warning(self) -> None:
        """Test the print_truncation_warning method."""
        with patch("sys.stderr", new=io.StringIO()) as fake_stderr:
            self.console_manager.print_truncation_warning()
            self.assertIn("Output is too large", fake_stderr.getvalue())

    def test_print_missing_api_key_error(self) -> None:
        """Test the print_missing_api_key_error method."""
        with patch("sys.stderr", new=io.StringIO()) as fake_stderr:
            self.console_manager.print_missing_api_key_error()
            self.assertIn("Missing API key", fake_stderr.getvalue())

    def test_print_config_table(self) -> None:
        """Test the print_config_table method."""
        with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            test_config = {"key1": "value1", "key2": "value2"}
            self.console_manager.print_config_table(test_config)
            # Check if all keys and values appear in the output
            for key, value in test_config.items():
                self.assertIn(key, fake_stdout.getvalue())
                self.assertIn(value, fake_stdout.getvalue())

    def test_handle_vibe_output_raw_only(self) -> None:
        """Test handle_vibe_output with only raw output enabled."""
        with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            self.console_manager.handle_vibe_output(
                output="Test output",
                show_raw_output=True,
                show_vibe=False,
                summary=None,
            )
            self.assertIn("Test output", fake_stdout.getvalue())
            # No vibe check should be printed
            self.assertNotIn("✨ Vibe check", fake_stdout.getvalue())

    def test_handle_vibe_output_vibe_only(self) -> None:
        """Test handle_vibe_output with only vibe output enabled."""
        with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            self.console_manager.handle_vibe_output(
                output="Test output",
                show_raw_output=False,
                show_vibe=True,
                summary="Vibe summary",
            )
            # Raw output should not be printed
            self.assertNotIn("Test output", fake_stdout.getvalue())
            # Vibe check should be printed
            self.assertIn("Vibe check", fake_stdout.getvalue())
            self.assertIn("Vibe summary", fake_stdout.getvalue())

    def test_handle_vibe_output_both(self) -> None:
        """Test handle_vibe_output with both outputs enabled."""
        with patch("sys.stdout", new=io.StringIO()) as fake_stdout:
            self.console_manager.handle_vibe_output(
                output="Test output",
                show_raw_output=True,
                show_vibe=True,
                summary="Vibe summary",
            )
            # Both outputs should be printed
            self.assertIn("Test output", fake_stdout.getvalue())
            self.assertIn("Vibe check", fake_stdout.getvalue())
            self.assertIn("Vibe summary", fake_stdout.getvalue())

    def test_process_output_for_vibe_no_truncation(self) -> None:
        """Test process_output_for_vibe with output under the token limit."""
        output = "Short output"
        processed_output, was_truncated = self.console_manager.process_output_for_vibe(
            output=output, max_token_limit=10000, truncation_ratio=3
        )
        self.assertEqual(processed_output, output)
        self.assertFalse(was_truncated)

    def test_process_output_for_vibe_with_truncation(self) -> None:
        """Test process_output_for_vibe with output exceeding the token limit."""
        # Create output that will exceed token limit (4 chars per token)
        large_output = "a" * 120000  # Should be about 30000 tokens

        # Patch the print_truncation_warning method instead of stderr
        with patch.object(
            self.console_manager, "print_truncation_warning"
        ) as mock_warning:
            processed_output, was_truncated = (
                self.console_manager.process_output_for_vibe(
                    output=large_output, max_token_limit=10000, truncation_ratio=3
                )
            )

            # Output should be truncated
            self.assertTrue(was_truncated)
            # Truncation warning should be called
            mock_warning.assert_called_once()
            # Processed output should contain truncation message
            self.assertIn("[...truncated", processed_output)
            # Processed output should be shorter than original
            self.assertLess(len(processed_output), len(large_output))


if __name__ == "__main__":
    unittest.main()
