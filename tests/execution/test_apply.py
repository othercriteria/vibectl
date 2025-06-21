"""
Test execution module for intelligent apply functionality.

This module tests the core functions in vibectl.execution.apply,
focusing on helper functions rather than the full workflow.
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from pydantic import ValidationError

from vibectl.config import Config
from vibectl.execution.apply import (
    discover_and_validate_files,
    execute_planned_commands,
    plan_and_execute_final_commands,
    run_intelligent_apply_workflow,
    validate_manifest_content,
)
from vibectl.types import (
    Error,
    LLMMetrics,
    LLMMetricsAccumulator,
    MetricsDisplayMode,
    OutputFlags,
    Success,
)


@pytest.fixture
def test_config() -> Config:
    """Provide a basic Config instance for testing."""
    return Config()


@pytest.fixture
def output_flags() -> OutputFlags:
    """Provide basic OutputFlags for testing."""
    return OutputFlags(
        show_vibe=True,
        show_metrics=MetricsDisplayMode.NONE,
        show_raw_output=False,
        show_kubectl=False,
        warn_no_output=False,
        model_name="test-model",
        warn_no_proxy=False,
        show_streaming=False,
    )


def create_test_metrics_accumulator() -> LLMMetricsAccumulator:
    """Helper to create a test metrics accumulator."""
    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.NONE,
        show_kubectl=False,
        warn_no_proxy=False,
        show_streaming=False,
    )
    return LLMMetricsAccumulator(output_flags)


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
        patch("vibectl.model_adapter.get_model_adapter") as mock_adapter,
        patch("vibectl.execution.apply.tempfile.TemporaryDirectory") as mock_temp,
    ):
        # Mock model adapter to return empty response
        mock_adapter_instance = Mock()
        mock_adapter_instance.get_model.return_value = Mock()
        mock_adapter_instance.execute_and_log_metrics = AsyncMock(
            return_value=(
                "",
                LLMMetrics(token_input=0, token_output=0, latency_ms=0.0, call_count=0),
            )
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
        assert isinstance(result.metrics, LLMMetrics)
        assert result.metrics.token_input == 0
        assert result.metrics.token_output == 0


@pytest.mark.asyncio
async def test_run_intelligent_apply_workflow_json_parse_error(
    test_config: Config, output_flags: OutputFlags
) -> None:
    """Test run_intelligent_apply_workflow on invalid JSON file scoping response."""
    with (
        patch("vibectl.model_adapter.get_model_adapter") as mock_adapter,
        patch("vibectl.execution.apply.tempfile.TemporaryDirectory") as mock_temp,
    ):
        # Mock model adapter to return invalid JSON
        mock_adapter_instance = Mock()
        mock_adapter_instance.get_model.return_value = Mock()
        mock_adapter_instance.execute_and_log_metrics = AsyncMock(
            return_value=(
                "invalid json {",
                LLMMetrics(token_input=0, token_output=0, latency_ms=0.0, call_count=0),
            )
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
        patch("vibectl.model_adapter.get_model_adapter") as mock_adapter,
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
                LLMMetrics(token_input=0, token_output=0, latency_ms=0.0, call_count=0),
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
@patch("vibectl.model_adapter.get_model_adapter")
async def test_plan_and_execute_final_commands_success(
    mock_get_model_adapter: MagicMock, test_config: Config
) -> None:
    """Test plan_and_execute_final_commands with successful execution."""
    # Mock data for the function
    semantically_valid_manifests = [
        (Path("deployment.yaml"), "apiVersion: apps/v1\nkind: Deployment"),
        (Path("service.yaml"), "apiVersion: v1\nkind: Service"),
    ]
    corrected_temp_manifest_paths = [Path("/tmp/corrected_config.yaml")]
    unresolvable_sources = [(Path("broken.yaml"), "syntax error")]
    updated_operation_memory = "deployment/nginx configured"
    llm_remaining_request = "apply to staging namespace"

    # Mock the model and adapter
    mock_adapter = AsyncMock()
    mock_get_model_adapter.return_value = mock_adapter

    # Mock the LLM response for final planning
    mock_plan_response = {
        "planned_commands": [
            {
                "action_type": "COMMAND",
                "commands": ["-f", "deployment.yaml"],
                "yaml_manifest": None,
                "allowed_exit_codes": [0],
                "explanation": "Apply deployment manifest",
            }
        ]
    }

    mock_adapter.execute_and_log_metrics.return_value = (
        json.dumps(mock_plan_response),
        LLMMetrics(token_input=10, token_output=20, latency_ms=100.0, call_count=1),
    )

    with patch("vibectl.execution.apply.run_kubectl") as mock_kubectl:
        mock_kubectl.return_value = Success(
            message="apply successful", data='{"items": []}'
        )

        with patch("vibectl.execution.apply.handle_command_output") as mock_output:
            mock_output.return_value = Success(
                message="deployment applied successfully"
            )

            with patch("vibectl.execution.apply.asyncio.to_thread") as mock_thread:
                mock_thread.side_effect = lambda func, *args, **kwargs: func(
                    *args, **kwargs
                )

                result = await plan_and_execute_final_commands(
                    semantically_valid_manifests,
                    corrected_temp_manifest_paths,
                    unresolvable_sources,
                    updated_operation_memory,
                    llm_remaining_request,
                    None,
                    test_config,
                    OutputFlags(
                        show_raw_output=False,
                        show_vibe=True,
                        warn_no_output=False,
                        model_name="test-model",
                        show_metrics=MetricsDisplayMode.NONE,
                        show_kubectl=False,
                        warn_no_proxy=False,
                        show_streaming=False,
                    ),
                    LLMMetricsAccumulator(
                        OutputFlags(
                            show_raw_output=False,
                            show_vibe=True,
                            warn_no_output=False,
                            model_name="test-model",
                            show_metrics=MetricsDisplayMode.NONE,
                            show_kubectl=False,
                            warn_no_proxy=False,
                            show_streaming=False,
                        )
                    ),
                )

                assert isinstance(result, Success)
                assert "successfully" in result.message.lower()


@pytest.mark.asyncio
@patch("vibectl.model_adapter.get_model_adapter")
async def test_plan_and_execute_final_commands_parse_error(
    mock_get_model_adapter: MagicMock, test_config: Config
) -> None:
    """Test plan_and_execute_final_commands when LLM response can't be parsed."""
    mock_adapter = AsyncMock()
    mock_get_model_adapter.return_value = mock_adapter

    # Mock LLM to return non-parseable response
    mock_adapter.execute_and_log_metrics.side_effect = (
        ValidationError.from_exception_data(
            "Test",
            [
                {
                    "type": "json_invalid",
                    "loc": (),
                    "input": "invalid json",
                    "ctx": {"error": "Invalid JSON"},
                }
            ],
        )
    )

    result = await plan_and_execute_final_commands(
        semantically_valid_manifests=[],
        corrected_temp_manifest_paths=[],
        unresolvable_sources=[],
        updated_operation_memory="",
        llm_remaining_request="",
        _llm_model=None,
        cfg=test_config,
        output_flags=OutputFlags(
            show_raw_output=False,
            show_vibe=True,
            warn_no_output=False,
            model_name="test-model",
            show_metrics=MetricsDisplayMode.NONE,
            show_kubectl=False,
            warn_no_proxy=False,
            show_streaming=False,
        ),
        llm_metrics_accumulator=create_test_metrics_accumulator(),
    )

    assert isinstance(result, Error)
    assert "parse" in result.error.lower() or "validation" in result.error.lower()


