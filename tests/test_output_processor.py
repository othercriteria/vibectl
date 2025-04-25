"""Tests for the output processor module."""

import json

import pytest
import yaml

from vibectl import truncation_logic as tl
from vibectl.output_processor import OutputProcessor
from vibectl.types import Truncation


@pytest.fixture
def processor() -> OutputProcessor:
    """Create an output processor with test settings."""
    return OutputProcessor(max_chars=200, llm_max_chars=50)


def test_process_logs_budgeted(processor: OutputProcessor) -> None:
    # Test that log processing respects an explicit budget
    lines = [f"2024-01-01T12:{i:02}:00 INFO Line {i}" for i in range(300)]
    log_output = "\n".join(lines)

    # --- Test Case 1: Budget allows full output --- #
    result_large_budget: Truncation = processor.process_logs(
        log_output, budget=len(log_output) + 100
    )
    assert result_large_budget.truncated == log_output

    # --- Test Case 2: Small budget forces truncation --- #
    small_budget = 100
    result_small_budget: Truncation = processor.process_logs(
        log_output, budget=small_budget
    )
    assert len(result_small_budget.truncated) <= small_budget
    # Check it contains the truncation marker (unless budget is extremely tiny)
    if small_budget > 50:  # Heuristic for very small budgets
        assert "[..." in result_small_budget.truncated

    # --- Test Case 3: Zero budget --- #
    result_zero_budget: Truncation = processor.process_logs(log_output, budget=0)
    assert result_zero_budget.truncated == tl.truncate_string(
        log_output, 0
    )  # Or maybe just truncates string

    # --- Test Case 4: Empty Input --- #
    result_empty: Truncation = processor.process_logs("", budget=100)
    assert result_empty.truncated == ""

    # --- Test Case 5: Short Input (within budget) --- #
    short_logs = "\n".join(lines[:5])
    result_short: Truncation = processor.process_logs(short_logs, budget=1000)
    assert result_short.truncated == short_logs


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
    # Simple string truncation may invalidate JSON,
    # so don't parse result_large.truncated


def test_process_json_invalid(processor: OutputProcessor) -> None:
    """Test processing invalid JSON output."""
    invalid_json = "{invalid: json}"
    # Invalid JSON is treated as plain text by process_json
    result_invalid: Truncation = processor.process_json(invalid_json)

    # Should fall back to standard text truncation
    # The fallback in process_json now uses max_chars
    if len(invalid_json) > processor.max_chars:
        # Check against expected standard truncation
        expected_trunc = tl.truncate_string(invalid_json, processor.max_chars)
        assert result_invalid.truncated == expected_trunc
    else:
        assert result_invalid.truncated == invalid_json


def test_format_kubernetes_resource(processor: OutputProcessor) -> None:
    """Test formatting Kubernetes resource output."""
    # Just ensure the method exists and returns the input
    output = "some kubernetes output"
    result = processor.format_kubernetes_resource(output)
    assert result == output


def test_validate_output_type(processor: OutputProcessor) -> None:
    """Test output type validation and detection."""
    # Test JSON detection
    json_output = json.dumps({"test": "data"})
    result_json1 = processor.validate_output_type(json_output)
    assert isinstance(result_json1, Truncation)
    assert result_json1.original_type == "json"

    result_json2 = processor.validate_output_type(' { "key": "value" } ')
    assert isinstance(result_json2, Truncation)
    assert result_json2.original_type == "json"

    result_json3 = processor.validate_output_type(" [1, 2, 3] ")
    assert isinstance(result_json3, Truncation)
    assert result_json3.original_type == "json"

    # Test YAML detection
    yaml_output_api = "apiVersion: v1\nkind: Pod"
    result_yaml1 = processor.validate_output_type(yaml_output_api)
    assert isinstance(result_yaml1, Truncation)
    assert result_yaml1.original_type == "yaml"

    yaml_output_kind = "\nkind: Deployment\nmetadata:\n  name: test"
    result_yaml2 = processor.validate_output_type(yaml_output_kind)
    assert isinstance(result_yaml2, Truncation)
    assert result_yaml2.original_type == "yaml"

    yaml_output_doc_start = "---\nkey: value"  # Simple string with marker
    result_yaml3 = processor.validate_output_type(yaml_output_doc_start)
    assert isinstance(result_yaml3, Truncation)
    assert result_yaml3.original_type == "yaml"

    # Test simple string without markers (should be text)
    yaml_simple_string = "just a string"
    result_yaml4 = processor.validate_output_type(yaml_simple_string)
    assert isinstance(result_yaml4, Truncation)
    assert result_yaml4.original_type == "text"

    # Test log detection
    log_output_ts = (
        "2024-01-01T12:00:00 INFO Starting service\n"
        "2024-01-01T12:00:01 DEBUG Processing request"
    )  # Multiple lines needed now
    result_logs = processor.validate_output_type(log_output_ts)
    assert isinstance(result_logs, Truncation)
    assert result_logs.original_type == "logs"

    # Test plain text detection
    text_output = "Regular text output\nwith multiple lines"
    result_text = processor.validate_output_type(text_output)
    assert isinstance(result_text, Truncation)
    assert result_text.original_type == "text"


