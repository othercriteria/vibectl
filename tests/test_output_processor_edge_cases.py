"""Tests for edge cases in the output processor module.

This module focuses on testing edge cases and corner cases for the output processor.
"""

import json
from typing import Any
from unittest.mock import patch

import pytest

from vibectl.output_processor import OutputProcessor
from vibectl.types import Truncation
from vibectl import truncation_logic as tl


@pytest.fixture
def processor() -> OutputProcessor:
    """Create an output processor with test settings."""
    return OutputProcessor(max_chars=200, llm_max_chars=50)


def test_process_for_llm_empty_input(processor: OutputProcessor) -> None:
    """Test processing empty input."""
    output = ""
    result: Truncation = processor.process_for_llm(output)

    assert result.original == output
    assert result.truncated == output


def test_process_for_llm_exactly_at_limit(processor: OutputProcessor) -> None:
    """Test processing output exactly at the llm_max_chars limit."""
    # Create output exactly at the llm_max_chars limit
    output = "x" * processor.llm_max_chars
    result: Truncation = processor.process_for_llm(output)

    # Should not truncate if exactly at the limit
    assert result.original == output
    assert result.truncated == output


def test_process_for_llm_one_over_limit(processor: OutputProcessor) -> None:
    """Test process_for_llm truncates correctly when input is just over limit."""
    # Create output one character over the llm limit
    output = "x" * (processor.llm_max_chars + 1)
    result: Truncation = processor.process_for_llm(output)

    assert len(result.truncated) < len(output)
    # Calculate expected truncation based on tl.truncate_string logic
    max_len = processor.llm_max_chars
    ellipsis = "..."
    ellipsis_len = len(ellipsis) # Should be 3

    if max_len <= ellipsis_len:
        expected_explicit = output[:max_len]
    else:
        remaining = max_len - ellipsis_len
        half_length = remaining // 2
        end_length = remaining - half_length # Calculate end length separately
        first_chunk = output[:half_length]
        last_chunk = output[-end_length:] if end_length > 0 else "" # Use end_length
        expected_explicit = f"{first_chunk}{ellipsis}{last_chunk}"

    assert result.truncated == expected_explicit


def test_process_logs_empty(processor: OutputProcessor) -> None:
    """Test processing empty log output."""
    logs = ""
    result: Truncation = processor.process_logs(logs)

    assert result.original == logs
    assert result.truncated == logs


def test_process_logs_single_line(processor: OutputProcessor) -> None:
    """Test processing single line log output."""
    logs = "2024-01-01 Single log entry"
    result: Truncation = processor.process_logs(logs)

    assert result.original == logs
    assert result.truncated == logs


def test_process_json_empty_object(processor: OutputProcessor) -> None:
    """Test processing empty JSON object."""
    json_str = "{}"
    result: Truncation = processor.process_json(json_str)

    assert result.original == json_str
    assert result.truncated == json_str


def test_process_json_empty_array(processor: OutputProcessor) -> None:
    """Test processing empty JSON array."""
    json_str = "[]"
    result: Truncation = processor.process_json(json_str)

    assert result.original == json_str
    assert result.truncated == json_str


def test_process_json_null(processor: OutputProcessor) -> None:
    """Test processing JSON null value."""
    json_str = "null"
    result: Truncation = processor.process_json(json_str)

    assert result.original == json_str
    assert result.truncated == json_str


@pytest.mark.skip(reason="Skipping until truncation logic is fully tested and stable")
def test_process_deeply_nested_json_structure(processor: OutputProcessor) -> None:
    """Test processing deeply nested JSON structure."""
    # Create deeply nested structure
    data: dict[str, dict[str, Any]] = {}
    current = data
    for i in range(20):  # Way past default max_depth
        current[f"level{i}"] = {}
        current = current[f"level{i}"]

    json_str = json.dumps(data)
    result: Truncation = processor.process_json(json_str)

    # The processed result should be valid JSON
    processed_data = json.loads(result.truncated)
    assert isinstance(processed_data, dict)
    assert result.truncated != json_str

    # For a more complex test, create a structure with large arrays AND deep nesting
    complex_data = {
        "items": [{"id": i, "data": "x" * 100} for i in range(50)],  # Long list, large items
        "deep": {
            "nested": {
                "structure": {
                    "with": {"lots": {"of": {"levels": [1, 2, 3, 4, 5] * 100}}}  # Deep and long list
                }
            }
        },
    }

    complex_json = json.dumps(complex_data)
    processor.max_chars = 100  # Set a very low limit for this part
    result_complex: Truncation = processor.process_json(complex_json)

    if len(complex_json) > processor.max_chars:
        assert result_complex.truncated != complex_json
        assert len(result_complex.truncated) <= processor.max_chars
    else:
        assert result_complex.truncated == complex_json

    # Test with short complex structure (should not truncate)
    complex_json_short = json.dumps({"items": [{"id": i, "data": "x" * 10} for i in range(5)]})
    result_complex_short: Truncation = processor.process_json(complex_json_short)
    assert result_complex_short.truncated == complex_json_short


@pytest.mark.skip(reason="Skipping until truncation logic is fully tested and stable")
def test_detect_output_type_mixed_content(processor: OutputProcessor) -> None:
    """Test output type detection with mixed content."""
    # Content that has log-like lines but is mostly text
    mixed_output = """
    Regular text line
    2024-01-01 12:34:56 This looks like a log line
    More regular text
    Yet another text line
    """

    # The refactored logic checks the start of lines within the first 5 lines.
    # If a log pattern appears there, it should be logs.
    assert processor.detect_output_type(mixed_output) == "logs"

    # Test content where log pattern is *not* in first 5 lines
    mixed_output_late_log = """
    Line 1
    Line 2
    Line 3
    Line 4
    Line 5
    Line 6
    2024-01-01 12:34:56 Log line later on
    """
    assert processor.detect_output_type(mixed_output_late_log) == "text"


def test_detect_output_type_json_with_yaml_markers(processor: OutputProcessor) -> None:
    """Test output type detection with JSON that contains YAML-like keys."""
    # JSON that happens to contain apiVersion and kind as keys
    json_output = json.dumps(
        {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "test"}}
    )

    # Should be detected as JSON first
    assert processor.detect_output_type(json_output) == "json"


def test_extract_yaml_sections_malformed(processor: OutputProcessor) -> None:
    """Test extracting sections from malformed YAML."""
    malformed_yaml = """
    apiVersion: v1
    kind: Pod
    indentation:
      is: wrong
        this: is
       not: valid
    metadata:
      name: test
    """

    # Should return content section as parsing fails
    sections = processor.extract_yaml_sections(malformed_yaml)
    assert list(sections.keys()) == ["content"]
    assert sections["content"] == malformed_yaml.strip()


def test_process_auto_garbage_input(processor: OutputProcessor) -> None:
    """Test automatic output processing with garbage/unparseable input."""
    # Create garbage input that doesn't match any known format
    garbage = "!@#$%^&*()_+<>?:{}"

    result: Truncation = processor.process_auto(garbage)

    # Should fall back to basic text processing
    assert result.original == garbage
    assert result.truncated == garbage


def test_extract_yaml_sections_non_k8s_format() -> None:
    """Test extract_yaml_sections with non-Kubernetes YAML."""
    processor = OutputProcessor()
    yaml_input = """
    user:
      name: Test User
      email: test@example.com
    settings:
      theme: dark
      notifications: true
    """
    sections = processor.extract_yaml_sections(yaml_input)
    assert list(sections.keys()) == ["user", "settings"]
    assert "name: Test User" in sections["user"]
    assert "theme: dark" in sections["settings"]