# Tests for execute_planned_commands


@pytest.mark.asyncio
async def test_execute_planned_commands_single_success(test_config: Config) -> None:
    """Test execute_planned_commands with a single successful command."""
    from vibectl.schema import CommandAction

    planned_commands = [
        CommandAction(
            action_type="COMMAND",
            commands=["-f", "deployment.yaml"],
            explanation="Apply deployment manifest",
            yaml_manifest=None,
            allowed_exit_codes=[0],
        )
    ]

    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.NONE,
        show_kubectl=False,
        warn_no_proxy=False,
        show_streaming=False,
    )

    with patch("vibectl.execution.apply.run_kubectl") as mock_kubectl:
        mock_kubectl.return_value = Success(
            message="apply successful", data='{"items": []}'
        )

        with patch("vibectl.execution.apply.handle_command_output") as mock_output:
            mock_output.return_value = Success(
                message="deployment applied successfully"
            )

            with patch("vibectl.execution.apply.asyncio.to_thread") as mock_thread:
                mock_thread.side_effect = lambda func, *args, **kwargs: func(
                    *args, **kwargs
                )

                result = await execute_planned_commands(
                    planned_commands,
                    test_config,
                    output_flags,
                    create_test_metrics_accumulator(),
                )

                assert isinstance(result, Success)
                assert "successfully" in result.message.lower()


