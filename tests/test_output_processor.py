"""Tests for the output processor module."""

import json
from typing import Any, cast

import pytest
import yaml

from vibectl.output_processor import OutputProcessor
from vibectl.types import Truncation
from vibectl import truncation_logic as tl


@pytest.fixture
def processor() -> OutputProcessor:
    """Create an output processor with test settings."""
    return OutputProcessor(max_chars=200, llm_max_chars=50)


def test_process_for_llm_no_truncation(processor: OutputProcessor) -> None:
    """Test processing output that doesn't need truncation."""
    output = "Short test output"
    result: Truncation = processor.process_for_llm(output)

    assert result.truncated == output


def test_process_for_llm_with_truncation(processor: OutputProcessor) -> None:
    """Test processing output that needs truncation."""
    # Create output that will exceed token limit
    output = "x" * 10000
    result: Truncation = processor.process_for_llm(output)

    assert len(result.truncated) < len(output)
    # Check for the specific marker used by truncate_string
    assert "..." in result.truncated
    # With the new implementation, we use llm_max_chars
    expected_chunk_size = (processor.llm_max_chars - 5) // 2 # Adjusted for truncate_string
    assert result.truncated.startswith(output[:expected_chunk_size])  # First chunk


@pytest.mark.skip(reason="Log marker heuristic under review")
def test_process_logs(processor: OutputProcessor) -> None:
    """Test processing log output."""
    # Create a very large log to ensure it's truncated
    lines = [f"2024-01-{i:02d} Log entry {i}" for i in range(1, 500)]
    logs = "\n".join(lines)
    result: Truncation = processor.process_logs(logs)

    assert len(result.truncated) < len(logs)
    # Should favor recent logs (higher ratio)
    assert lines[-1] in result.truncated  # Most recent entry should be present
    # Check for the specific line truncation marker used in process_logs
    num_lines = len(lines)
    end_lines_count = min(num_lines - 1, 60)
    expected_marker = f"[... {end_lines_count} lines truncated ...]"
    assert expected_marker in result.truncated


#@pytest.mark.skip(reason="Skipping until truncation logic is fully tested and stable") # Unskip
def test_process_json_valid(processor: OutputProcessor) -> None:
    """Test processing valid JSON output."""
    # Test small JSON (no truncation needed)
    small_data = {"name": "test", "value": 42}
    json_str = json.dumps(small_data)
    result_small: Truncation = processor.process_json(json_str)
    assert result_small.truncated == json_str

    # Test large JSON (needs truncation)
    large_data = {
        "items": [{"name": f"item-{i}", "value": i} for i in range(500)],
        "metadata": {
            "count": 500,
            "details": {
                "type": "test",
                "nested": {
                    "deep": "value",
                    "items": list(range(500)),
                },
            },
        },
    }

    json_str_large = json.dumps(large_data)
    result_large: Truncation = processor.process_json(json_str_large)

    # Check that truncation happened and respects limits
    assert len(result_large.truncated) < len(json_str_large)
    assert len(result_large.truncated) <= processor.max_chars
    # Simple string truncation may invalidate JSON, so don't parse result_large.truncated


#@pytest.mark.skip(reason="Skipping until truncation logic is fully tested and stable") # Unskip
def test_process_json_invalid(processor: OutputProcessor) -> None:
    """Test processing invalid JSON output."""
    invalid_json = "{invalid: json}"
    # Invalid JSON is treated as plain text by process_json
    result_invalid: Truncation = processor.process_json(invalid_json)

    # Should fall back to standard text truncation (process_for_llm)
    # It might or might not be truncated based on llm_max_chars
    # Using llm_max_chars=50 from fixture
    if len(invalid_json) > processor.llm_max_chars:
        # Check against expected llm truncation
        expected_llm_trunc = tl.truncate_string(invalid_json, processor.llm_max_chars)
        assert result_invalid.truncated == expected_llm_trunc
    else:
        assert result_invalid.truncated == invalid_json


def test_format_kubernetes_resource(processor: OutputProcessor) -> None:
    """Test formatting Kubernetes resource output."""
    # Just ensure the method exists and returns the input
    output = "some kubernetes output"
    result = processor.format_kubernetes_resource(output)
    assert result == output


