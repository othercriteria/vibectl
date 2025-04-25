"""Tests for edge cases in the output processor module.

This module focuses on testing edge cases and corner cases for the output processor.
"""

import json

import pytest

from vibectl.output_processor import OutputProcessor, Truncation


@pytest.fixture
def processor() -> OutputProcessor:
    """Create an output processor with default test settings."""
    return OutputProcessor(max_chars=200, llm_max_chars=50)


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


def test_detect_output_type_json_with_yaml_markers(processor: OutputProcessor) -> None:
    """Test validate_output_type with JSON that contains YAML-like keys."""
    # JSON that happens to contain apiVersion and kind as keys
    json_output = json.dumps(
        {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "test"}}
    )

    # Should be detected as JSON first
    result = processor.validate_output_type(json_output)
    assert isinstance(result, Truncation)
    assert result.original_type == "json"


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