@pytest.mark.asyncio
async def test_execute_planned_commands_with_yaml_manifest(test_config: Config) -> None:
    """Test execute_planned_commands with a command that uses YAML manifest."""
    from vibectl.schema import CommandAction

    yaml_content = """
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
"""

    planned_commands = [
        CommandAction(
            action_type="COMMAND",
            commands=["-f", "-"],
            explanation="Apply YAML manifest from stdin",
            yaml_manifest=yaml_content,
            allowed_exit_codes=[0],
        )
    ]

    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.NONE,
        show_kubectl=False,
        warn_no_proxy=False,
        show_streaming=False,
    )

    with patch("vibectl.execution.apply.run_kubectl_with_yaml") as mock_kubectl_yaml:
        mock_kubectl_yaml.return_value = Success(
            message="apply successful",
            data='{"items": [{"metadata": {"name": "test-pod"}}]}',
        )

        with patch("vibectl.execution.apply.handle_command_output") as mock_output:
            mock_output.return_value = Success(message="pod/test-pod created")

            with patch("vibectl.execution.apply.asyncio.to_thread") as mock_thread:

                def mock_to_thread_side_effect(
                    func: Any, *args: Any, **kwargs: Any
                ) -> Any:
                    # Handle parameter name mismatch: cmd -> args
                    # for run_kubectl_with_yaml
                    if func.__name__ == "run_kubectl_with_yaml" and "cmd" in kwargs:
                        kwargs["args"] = kwargs.pop("cmd")
                        # Call the mocked version instead of the real function
                        return mock_kubectl_yaml(*args, **kwargs)
                    return func(*args, **kwargs)

                mock_thread.side_effect = mock_to_thread_side_effect

                result = await execute_planned_commands(
                    planned_commands,
                    test_config,
                    output_flags,
                    create_test_metrics_accumulator(),
                )

                assert isinstance(result, Success)
                mock_kubectl_yaml.assert_called_once()
                # Verify the YAML content was passed
                call_args = mock_kubectl_yaml.call_args
                assert call_args[1]["yaml_content"] == yaml_content


@pytest.mark.asyncio
async def test_execute_planned_commands_kubectl_failure(test_config: Config) -> None:
    """Test execute_planned_commands when kubectl command fails."""
    from vibectl.schema import CommandAction

    planned_commands = [
        CommandAction(
            action_type="COMMAND",
            commands=["-f", "nonexistent.yaml"],
            explanation="Apply nonexistent file",
            yaml_manifest=None,
            allowed_exit_codes=[0],
        )
    ]

    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.NONE,
        show_kubectl=False,
        warn_no_proxy=False,
        show_streaming=False,
    )

    with patch("vibectl.execution.apply.run_kubectl") as mock_kubectl:
        mock_kubectl.return_value = Error(error="file not found: nonexistent.yaml")

        with patch("vibectl.execution.apply.asyncio.to_thread") as mock_thread:
            mock_thread.side_effect = lambda func, *args, **kwargs: func(
                *args, **kwargs
            )

            result = await execute_planned_commands(
                planned_commands,
                test_config,
                output_flags,
                create_test_metrics_accumulator(),
            )

            assert isinstance(result, Error)
            assert "failed" in result.error.lower()


@pytest.mark.asyncio
async def test_execute_planned_commands_empty_command_list(test_config: Config) -> None:
    """Test execute_planned_commands with a command that has empty command list."""
    from vibectl.schema import CommandAction

    planned_commands = [
        CommandAction(
            action_type="COMMAND",
            commands=["-f", "-"],  # Use stdin to make it valid
            explanation="Apply via stdin",
            yaml_manifest="apiVersion: v1\nkind: Pod\nmetadata:\n  name: test",
            allowed_exit_codes=[0],
        )
    ]

    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.NONE,
        show_kubectl=False,
        warn_no_proxy=False,
        show_streaming=False,
    )

    # Manually test the empty command list case by checking the function logic
    # when planned_cmd_response.commands is empty after being set
    with patch("vibectl.execution.apply.run_kubectl_with_yaml") as mock_kubectl:
        mock_kubectl.return_value = Success(
            message="apply successful", data='{"items": []}'
        )

        with patch("vibectl.execution.apply.handle_command_output") as mock_output:
            mock_output.return_value = Success(message="resource applied")

            with patch("vibectl.execution.apply.asyncio.to_thread") as mock_thread:
                mock_thread.side_effect = lambda func, *args, **kwargs: func(
                    *args, **kwargs
                )

                # Test with a modified command action that has empty commands
                # after construction
                planned_commands[0].commands = []  # Set to empty after construction

                result = await execute_planned_commands(
                    planned_commands,
                    test_config,
                    output_flags,
                    create_test_metrics_accumulator(),
                )

                assert isinstance(result, Error)
                assert "failed" in result.error.lower()


