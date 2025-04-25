"""
Tests for OutputProcessor.__init__ coverage.
"""

import pytest
from vibectl.output_processor import OutputProcessor

# --- Fixtures ---

@pytest.fixture
def processor() -> OutputProcessor:
    """Default OutputProcessor instance."""
    return OutputProcessor()

@pytest.fixture
def processor_short_limits() -> OutputProcessor:
    """OutputProcessor with short limits for testing."""
    return OutputProcessor(max_chars=50, llm_max_chars=20)

# --- __init__ Tests ---

def test_init_default_limits() -> None:
    """Test default limits are set correctly."""
    proc = OutputProcessor()
    assert proc.max_chars == 2000
    assert proc.llm_max_chars == 200

def test_init_custom_limits() -> None:
    """Test custom limits are set correctly."""
    proc = OutputProcessor(max_chars=500, llm_max_chars=100)
    assert proc.max_chars == 500
    assert proc.llm_max_chars == 100 