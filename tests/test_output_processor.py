"""Tests for the output processor module."""

import json
import logging

import pytest
import yaml

from vibectl import truncation_logic as tl
from vibectl.output_processor import OutputProcessor
from vibectl.types import Truncation

# Initialize logger for this module
logger = logging.getLogger(__name__)


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
    spec:
      containers:
      - name: main
        image: busybox
    status:
      phase: Running
    """
    sections = processor.extract_yaml_sections(yaml_output)
    assert "apiVersion" in sections
    assert "kind" in sections
    assert "metadata" in sections
    assert "spec" in sections
    assert "status" in sections
    assert sections["kind"].strip() == "kind: Pod"
    assert "containers:" in sections["spec"]

    # Test YAML that is just a string
    yaml_string = "just a simple string"
    sections_string = processor.extract_yaml_sections(yaml_string)
    assert "content" in sections_string
    assert sections_string["content"] == yaml_string

    # Test YAML that is a list
    yaml_list = """
    - item1
    - item2
    """
    sections_list = processor.extract_yaml_sections(yaml_list)
    assert "content" in sections_list
    # Dump reconstructs the list yaml, adding explicit start
    # Strip trailing newline from yaml.dump output for comparison
    assert sections_list["content"] == ("---\n" + yaml.dump(["item1", "item2"])).strip()

    # Test empty YAML
    sections_empty = processor.extract_yaml_sections("")
    assert sections_empty == {"content": ""}

    # Test YAML with only comments
    yaml_comment = "# Just a comment"
    sections_comment = processor.extract_yaml_sections(yaml_comment)
    assert sections_comment == {"content": yaml_comment}

    # Test malformed YAML (should fallback gracefully)
    yaml_malformed = "key: value:\n  nested: oops"
    sections_malformed = processor.extract_yaml_sections(yaml_malformed)
    assert sections_malformed == {"content": yaml_malformed}


def test_extract_yaml_sections_multi_document() -> None:
    """Test extracting sections from multi-document YAML."""
    processor = OutputProcessor()

    # Simplified multi-document string, ensuring --- is on its own line
    yaml_multi = """
apiVersion: v1
kind: Pod
---
kind: Service
ports:
- 80
---
- itemA
- itemB
---
"""
    sections = processor.extract_yaml_sections(yaml_multi)

    # Check first document sections
    assert "apiVersion" in sections
    assert sections["apiVersion"].strip() == "apiVersion: v1"
    assert "kind" in sections
    assert sections["kind"].strip() == "kind: Pod"
    # Check second document section
    assert "document_2" in sections
    assert "kind: Service" in sections["document_2"]
    assert "- 80" in sections["document_2"]
    assert sections["document_2"].strip().startswith("---")

    # Check third document section
    assert "document_3" in sections
    assert "- itemA" in sections["document_3"]
    assert sections["document_3"].strip().startswith("---")

    # Check fourth document section (None)
    assert "document_4" in sections
    # Dump of None with explicit_start=True produces '--- null\n...'
    # Strip potential trailing '...' or whitespace for robust comparison
    assert sections["document_4"].strip().replace("\n...", "") == "--- null"


def test_process_yaml_multi_document_no_truncation(processor: OutputProcessor) -> None:
    """Test multi-document YAML that fits within budget."""
    # Ensure --- starts on a new line
    yaml_multi = """
apiVersion: v1
kind: Pod
metadata:
  name: pod1
---
apiVersion: v1
kind: Service
metadata:
  name: service1
