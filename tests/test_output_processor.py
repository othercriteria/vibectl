"""Tests for the output processor module."""

import json
from typing import Any, Dict, List, cast

import pytest

from vibectl.output_processor import OutputProcessor


@pytest.fixture
def processor() -> OutputProcessor:
    """Create an output processor with test settings."""
    return OutputProcessor(max_token_limit=100, truncation_ratio=2)


def test_process_for_llm_no_truncation(processor: OutputProcessor) -> None:
    """Test processing output that doesn't need truncation."""
    output = "Short test output"
    processed, truncated = processor.process_for_llm(output)

    assert processed == output
    assert not truncated


def test_process_for_llm_with_truncation(processor: OutputProcessor) -> None:
    """Test processing output that needs truncation."""
    # Create output that will exceed token limit
    output = "x" * 10000
    processed, truncated = processor.process_for_llm(output)

    # Calculate expected chunk size
    expected_chunk_size = (processor.max_chars - 50) // 2

    assert len(processed) < len(output)
    assert truncated
    assert "[...truncated...]" in processed
    assert processed.startswith(output[:expected_chunk_size])  # First chunk
    assert processed.endswith(output[-expected_chunk_size:])  # Last chunk


def test_process_logs(processor: OutputProcessor) -> None:
    """Test processing log output."""
    logs = "\n".join([f"2024-01-{i:02d} Log entry {i}" for i in range(1, 100)])
    processed, truncated = processor.process_logs(logs)

    assert len(processed) < len(logs)
    assert truncated
    # Should favor recent logs (higher ratio)
    assert "2024-01-99" in processed  # Most recent entry should be present


def test_process_json_valid(processor: OutputProcessor) -> None:
    """Test processing valid JSON output."""
    # Test small JSON (no truncation needed)
    small_data = {"name": "test", "value": 42}
    json_str = json.dumps(small_data)
    processed, truncated = processor.process_json(json_str)
    assert not truncated
    assert processed == json_str

    # Test large JSON (needs truncation)
    large_data = {
        "items": [{"name": f"item-{i}", "value": i} for i in range(100)],
        "metadata": {
            "count": 100,
            "details": {
                "type": "test",
                "nested": {
                    "deep": "value",
                    "items": list(range(100)),
                },
            },
        },
    }

    json_str = json.dumps(large_data)
    processed, truncated = processor.process_json(json_str)

    # Parse the processed output back to verify structure
    processed_data = json.loads(processed)

    # Verify truncation of large arrays
    assert truncated
    assert len(processed_data["items"]) < 100
    assert any(
        isinstance(item, str) and "more items" in item
        for item in processed_data["items"]
    )

    # Verify important keys are preserved
    assert "name" in processed_data["items"][0]

    # Verify nested truncation
    assert isinstance(processed_data["metadata"]["details"]["nested"], dict)


def test_process_json_invalid(processor: OutputProcessor) -> None:
    """Test processing invalid JSON output."""
    invalid_json = "{invalid: json}"
    processed, truncated = processor.process_json(invalid_json)

    # Should fall back to standard truncation
    assert processed == invalid_json
    assert not truncated


def test_truncate_json_object_dict(processor: OutputProcessor) -> None:
    """Test truncating dictionary objects."""
    # Create a large dictionary
    data = {f"key-{i}": f"value-{i}" for i in range(20)}
    data["name"] = "important"  # Important key
    data["status"] = "active"  # Important key

    truncated = cast("Dict[str, Any]", processor._truncate_json_object(data))

    # Important keys should be preserved
    assert "name" in truncated
    assert "status" in truncated

    # Should have summary of truncated items
    assert "..." in truncated
    assert len(truncated) < len(data)


def test_truncate_json_object_list(processor: OutputProcessor) -> None:
    """Test truncating list objects."""
    # Create a large list
    data = list(range(20))

    truncated = cast("List[Any]", processor._truncate_json_object(data))

    # Should keep first and last few items with summary
    assert len(truncated) < len(data)
    assert isinstance(truncated[0], int)  # First items preserved
    assert any(
        isinstance(item, str) and "more items" in item for item in truncated
    )  # Summary included


def test_truncate_json_object_nested(processor: OutputProcessor) -> None:
    """Test truncating nested objects."""
    data = {"level1": {"level2": {"level3": {"level4": "too deep"}}}}

    truncated = cast(
        "Dict[str, Any]", processor._truncate_json_object(data, max_depth=2)
    )

    # Should truncate at max_depth
    assert isinstance(truncated["level1"]["level2"], dict)
    assert len(truncated["level1"]["level2"]) <= 1


def test_format_kubernetes_resource(processor: OutputProcessor) -> None:
    """Test formatting Kubernetes resource references."""
    test_cases = [
        ("pod", "nginx", "pods/nginx"),
        ("deployment", "web", "deployments/web"),
        ("proxy", "envoy", "proxies/envoy"),
        ("policy", "secure", "policies/secure"),
    ]

    for resource_type, name, expected in test_cases:
        result = processor.format_kubernetes_resource(resource_type, name)
        assert result == expected


def test_detect_output_type(processor: OutputProcessor) -> None:
    """Test output type detection."""
    # Test JSON detection
    json_output = json.dumps({"test": "data"})
    assert processor.detect_output_type(json_output) == "json"

    # Test YAML detection
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


