"""
Test execution module for intelligent apply functionality.

This module tests the core functions in vibectl.execution.apply,
focusing on helper functions rather than the full workflow.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pydantic import ValidationError

from vibectl.config import Config
from vibectl.execution.apply import (
    discover_and_validate_files,
    plan_and_execute_final_commands,
    run_intelligent_apply_workflow,
    validate_manifest_content,
)
from vibectl.types import Error, OutputFlags, Success


@pytest.fixture
def test_config() -> Config:
    """Provide a basic Config instance for testing."""
    return Config()


@pytest.fixture
def output_flags() -> OutputFlags:
    """Provide basic OutputFlags for testing."""
    return OutputFlags(
        show_vibe=True,
        show_metrics=False,
        show_raw=False,
        show_kubectl=False,
        warn_no_output=False,
        model_name="test-model",
        warn_no_proxy=False,
    )


# Tests for validate_manifest_content


@pytest.mark.asyncio
async def test_validate_manifest_content_valid_yaml(test_config: Config) -> None:
    """Test validate_manifest_content with valid Kubernetes YAML."""
    valid_yaml = """
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
spec:
  containers:
  - name: nginx
    image: nginx:latest
"""

    with patch("vibectl.execution.apply.run_kubectl_with_yaml") as mock_kubectl:
        mock_kubectl.return_value = Success(
            message="server-side dry-run successful",
            data={"file_path": "test.yaml", "content": valid_yaml},
        )

        result = await validate_manifest_content(
            content=valid_yaml, file_path=Path("test.yaml"), cfg=test_config
        )

        assert isinstance(result, Success)
        assert "valid: Manifest test.yaml is valid" in result.message

        # Verify kubectl was called with dry-run
        mock_kubectl.assert_called_once()
        args, kwargs = mock_kubectl.call_args
        assert "apply" in kwargs["args"]
        assert "--dry-run=server" in kwargs["args"]


@pytest.mark.asyncio
async def test_validate_manifest_content_empty_file(test_config: Config) -> None:
    """Test validate_manifest_content with empty file content."""
    empty_content = ""

    result = await validate_manifest_content(
        content=empty_content, file_path=Path("empty.yaml"), cfg=test_config
    )

    assert isinstance(result, Error)
    assert "empty_file" in result.error
    assert "empty.yaml" in result.error


@pytest.mark.asyncio
async def test_validate_manifest_content_comment_only(test_config: Config) -> None:
    """Test validate_manifest_content with comment-only content."""
    comment_content = "# This is just a comment"

    result = await validate_manifest_content(
        content=comment_content, file_path=Path("comment.yaml"), cfg=test_config
    )

    assert isinstance(result, Error)
    assert "empty_file" in result.error


@pytest.mark.asyncio
async def test_validate_manifest_content_yaml_syntax_error(test_config: Config) -> None:
    """Test validate_manifest_content with invalid YAML syntax."""
    invalid_yaml = """
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
  invalid: [unclosed bracket
"""

    result = await validate_manifest_content(
        content=invalid_yaml, file_path=Path("invalid.yaml"), cfg=test_config
    )

    assert isinstance(result, Error)
    assert "yaml_syntax_error" in result.error


@pytest.mark.asyncio
async def test_validate_manifest_content_dry_run_failure(test_config: Config) -> None:
    """Test validate_manifest_content when kubectl dry-run fails."""
    valid_yaml_syntax = """
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
spec:
  containers:
  - name: nginx
    image: nonexistent:latest
"""

    with patch("vibectl.execution.apply.run_kubectl_with_yaml") as mock_kubectl:
        mock_kubectl.return_value = Error(error="dry-run failed: image not found")

        result = await validate_manifest_content(
            content=valid_yaml_syntax, file_path=Path("test.yaml"), cfg=test_config
        )

        assert isinstance(result, Error)
        assert "dry_run_error" in result.error
        assert "test.yaml" in result.error


@pytest.mark.asyncio
async def test_validate_manifest_content_kubectl_not_found(test_config: Config) -> None:
    """Test validate_manifest_content when kubectl is not found."""
    valid_yaml = """
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
"""

    with patch("vibectl.execution.apply.run_kubectl_with_yaml") as mock_kubectl:
        mock_kubectl.return_value = Error(
            error="kubectl not found", exception=FileNotFoundError("kubectl not found")
        )

        result = await validate_manifest_content(
            content=valid_yaml, file_path=Path("test.yaml"), cfg=test_config
        )

        assert isinstance(result, Error)
        assert "kubectl not found" in result.error


# Tests for discover_and_validate_files


@pytest.mark.asyncio
async def test_discover_and_validate_files_single_valid_file(
    test_config: Config, tmp_path: Path
) -> None:
    """Test discover_and_validate_files with a single valid manifest file."""
    # Create a temporary valid manifest file
    manifest_file = tmp_path / "deployment.yaml"
    manifest_content = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-deployment
spec:
  replicas: 3
  selector:
    matchLabels:
      app: nginx
  template:
    metadata:
      labels:
        app: nginx
    spec:
      containers:
      - name: nginx
        image: nginx:latest
"""
    manifest_file.write_text(manifest_content)

    with patch("vibectl.execution.apply.validate_manifest_content") as mock_validate:
        mock_validate.return_value = Success(
            message="valid manifest",
            data={"file_path": str(manifest_file), "content": manifest_content},
        )

        valid_manifests, invalid_sources = await discover_and_validate_files(
            file_selectors=[str(manifest_file)], cfg=test_config
        )

        assert len(valid_manifests) == 1
        assert len(invalid_sources) == 0
        assert valid_manifests[0][0] == manifest_file.resolve()
        assert valid_manifests[0][1] == manifest_content


@pytest.mark.asyncio
async def test_discover_and_validate_files_non_kubernetes_file(
    test_config: Config, tmp_path: Path
) -> None:
    """Test discover_and_validate_files with a non-Kubernetes file."""
    # Create a file that doesn't look like Kubernetes YAML
    non_k8s_file = tmp_path / "config.yaml"
    non_k8s_content = """
database:
  host: localhost
  port: 5432
application:
  name: myapp
"""
    non_k8s_file.write_text(non_k8s_content)

    valid_manifests, invalid_sources = await discover_and_validate_files(
        file_selectors=[str(non_k8s_file)], cfg=test_config
    )

    assert len(valid_manifests) == 0
    assert len(invalid_sources) == 1
    assert invalid_sources[0][0] == non_k8s_file.resolve()
    assert "not_kubernetes" in invalid_sources[0][2]


@pytest.mark.asyncio
async def test_discover_and_validate_files_directory(
    test_config: Config, tmp_path: Path
) -> None:
    """Test discover_and_validate_files with a directory containing multiple files."""
    # Create a directory with multiple files
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Valid Kubernetes file
    valid_file = manifests_dir / "deployment.yaml"
    valid_content = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-deployment
"""
    valid_file.write_text(valid_content)

    # Non-Kubernetes file
    invalid_file = manifests_dir / "config.txt"
    invalid_file.write_text("This is not YAML")

    with patch("vibectl.execution.apply.validate_manifest_content") as mock_validate:
        mock_validate.return_value = Success(
            message="valid manifest",
            data={"file_path": str(valid_file), "content": valid_content},
        )

        valid_manifests, invalid_sources = await discover_and_validate_files(
            file_selectors=[str(manifests_dir)], cfg=test_config
        )

        # Should find the valid YAML file and mark the txt file as invalid
        assert len(valid_manifests) == 1
        assert len(invalid_sources) == 1
        assert valid_manifests[0][0] == valid_file.resolve()


@pytest.mark.asyncio
async def test_discover_and_validate_files_nonexistent_path(
    test_config: Config,
) -> None:
    """Test discover_and_validate_files with nonexistent file path."""
    nonexistent_path = "/path/that/does/not/exist"

    valid_manifests, invalid_sources = await discover_and_validate_files(
        file_selectors=[nonexistent_path], cfg=test_config
    )

    assert len(valid_manifests) == 0
    assert len(invalid_sources) == 1
    assert "Not a file or directory" in invalid_sources[0][2]


@pytest.mark.asyncio
async def test_discover_and_validate_files_unreadable_file(
    test_config: Config, tmp_path: Path
) -> None:
    """Test discover_and_validate_files with unreadable file."""
    unreadable_file = tmp_path / "unreadable.yaml"
    unreadable_file.write_text("test content")

    with patch.object(Path, "read_text") as mock_read:
        mock_read.side_effect = PermissionError("Permission denied")

        valid_manifests, invalid_sources = await discover_and_validate_files(
            file_selectors=[str(unreadable_file)], cfg=test_config
        )

        assert len(valid_manifests) == 0
        assert len(invalid_sources) == 1
        assert "Read error" in invalid_sources[0][2]


# Tests for run_intelligent_apply_workflow (early exception cases)


@pytest.mark.asyncio
async def test_run_intelligent_apply_workflow_empty_llm_response(
    test_config: Config, output_flags: OutputFlags
) -> None:
    """Test run_intelligent_apply_workflow on empty file scoping response."""
    with (
        patch("vibectl.execution.apply.get_model_adapter") as mock_adapter,
        patch("vibectl.execution.apply.tempfile.TemporaryDirectory") as mock_temp,
    ):
        # Mock model adapter to return empty response
        mock_adapter_instance = Mock()
        mock_adapter_instance.get_model.return_value = Mock()
        mock_adapter_instance.execute_and_log_metrics = AsyncMock(
            return_value=("", {"test": "metrics"})
        )
        mock_adapter.return_value = mock_adapter_instance

        # Mock temp directory
        mock_temp_instance = Mock()
        mock_temp_instance.name = "/tmp/test"
        mock_temp.return_value = mock_temp_instance

        result = await run_intelligent_apply_workflow(
            request="test request", cfg=test_config, output_flags=output_flags
        )

        assert isinstance(result, Error)
        assert "LLM returned an empty response for file scoping" in result.error
        assert result.metrics == {"test": "metrics"}


@pytest.mark.asyncio
async def test_run_intelligent_apply_workflow_json_parse_error(
    test_config: Config, output_flags: OutputFlags
) -> None:
    """Test run_intelligent_apply_workflow on invalid JSON file scoping response."""
    with (
        patch("vibectl.execution.apply.get_model_adapter") as mock_adapter,
        patch("vibectl.execution.apply.tempfile.TemporaryDirectory") as mock_temp,
    ):
        # Mock model adapter to return invalid JSON
        mock_adapter_instance = Mock()
        mock_adapter_instance.get_model.return_value = Mock()
        mock_adapter_instance.execute_and_log_metrics = AsyncMock(
            return_value=("invalid json {", {"test": "metrics"})
        )
        mock_adapter.return_value = mock_adapter_instance

        # Mock temp directory
        mock_temp_instance = Mock()
        mock_temp_instance.name = "/tmp/test"
        mock_temp.return_value = mock_temp_instance

        result = await run_intelligent_apply_workflow(
            request="test request", cfg=test_config, output_flags=output_flags
        )

        assert isinstance(result, Error)
        assert "Failed to parse LLM file scope response" in result.error


@pytest.mark.asyncio
async def test_run_intelligent_apply_workflow_kubectl_not_found_early(
    test_config: Config, output_flags: OutputFlags
) -> None:
    """Test run_intelligent_apply_workflow stops early when kubectl is not found."""
    with (
        patch("vibectl.execution.apply.get_model_adapter") as mock_adapter,
        patch("vibectl.execution.apply.discover_and_validate_files") as mock_discover,
        patch("vibectl.execution.apply.tempfile.TemporaryDirectory") as mock_temp,
    ):
        # Mock successful LLM response for file scoping
        mock_adapter_instance = Mock()
        mock_adapter_instance.get_model.return_value = Mock()
        mock_adapter_instance.execute_and_log_metrics = AsyncMock(
            return_value=(
                '{"file_selectors": ["test.yaml"], '
                '"remaining_request_context": "test"}',
                {"test": "metrics"},
            )
        )
        mock_adapter.return_value = mock_adapter_instance

        # Mock discovery to return kubectl not found error
        mock_discover.return_value = (
            [],  # no valid manifests
            [
                (Path("test.yaml"), None, "CRITICAL: kubectl not found")
            ],  # critical error
        )

        # Mock temp directory
        mock_temp_instance = Mock()
        mock_temp_instance.name = "/tmp/test"
        mock_temp.return_value = mock_temp_instance

        result = await run_intelligent_apply_workflow(
            request="test request", cfg=test_config, output_flags=output_flags
        )

        assert isinstance(result, Error)
        assert "Critical setup error" in result.error
        assert "kubectl not found" in result.error


@pytest.mark.asyncio
async def test_plan_and_execute_final_commands_success(test_config: Config) -> None:
    """Test successful planning and execution of final commands."""
    # Mock data
    semantically_valid_manifests: list[tuple[Path, str]] = [
        (Path("/tmp/test1.yaml"), "apiVersion: v1\nkind: Pod")
    ]
    corrected_temp_manifest_paths: list[Path] = [Path("/tmp/corrected.yaml")]
    unresolvable_sources: list[tuple[Path, str]] = [
        (Path("/tmp/broken.yaml"), "Could not parse YAML")
    ]
    updated_operation_memory = "test operation memory"
    llm_remaining_request = "test remaining request"

    # Mock LLM response
    mock_llm_response = {
        "planned_commands": [
            {
                "action_type": "COMMAND",
                "commands": ["-f", "/tmp/test1.yaml"],
                "yaml_manifest": None,
                "allowed_exit_codes": [0],
                "reasoning": "Apply test manifest",
            }
        ]
    }

    # Mock model adapter and model
    mock_model_adapter = Mock()
    mock_model = Mock()

    # Mock execute_and_log_metrics to return our mock response
    mock_model_adapter.execute_and_log_metrics = AsyncMock(
        return_value=(json.dumps(mock_llm_response), {"tokens": 100})
    )

    # Mock execute_planned_commands to return success
    with patch("vibectl.execution.apply.execute_planned_commands") as mock_execute:
        mock_execute.return_value = Success(
            message="All commands executed successfully", data="test output"
        )

        result = await plan_and_execute_final_commands(
            semantically_valid_manifests=semantically_valid_manifests,
            corrected_temp_manifest_paths=corrected_temp_manifest_paths,
            unresolvable_sources=unresolvable_sources,
            updated_operation_memory=updated_operation_memory,
            llm_remaining_request=llm_remaining_request,
            model_adapter=mock_model_adapter,
            llm_model=mock_model,
            cfg=test_config,
            output_flags=OutputFlags(
                show_raw=False,
                show_vibe=False,
                warn_no_output=False,
                model_name="test-model",
                show_metrics=False,
            ),
        )

        # Verify result
        assert isinstance(result, Success)
        assert result.message == "All commands executed successfully"

        # Verify LLM was called correctly
        mock_model_adapter.execute_and_log_metrics.assert_called_once()

        # Verify command execution was called
        mock_execute.assert_called_once()


@pytest.mark.asyncio
async def test_plan_and_execute_final_commands_parse_error(test_config: Config) -> None:
    """Test handling of LLM response parsing errors in final commands."""
    # Mock data
    semantically_valid_manifests: list[tuple[Path, str]] = []
    corrected_temp_manifest_paths: list[Path] = []
    unresolvable_sources: list[tuple[Path, str]] = []
    updated_operation_memory = "test operation memory"
    llm_remaining_request = "test remaining request"

    # Mock model adapter and model
    mock_model_adapter = Mock()
    mock_model = Mock()

    # Mock execute_and_log_metrics to return invalid JSON
    mock_model_adapter.execute_and_log_metrics = AsyncMock(
        return_value=("invalid json response", {"tokens": 50})
    )

    result = await plan_and_execute_final_commands(
        semantically_valid_manifests=semantically_valid_manifests,
        corrected_temp_manifest_paths=corrected_temp_manifest_paths,
        unresolvable_sources=unresolvable_sources,
        updated_operation_memory=updated_operation_memory,
        llm_remaining_request=llm_remaining_request,
        model_adapter=mock_model_adapter,
        llm_model=mock_model,
        cfg=test_config,
        output_flags=OutputFlags(
            show_raw=False,
            show_vibe=False,
            warn_no_output=False,
            model_name="test-model",
            show_metrics=False,
        ),
    )

    # Verify error result
    assert isinstance(result, Error)
    assert "Failed to parse LLM final plan" in result.error
    assert isinstance(result.exception, ValidationError)
