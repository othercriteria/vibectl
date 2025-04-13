"""
Tests for output_processor.py coverage gaps.

This file focuses on testing specific code paths that are not covered by other tests.
"""

import pytest

from vibectl.output_processor import OutputProcessor


@pytest.fixture
def processor() -> OutputProcessor:
    """Return a new OutputProcessor instance for testing."""
    return OutputProcessor()


def test_process_yaml_with_status_section_truncation() -> None:
    """Test truncating a status section in YAML."""
    # Create a processor with small max_chars for testing
    processor = OutputProcessor(max_chars=100)

    # Create a very long status section (over 500 chars threshold)
    status_value = "\n".join([f"line{i}: value{'x' * 20}{i}" for i in range(30)])

    # Create sections dict with long status
    sections = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": "name: test-pod",
        "status": status_value,
    }

    # Verify our test data exceeds the threshold for truncation
    assert len(sections["status"]) > 500

    # Test directly the section truncation
    truncated_sections = processor.truncate_yaml_status(sections)

    # Verify truncation occurred
    assert len(truncated_sections["status"]) < len(sections["status"])
    assert "[status truncated]" in truncated_sections["status"]


def test_process_yaml_with_section_threshold() -> None:
    """Test section threshold calculation and application in truncate_string."""
    processor = OutputProcessor(max_chars=100)

    # Create a test string that exceeds threshold
    test_string = "x" * 200
    threshold = 50

    # Test truncate_string directly
    truncated = processor.truncate_string(test_string, threshold)

    # Verify truncation
    assert len(truncated) < len(test_string)
    assert "..." in truncated


def test_process_yaml_without_truncation(processor: OutputProcessor) -> None:
    """Test process_yaml with YAML that doesn't need truncation."""
    # Set a higher max_chars value to ensure no truncation
    processor.max_chars = 5000

    yaml_output = """
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
  namespace: default
spec:
  containers:
  - name: nginx
    image: nginx:latest
"""
    # Process the YAML
    processed, truncated = processor.process_yaml(yaml_output)

    # Verify no truncation occurred
    assert not truncated

    # Verify that the output contains all the key information
    # Match the actual format of the processed output
    assert "apiVersion" in processed
    assert "kind" in processed
    assert "Pod" in processed
    assert "metadata" in processed
    assert "name: test-pod" in processed
    assert "nginx" in processed


def test_extract_yaml_sections_with_empty_data(processor: OutputProcessor) -> None:
    """Test extract_yaml_sections with empty YAML data."""
    # Test with empty YAML
    empty_yaml = ""
    sections = processor.extract_yaml_sections(empty_yaml)

    # Should return a content section with the empty string
    assert "content" in sections
    assert sections["content"] == ""

    # Test with None data
    null_yaml = "null"
    sections = processor.extract_yaml_sections(null_yaml)

    # Should return a content section with the YAML string
    assert "content" in sections
    assert "null" in sections["content"]


def test_extract_yaml_sections_with_no_sections(processor: OutputProcessor) -> None:
    """Test extract_yaml_sections with YAML that has no sections."""
    # Test with YAML that has no top-level sections
    sections = processor.extract_yaml_sections("apiVersion: v1")

    # Should have extracted the apiVersion key
    assert "apiVersion" in sections or "content" in sections


def test_truncate_string_without_truncation(processor: OutputProcessor) -> None:
    """Test truncate_string with a string that doesn't need truncation."""
    text = "This is a short string"
    max_length = 100

    # Truncate the string
    truncated = processor.truncate_string(text, max_length)

    # Should return the original string
    assert truncated == text

    # Test with exact match to max_length
    text = "x" * 50
    max_length = 50
    truncated = processor.truncate_string(text, max_length)

    # Should return the original string
    assert truncated == text
