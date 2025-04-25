"""
Tests for OutputProcessor.process_for_llm coverage.
"""

import pytest
from vibectl.output_processor import OutputProcessor
from vibectl.types import Truncation

# --- Fixtures ---

@pytest.fixture
def processor() -> OutputProcessor:
    """Default OutputProcessor instance."""
    return OutputProcessor()

@pytest.fixture
def processor_short_limits() -> OutputProcessor:
    """OutputProcessor with short limits for testing."""
    return OutputProcessor(max_chars=50, llm_max_chars=20)

# --- process_for_llm Tests ---

def test_process_for_llm_truncation(processor_short_limits: OutputProcessor) -> None:
    """Test LLM truncation."""
    long_string = "a" * 100
    truncated = processor_short_limits.process_for_llm(long_string)
    assert len(truncated.truncated) == 20
    assert "..." in truncated.truncated

def test_process_for_llm_no_truncation(processor: OutputProcessor) -> None:
    """Test LLM processing without truncation."""
    short_string = "abc"
    processed = processor.process_for_llm(short_string)
    assert processed.truncated == short_string 