def test_process_auto(processor: OutputProcessor) -> None:
    """Test automatic output processing based on type."""
    # Test JSON processing
    json_data = {"items": [{"name": f"item-{i}", "value": i} for i in range(100)]}
    json_output = json.dumps(json_data)
    processed, truncated = processor.process_auto(json_output)
    assert truncated
    assert len(json.loads(processed)["items"]) < 100

    # Test log processing
    log_output = "\n".join(
        [
            "2024-01-01T12:00:00 INFO Starting service",
            "2024-01-01T12:00:01 DEBUG Processing request",
        ]
        * 100
    )
    processed, truncated = processor.process_auto(log_output)
    assert truncated
    assert "2024-01-01T12:00:01" in processed  # Recent logs preserved

    # Test YAML processing
    yaml_output = (
        """
    apiVersion: v1
    kind: Pod
    metadata:
      name: test
    status:
      phase: Running
      conditions:
        - type: Ready
          status: "True"
    """
        * 100
    )  # Make it long enough to trigger truncation
    processed, truncated = processor.process_auto(yaml_output)
    assert truncated
    assert "apiVersion: v1" in processed
    assert "kind: Pod" in processed

    # Test plain text processing
    text_output = "x" * 10000
    processed, truncated = processor.process_auto(text_output)
    assert truncated
    assert "[...truncated...]" in processed


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
    assert sections == {"root": simple_yaml.strip()}

    # Test invalid YAML
    invalid_yaml = "not: valid: yaml: content"
    sections = processor.extract_yaml_sections(invalid_yaml)
    assert sections == {"root": invalid_yaml.strip()}


def test_truncate_yaml_status() -> None:
    """Test truncating YAML status sections."""
    processor = OutputProcessor()

    # Test with status section exceeding threshold
    sections = {
        "metadata": "name: test",
        "spec": "replicas: 3",
        "status": "phase: Running\n"
        + "\n".join([f"condition-{i}: value-{i}" for i in range(100)]),
    }
    truncated = processor.truncate_yaml_status(sections)

    assert len(truncated["status"]) < len(sections["status"])
    assert "[status truncated]" in truncated["status"]
    assert truncated["metadata"] == sections["metadata"]  # Other sections unchanged
    assert truncated["spec"] == sections["spec"]  # Other sections unchanged

    # Test with status section under threshold
    small_sections = {
        "metadata": "name: test",
        "status": "phase: Running",  # Under threshold
    }
    truncated = processor.truncate_yaml_status(small_sections)
    assert truncated["status"] == small_sections["status"]  # No truncation needed

    # Test with no status section
    no_status = {"metadata": "name: test", "spec": "replicas: 3"}
    truncated = processor.truncate_yaml_status(no_status)
    assert truncated == no_status  # No changes needed

    # Test with custom threshold
    custom_sections = {
        "status": "phase: Running\n"
        + "\n".join([f"condition-{i}: value-{i}" for i in range(10)])
    }
    truncated = processor.truncate_yaml_status(custom_sections, threshold=50)
    assert len(truncated["status"]) < len(custom_sections["status"])
    assert "[status truncated]" in truncated["status"]


def test_process_output_for_vibe() -> None:
    """Test processing output specifically for vibe."""
    processor = OutputProcessor()

    # Test with JSON output
    json_data = {
        "items": [{"name": f"item-{i}", "value": i} for i in range(100)],
        "metadata": {"count": 100},
    }
    json_output = json.dumps(json_data)
    processed, truncated = processor.process_output_for_vibe(json_output)
    assert truncated
    processed_data = json.loads(processed)
    assert len(processed_data["items"]) < 100
    assert "metadata" in processed_data

    # Test with YAML output
    yaml_output = (
        """
    apiVersion: v1
    kind: Pod
    metadata:
      name: test-pod
    status:
      phase: Running
      conditions:
      - type: Ready
        status: "True"
        lastTransitionTime: "2024-01-01T00:00:00Z"
        lastProbeTime: "2024-01-01T00:00:00Z"
        message: "Pod is ready"
    """
        * 50
    )  # Make it long enough to trigger truncation
    processed, truncated = processor.process_output_for_vibe(yaml_output)
    assert truncated
    assert "apiVersion: v1" in processed
    assert "kind: Pod" in processed
    assert "[status truncated]" in processed

    # Test with log output
    log_output = "\n".join(
        [
            "2024-01-01T12:00:00 INFO Starting service",
            "2024-01-01T12:00:01 DEBUG Processing request",
        ]
        * 100
    )
    processed, truncated = processor.process_output_for_vibe(log_output)
    assert truncated
    assert "2024-01-01T12:00:01" in processed  # Recent logs preserved

    # Test with plain text
    text_output = "x" * 10000
    processed, truncated = processor.process_output_for_vibe(text_output)
    assert truncated
    assert "[...truncated...]" in processed


def test_find_max_depth_empty_containers() -> None:
    """Test _find_max_depth with empty containers."""
    processor = OutputProcessor()

    # Test with empty dict
    depth = processor._find_max_depth({})
    assert depth == 0

    # Test with empty list
    depth = processor._find_max_depth([])
    assert depth == 0

    # Test with max depth limit
    deeply_nested = {
        "a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": {"i": {"j": {"k": 1}}}}}}}}}}
    }
    depth = processor._find_max_depth(deeply_nested)
    assert depth == 11  # The depth is actually 11 with our test structure
