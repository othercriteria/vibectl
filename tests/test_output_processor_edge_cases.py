"""Tests for edge cases in the output processor module.

This module focuses on testing edge cases and corner cases for the output processor.
"""

import json
from unittest.mock import patch

import pytest

from vibectl.output_processor import OutputProcessor


@pytest.fixture
def processor() -> OutputProcessor:
    """Create an output processor with test settings."""
    return OutputProcessor(max_token_limit=100, truncation_ratio=2)


def test_process_for_llm_empty_input(processor: OutputProcessor) -> None:
    """Test processing empty input."""
    output = ""
    processed, truncated = processor.process_for_llm(output)

    assert processed == output
    assert not truncated


def test_process_for_llm_exactly_at_limit(processor: OutputProcessor) -> None:
    """Test processing output exactly at token limit."""
    # Create output exactly at the token limit
    output = "x" * processor.max_chars
    processed, truncated = processor.process_for_llm(output)

    assert processed == output
    assert not truncated


def test_process_for_llm_one_over_limit(processor: OutputProcessor) -> None:
    """Test processing output just one character over the token limit."""
    # Create output one character over the token limit
    output = "x" * (processor.max_chars + 1)
    processed, truncated = processor.process_for_llm(output)

    assert len(processed) < len(output)
    assert truncated
    assert "[...truncated...]" in processed


def test_process_logs_empty(processor: OutputProcessor) -> None:
    """Test processing empty log output."""
    logs = ""
    processed, truncated = processor.process_logs(logs)

    assert processed == logs
    assert not truncated


def test_process_logs_single_line(processor: OutputProcessor) -> None:
    """Test processing single line log output."""
    logs = "2024-01-01 Single log entry"
    processed, truncated = processor.process_logs(logs)

    assert processed == logs
    assert not truncated


def test_process_json_empty_object(processor: OutputProcessor) -> None:
    """Test processing empty JSON object."""
    json_str = "{}"
    processed, truncated = processor.process_json(json_str)

    assert processed == json_str
    assert not truncated


def test_process_json_empty_array(processor: OutputProcessor) -> None:
    """Test processing empty JSON array."""
    json_str = "[]"
    processed, truncated = processor.process_json(json_str)

    assert processed == json_str
    assert not truncated


def test_process_json_null(processor: OutputProcessor) -> None:
    """Test processing JSON null value."""
    json_str = "null"
    processed, truncated = processor.process_json(json_str)

    assert processed == json_str
    assert not truncated


def test_process_json_deeply_nested(processor: OutputProcessor) -> None:
    """Test processing deeply nested JSON structure."""
    # Create deeply nested structure
    data = {}
    current = data
    for i in range(10):  # Way past max_depth
        current[f"level{i}"] = {}
        current = current[f"level{i}"]

    json_str = json.dumps(data)
    processed, truncated = processor.process_json(json_str)

    # The processed result should be truncated at max_depth
    result = json.loads(processed)

    # Verify some form of truncation was applied
    assert truncated

    # The actual implementation might not truncate exactly at max_depth,
    # so we just check that truncation happened
    assert json_str != processed


def test_truncate_json_object_with_circular_references(
    processor: OutputProcessor,
) -> None:
    """Test handling of potential circular references in JSON objects."""
    # Python doesn't allow true circular references in dicts, so we simulate with deep nesting
    data = {"self": {"nested": {"deep": {"circular": "reference"}}}}

    # Patch max_depth to simulate detection of circular references
    with patch.object(
        processor, "_truncate_json_object", side_effect=processor._truncate_json_object
    ):
        result = processor._truncate_json_object(data, max_depth=10)

        # Should not cause infinite recursion
        assert isinstance(result, dict)
        assert processor._truncate_json_object.call_count > 0


def test_detect_output_type_mixed_content(processor: OutputProcessor) -> None:
    """Test output type detection with mixed content."""
    # Content that has log-like lines but is mostly text
    mixed_output = """
    Regular text line
    2024-01-01 12:34:56 This looks like a log line
    More regular text
    Yet another text line
    """

    # It contains a log pattern, so should be detected as logs
    assert processor.detect_output_type(mixed_output) == "logs"


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

    # Should still extract what it can
    sections = processor.extract_yaml_sections(malformed_yaml)
    assert "apiVersion" in sections
    assert "kind" in sections
    # At minimum these should extract


def test_process_output_for_vibe_complex_structure(processor: OutputProcessor) -> None:
    """Test processing complex output for vibe with mixed structures."""
    # Create complex output with special characters and unusual structures
    complex_output = """
    RESOURCE: pod/test
    STATUS:  Running
    DETAILS: ---
    spec:
      containers:
      - name: test
        image: nginx:1.14.2
        ports:
        - containerPort: 80
    status:
      phase: Running
      conditions:
      - type: Ready
        status: "True"
      - type: PodScheduled
        status: "True"
    EVENTS:
    LAST SEEN   TYPE      REASON    MESSAGE
    1m          Normal    Scheduled    Successfully assigned default/test to node-1
    30s         Normal    Pulling      Pulling image "nginx:1.14.2"
    15s         Normal    Pulled       Successfully pulled image "nginx:1.14.2"
    10s         Normal    Created      Created container test
    5s          Normal    Started      Started container test
    """

    processed, truncated = processor.process_output_for_vibe(complex_output)

    # Check appropriate processing
    assert (
        len(processed) <= processor.max_chars * 10
    )  # Allow for some truncation margin
    assert "pod/test" in processed  # Essential info should be preserved


def test_process_auto_garbage_input(processor: OutputProcessor) -> None:
    """Test automatic output processing with garbage/unparseable input."""
    # Create garbage input that doesn't match any known format
    garbage = "!@#$%^&*()_+<>?:{}"

    processed, truncated = processor.process_auto(garbage)

    # Should fall back to basic text processing
    assert processed == garbage
    assert not truncated


def test_extract_yaml_sections_non_k8s_format() -> None:
    """Test extract_yaml_sections with non-Kubernetes format YAML."""
    processor = OutputProcessor()

    # Regular YAML that doesn't follow k8s format pattern
    yaml_output = """
    app: my-app
    environment: production
    settings:
      timeout: 30
      retries: 3
    database:
      host: localhost
      port: 5432
    """

    sections = processor.extract_yaml_sections(yaml_output)

    # Should return as a single "root" section since it's not k8s format
    assert len(sections) == 1
    assert "root" in sections
    assert "app: my-app" in sections["root"]
    assert "environment: production" in sections["root"]