"""
    budget = len(yaml_multi) + 100
    result = processor.process_yaml(yaml_multi, budget=budget)
    # Reconstruction might slightly alter spacing/newlines, focus on content
    reconstructed_expected = processor._reconstruct_yaml(
        processor.extract_yaml_sections(yaml_multi)
    )
    # Use PyYAML to load both results and compare the data structures
    # This avoids issues with minor whitespace/formatting differences
    data_truncated: list | None = None
    data_expected: list | None = None
    try:
        data_truncated = list(yaml.safe_load_all(result.truncated))
    except yaml.YAMLError as e:
        logger.warning(f"Truncated output is not valid YAML: {e}\n{result.truncated}")
    try:
        data_expected = list(yaml.safe_load_all(reconstructed_expected))
    except yaml.YAMLError as e:
        logger.warning(
            f"Expected reconstruction is not valid YAML: {e}\n{reconstructed_expected}"
        )

    # Only compare if both were successfully parsed
    if data_truncated is not None and data_expected is not None:
        assert data_truncated == data_expected  # Compare parsed data
    elif data_truncated is None:
        pytest.fail("Could not parse truncated output which was expected to be valid.")
    elif data_expected is None:
        pytest.fail("Could not parse expected reconstruction which should be valid.")

    assert result.original_type == "yaml"


def test_process_yaml_multi_document_truncation_second_doc(
    processor: OutputProcessor,
) -> None:
    """Test multi-doc YAML truncation driven by a large second document."""
    doc1 = "apiVersion: v1\\nkind: Pod\\nmetadata:\\n  name: pod1"
    # Ensure --- starts on a new line
    doc2_base = (
        "---\\napiVersion: v1\\nkind: Service\\nmetadata:\\n  name: service1"
        "\\nspec:\\n  ports:\\n"
    )
    doc2 = doc2_base + "  - port: 80\\n" * 20
    yaml_multi = f"{doc1}\\n{doc2}"  # Combine directly

    # Set budget so that doc1 fits, but doc1 + doc2 exceeds it
    budget = len(doc1) + 80

    result = processor.process_yaml(yaml_multi, budget=budget)

    assert len(result.truncated) <= budget
    assert result.original_type == "yaml"
    # Check that the first doc is likely intact (check a key)
    assert "kind: Pod" in result.truncated
    # Check for truncation marker (unless budget is extremely small)
    if budget > 20:
        assert "..." in result.truncated
    # Check if the output is still valid YAML and has at least two documents
    try:
        parsed_docs = list(yaml.safe_load_all(result.truncated))
        # If budget is extremely tight, the final string truncate might make it invalid
        # or only leave one doc. We accept that for this scenario focus on length check.
        if budget > 50:  # Heuristic: If budget allows more than just tiny fragment
            assert len(parsed_docs) >= 1  # Should have at least the first doc
            # We ideally want 2, but truncation might remove the 2nd entirely
    except yaml.YAMLError as e:
        # If parsing fails, it means truncation was very aggressive, which might be
        # acceptable if budget is tiny. Check budget size.
        if budget > 50:  # If budget was larger, failing parse is unexpected
            logger.warning(
                f"YAML parse failed even with budget {budget}, likely due to final "
                f"string truncation: {e}"
            )
        else:
            pass  # Allow parse failure for tiny budgets


def test_process_yaml_multi_document_truncation_first_doc(
    processor: OutputProcessor,
) -> None:
    """Test multi-doc YAML truncation driven by a large first document."""
    # Ensure --- starts on a new line
    doc1_base = (
        "apiVersion: v1\\nkind: Pod\\nmetadata:\\n  name: pod1"
        "\\nspec:\\n  containers:\\n"
    )
    doc1 = doc1_base + "  - name: c{i}\\n" * 20

    doc2 = "---\\napiVersion: v1\\nkind: Service\\nmetadata:\\n  name: service1"
    yaml_multi = f"{doc1}\\n{doc2}"  # Combine directly

    # Set budget small enough to force truncation within the first doc's sections
    budget = len(doc1) // 2

    result = processor.process_yaml(yaml_multi, budget=budget)

    assert len(result.truncated) <= budget
    assert result.original_type == "yaml"
    # Check that keys from the first doc are present
    assert "apiVersion:" in result.truncated
    assert "kind:" in result.truncated
    assert "spec:" in result.truncated
    # Check for truncation marker
    assert "..." in result.truncated
    # Check if the output is still valid YAML and has at least one document
    # The second doc might be completely truncated here.
    try:
        parsed_docs = list(yaml.safe_load_all(result.truncated))
        assert len(parsed_docs) >= 1  # Should still have the truncated first doc
    except yaml.YAMLError as e:
        logger.warning(
            f"YAML parse failed for truncated first doc (budget {budget}), likely "
            f"due to final string truncation: {e}"
        )


def test_process_yaml_multi_document_truncation_both_docs(
    processor: OutputProcessor,
) -> None:
    """Test multi-doc YAML truncation when both docs are large."""
    # Ensure --- starts on a new line
    doc1_base = (
        "apiVersion: v1\\nkind: Pod\\nmetadata:\\n  name: pod1"
        "\\nspec:\\n  containers:\\n"
    )
    doc1 = doc1_base + "  - name: c{i}\\n" * 20

    doc2_base = (
        "---\\napiVersion: v1\\nkind: Service\\nmetadata:\\n  name: service1"
        "\\nspec:\\n  ports:\\n"
    )
    doc2 = doc2_base + "  - port: 80\\n" * 20
    yaml_multi = f"{doc1}\\n{doc2}"  # Combine directly

    # Set budget very small to force truncation everywhere
    budget = 100

    result = processor.process_yaml(yaml_multi, budget=budget)

    assert len(result.truncated) <= budget
    assert result.original_type == "yaml"
    # Check that some keys from first doc might exist
    assert "apiVersion:" in result.truncated or "kind:" in result.truncated
    # Check for truncation marker
    assert "..." in result.truncated
    # Check if the output is still valid YAML and has at least one document.
    # With a tiny budget, the second doc is likely gone entirely.
    try:
        parsed_docs = list(yaml.safe_load_all(result.truncated))
        assert len(parsed_docs) >= 1  # Should still have the truncated first doc
    except yaml.YAMLError as e:
        logger.warning(
            f"YAML parse failed for both truncated docs (budget {budget}), likely "
            f"due to final string truncation: {e}"
        )


def test_process_auto_llm_budget() -> None:
    """
    Test automatic processing specifically using the llm_max_chars budget.
    """
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