def test_process_auto(processor: OutputProcessor) -> None:
    """
    Test automatic output processing based on type using standard budgets
    (max_chars).
    """
    # Test JSON processing (using max_chars)
    large_data_json = {
        "items": [
            {"name": f"item-{i}", "value": i} for i in range(100)
        ],  # Reduced from 500
        "metadata": {"count": 100},  # Reduced count
    }
    json_output = json.dumps(large_data_json)
    result_json: Truncation = processor.process_auto(json_output)
    # Check that truncation happened and respects limits (max_chars)
    if len(json_output) > processor.max_chars:
        assert len(result_json.truncated) < len(json_output)
        assert len(result_json.truncated) <= processor.max_chars
    else:
        assert result_json.truncated == json_output
    # Simple string truncation may invalidate JSON,
    # so don't parse result_json.truncated

    # Test log processing (using max_chars)
    log_lines = [
        "2024-01-01T12:01:00 INFO Starting service",
        "2024-01-01T12:01:01 DEBUG Processing request",
    ]
    log_output = "\n".join(log_lines * 50)  # Reduced from 300 repetitions
    result_log: Truncation = processor.process_auto(log_output)
    if len(log_output) > processor.max_chars:
        assert len(result_log.truncated) < len(log_output)
        assert len(result_log.truncated) <= processor.max_chars
        # Check for log markers if budget was small enough
        if processor.max_chars < 1000:  # Heuristic: small budget likely shows marker
            assert "[..." in result_log.truncated
    else:
        assert result_log.truncated == log_output

    # Test YAML processing (using max_chars)
    yaml_base = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": "test"},
        "spec": {
            "containers": [
                {"name": f"cont-{i}", "image": f"img:{i}"} for i in range(20)
            ]
        },
        "status": {"phase": "Running"},
    }  # Reduced containers from 50
    yaml_output = yaml.dump(yaml_base, width=200) * 5  # Reduced from 20 repetitions
    result_yaml: Truncation = processor.process_auto(yaml_output)
    if len(yaml_output) > processor.max_chars:
        assert len(result_yaml.truncated) < len(yaml_output)
        assert len(result_yaml.truncated) <= processor.max_chars
        # Check if some top level keys still exist after potential section truncation
        assert "apiVersion:" in result_yaml.truncated
        assert "kind:" in result_yaml.truncated
    else:
        assert result_yaml.truncated == yaml_output

    # Test plain text processing (uses max_chars for text fallback)
    text_output = "x" * (
        processor.max_chars + 100
    )  # Ensure truncation based on max_chars
    result_text: Truncation = processor.process_auto(text_output)
    # process_auto should use max_chars for text fallback
    if len(text_output) > processor.max_chars:
        assert len(result_text.truncated) <= processor.max_chars
        expected_trunc = tl.truncate_string(text_output, processor.max_chars)
        assert result_text.truncated == expected_trunc
    else:
        assert result_text.truncated == text_output


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


def test_process_auto_llm_budget() -> None:
    """Test process_auto with explicit llm_max_chars budget."""
    processor = OutputProcessor(max_chars=1000, llm_max_chars=50)

    # 1. Test Text Truncation with LLM budget
    long_text = "This is a very long string that needs to be truncated for the LLM." * 3
    assert len(long_text) > processor.llm_max_chars
    result_text = processor.process_auto(long_text, budget=processor.llm_max_chars)
    assert result_text.original_type == "text"
    assert len(result_text.truncated) <= processor.llm_max_chars
    assert result_text.truncated != long_text
    assert "..." in result_text.truncated

    # 2. Test YAML Truncation with LLM budget
    long_yaml_data = {"a": "long string " * 10, "b": {"c": "another long string " * 10}}
    long_yaml = yaml.dump(long_yaml_data)
    assert len(long_yaml) > processor.llm_max_chars
    result_yaml = processor.process_auto(long_yaml, budget=processor.llm_max_chars)
    assert result_yaml.original_type == "yaml"
    assert len(result_yaml.truncated) <= processor.llm_max_chars
    assert result_yaml.truncated != long_yaml

    # 3. Test Logs Truncation with LLM budget
    # Add timestamps to match log detection pattern
    log_lines = [
        f"2024-07-15T10:00:{i:02d} Log line {i} with lots of content " * 2
        for i in range(50)
    ]
    long_logs = "\n".join(log_lines)
    assert len(long_logs) > processor.llm_max_chars
    result_logs = processor.process_auto(long_logs, budget=processor.llm_max_chars)
    assert result_logs.original_type == "logs"  # Re-check this assertion
    assert len(result_logs.truncated) <= processor.llm_max_chars
    assert result_logs.truncated != long_logs

    # 4. Test JSON Truncation with LLM budget (simple string trunc for now)
    long_json_data = {"key": "value " * 50}
    long_json = json.dumps(long_json_data)
    assert len(long_json) > processor.llm_max_chars
    result_json = processor.process_auto(long_json, budget=processor.llm_max_chars)
    assert result_json.original_type == "json"
    assert len(result_json.truncated) <= processor.llm_max_chars
    assert result_json.truncated != long_json
    assert "..." in result_json.truncated  # String truncation marker
