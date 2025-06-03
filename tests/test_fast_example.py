"""Example of tests optimized for speed using pytest.mark.fast."""

from unittest.mock import patch

import pytest

from vibectl.config import Config


@pytest.mark.fast
def test_fast_example_without_memory_reset() -> None:
    """This test is optimized by skipping memory reset.

    Tests marked with @pytest.mark.fast will not run the memory reset
    fixture before and after each test, improving performance.
    """
    # This assertion is just to demonstrate the test
    assert True


@pytest.mark.fast
def test_config_in_memory_operations() -> None:
    """Test Config operations without file I/O.

    This demonstrates using patch to avoid file operations during tests.
    """
    with patch.object(Config, "_save_config", return_value=None):
        # Create an in-memory config that doesn't write to disk
        config = Config()

        # Set a value (would normally write to disk, but we've patched it)
        config.set("display.theme", "light")

        # Verify the value was set in memory
        assert config.get("display.theme") == "light"