@pytest.mark.asyncio
async def test_execute_planned_commands_all_empty_commands(test_config: Config) -> None:
    """Test execute_planned_commands when all commands have empty command lists."""
    from vibectl.schema import CommandAction

    # Create multiple commands that will all fail due to empty command lists
    planned_commands = [
        CommandAction(
            action_type="COMMAND",
            commands=["-f", "-"],  # Will be cleared to simulate the issue
            explanation="First command",
            yaml_manifest="apiVersion: v1\nkind: Pod\nmetadata:\n  name: test1",
            allowed_exit_codes=[0],
        ),
        CommandAction(
            action_type="COMMAND",
            commands=["-f", "-"],  # Will be cleared to simulate the issue
            explanation="Second command",
            yaml_manifest="apiVersion: v1\nkind: Service\nmetadata:\n  name: test2",
            allowed_exit_codes=[0],
        ),
    ]

    # Clear commands after construction to test empty command handling
    planned_commands[0].commands = []
    planned_commands[1].commands = []

    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.NONE,
        show_kubectl=False,
        warn_no_proxy=False,
        show_streaming=False,
    )

    result = await execute_planned_commands(
        planned_commands, test_config, output_flags, create_test_metrics_accumulator()
    )

    # Should return Error since all commands failed due to empty command lists
    assert isinstance(result, Error)
    assert "failed" in result.error.lower()  # "Some planned commands failed."


@pytest.mark.asyncio
async def test_execute_planned_commands_multiple_commands_mixed_results(
    test_config: Config,
) -> None:
    """Test execute_planned_commands with multiple commands having mixed results."""
    from vibectl.schema import CommandAction

    planned_commands = [
        CommandAction(
            action_type="COMMAND",
            commands=["-f", "good.yaml"],
            explanation="Apply good manifest",
            yaml_manifest=None,
            allowed_exit_codes=[0],
        ),
        CommandAction(
            action_type="COMMAND",
            commands=["-f", "bad.yaml"],
            explanation="Apply bad manifest",
            yaml_manifest=None,
            allowed_exit_codes=[0],
        ),
    ]

    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.NONE,
        show_kubectl=False,
        warn_no_proxy=False,
        show_streaming=False,
    )

    def mock_kubectl_side_effect(*args: Any, **kwargs: Any) -> Success | Error:
        cmd = kwargs.get("cmd", args[0] if args else [])
        if "good.yaml" in str(cmd):
            return Success(message="apply successful", data='{"items": []}')
        else:
            return Error(error="file not found: bad.yaml")

    with patch("vibectl.execution.apply.run_kubectl") as mock_kubectl:
        mock_kubectl.side_effect = mock_kubectl_side_effect

        with patch("vibectl.execution.apply.handle_command_output") as mock_output:
            mock_output.return_value = Success(message="resource applied")

            with patch("vibectl.execution.apply.asyncio.to_thread") as mock_thread:
                mock_thread.side_effect = lambda func, *args, **kwargs: func(
                    *args, **kwargs
                )

                result = await execute_planned_commands(
                    planned_commands,
                    test_config,
                    output_flags,
                    create_test_metrics_accumulator(),
                )

                assert isinstance(result, Error)
                assert "failed" in result.error.lower()


@pytest.mark.asyncio
async def test_execute_planned_commands_yaml_manifest_without_stdin(
    test_config: Config,
) -> None:
    """Test execute_planned_commands with YAML manifest but command without stdin."""
    from vibectl.schema import CommandAction

    yaml_content = "apiVersion: v1\nkind: Pod"

    planned_commands = [
        CommandAction(
            action_type="COMMAND",
            commands=["-f", "deployment.yaml"],  # File, not stdin
            explanation="Apply file with unnecessary YAML",
            yaml_manifest=yaml_content,  # This should be ignored
            allowed_exit_codes=[0],
        )
    ]

    output_flags = OutputFlags(
        show_raw_output=False,
        show_vibe=True,
        warn_no_output=False,
        model_name="test-model",
        show_metrics=MetricsDisplayMode.NONE,
        show_kubectl=False,
        warn_no_proxy=False,
        show_streaming=False,
    )

    with patch("vibectl.execution.apply.run_kubectl") as mock_kubectl:
        mock_kubectl.return_value = Success(
            message="apply successful", data='{"items": []}'
        )

        with patch("vibectl.execution.apply.handle_command_output") as mock_output:
            mock_output.return_value = Success(message="deployment applied")

            with patch("vibectl.execution.apply.asyncio.to_thread") as mock_thread:
                mock_thread.side_effect = lambda func, *args, **kwargs: func(
                    *args, **kwargs
                )

                result = await execute_planned_commands(
                    planned_commands,
                    test_config,
                    output_flags,
                    create_test_metrics_accumulator(),
                )

                assert isinstance(result, Success)
                # Should use run_kubectl, not run_kubectl_with_yaml
                mock_kubectl.assert_called_once()