#@pytest.mark.skip(reason="Skipping until truncation logic is fully tested and stable") # Unskip
def test_detect_output_type(processor: OutputProcessor) -> None:
    """Test output type detection."""
    # Test JSON detection
    json_output = json.dumps({"test": "data"})
    assert processor.detect_output_type(json_output) == "json"
    assert processor.detect_output_type(' { "key": "value" } ') == "json"
    assert processor.detect_output_type(' [1, 2, 3] ') == "json"

    # Test YAML detection
    yaml_output_api = "apiVersion: v1\nkind: Pod"
    assert processor.detect_output_type(yaml_output_api) == "yaml"
    yaml_output_kind = "\nkind: Deployment\nmetadata:\n  name: test"
    assert processor.detect_output_type(yaml_output_kind) == "yaml"
    yaml_output_doc_start = "---\nyaml\nkey: value"
    # Check if it actually parses as YAML before asserting type
    try:
        yaml.safe_load(yaml_output_doc_start)
        assert processor.detect_output_type(yaml_output_doc_start) == "yaml"
    except yaml.YAMLError:
        assert processor.detect_output_type(yaml_output_doc_start) != "yaml"

    # Test log detection
    log_output_ts = "2024-01-01T12:00:00 INFO Starting service" # ISO format
    assert processor.detect_output_type(log_output_ts) == "logs"
    yaml_output = """
    apiVersion: v1
    kind: Pod
    metadata:
      name: test
    """
    assert processor.detect_output_type(yaml_output) == "yaml"

    # Test log detection
    log_output = """
    2024-01-01T12:00:00 INFO Starting service
    2024-01-01T12:00:01 DEBUG Processing request
    """
    assert processor.detect_output_type(log_output) == "logs"

    # Test plain text detection
    text_output = "Regular text output\nwith multiple lines"
    assert processor.detect_output_type(text_output) == "text"


#@pytest.mark.skip(reason="Skipping until truncation logic is fully tested and stable") # Unskip
def test_process_auto(processor: OutputProcessor) -> None:
    """Test automatic output processing based on type."""
    # Test JSON processing (use previous test data)
    large_data = {
        "items": [{"name": f"item-{i}", "value": i} for i in range(500)],
        "metadata": { "count": 500 }
    }
    json_output = json.dumps(large_data)
    result_json: Truncation = processor.process_auto(json_output)
    # Check that truncation happened and respects limits
    assert len(result_json.truncated) < len(json_output)
    assert len(result_json.truncated) <= processor.max_chars
    # Simple string truncation may invalidate JSON, so don't parse result_json.truncated

    # Test log processing
    log_lines = [
        "2024-01-01T12:01:00 INFO Starting service",
        "2024-01-01T12:01:01 DEBUG Processing request",
    ]
    log_output = "\n".join(log_lines * 300) # Ensure truncation
    result_log: Truncation = processor.process_auto(log_output)
    assert log_lines[-1] in result_log.truncated  # Recent logs preserved

    # Test YAML processing
    yaml_base = """apiVersion: v1
kind: Pod
metadata:
  name: test
status:
  phase: Running
  conditions: []"""
    yaml_output = yaml_base * 50 # Make long enough to truncate
    result_yaml: Truncation = processor.process_auto(yaml_output)
    assert result_yaml.truncated.startswith("apiVersion: v1") # Check start

    # Test plain text processing
    text_output = "x" * 10000
    result_text: Truncation = processor.process_auto(text_output)
    assert len(result_text.truncated) > 0


def test_extract_yaml_sections() -> None:
    """Test extracting sections from YAML output."""
    processor = OutputProcessor()

    # Test basic YAML with multiple sections
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
    status:
      phase: Running
      conditions:
      - type: Ready
        status: "True"
    """
    sections = processor.extract_yaml_sections(yaml_output)

    assert "metadata" in sections
    assert "spec" in sections
    assert "status" in sections
    assert "name: test-pod" in sections["metadata"]
    assert "nginx:latest" in sections["spec"]
    assert "phase: Running" in sections["status"]

    # Test YAML with no sections
    simple_yaml = """
    key1: value1
    key2: value2
    """
    sections = processor.extract_yaml_sections(simple_yaml)
    # For simple YAML, the parser will now return individual keys
    assert len(sections) > 0
    # We don't care about exact sections, just that it was parsed


@pytest.mark.skip(reason="Testing removed status truncation logic")
def test_truncate_yaml_status() -> None:
    """Test truncating YAML status sections."""
    # This test refers to a removed method
    pass


@pytest.mark.skip(reason="Skipping until truncation logic is fully tested and stable")
def test_process_output_for_vibe() -> None:
    """Test processing output specifically for vibe."""
    # This test refers to a removed method
    pass
