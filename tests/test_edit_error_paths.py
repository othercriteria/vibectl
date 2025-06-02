"""Tests for error paths and edge cases in edit execution."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from vibectl.config import Config
from vibectl.execution.edit import (
    _apply_patch,
    _fetch_resource,
    _generate_patch_from_changes,
    _generate_summary_diff,
    _invoke_editor,
    _summarize_resource,
    run_intelligent_edit_workflow,
    run_intelligent_vibe_edit_workflow,
)
from vibectl.schema import (
    ActionType,
    EditResourceScopeResponse,
    ErrorAction,
    LLMPlannerResponse,
    ThoughtAction,
)
from vibectl.types import Error, LLMMetrics, MetricsDisplayMode, OutputFlags, Success


class TestEditErrorPaths:
    """Test error paths and edge cases in edit execution."""

    @pytest.fixture
    def output_flags(self) -> OutputFlags:
        """Create output flags for testing."""
        return OutputFlags(
            show_raw_output=False,
            show_vibe=False,
            warn_no_output=False,
            model_name="test-model",
            show_metrics=MetricsDisplayMode.NONE,
            show_kubectl=False,
            warn_no_proxy=True,
            show_streaming=False,
        )

    @pytest.fixture
    def config(self) -> Config:
        """Create config for testing."""
        return Config()

    @pytest.mark.asyncio
    async def test_fetch_resource_error(self, config: Config) -> None:
        """Test _fetch_resource when kubectl returns an error."""
        with patch("vibectl.execution.edit.run_kubectl") as mock_kubectl:
            mock_kubectl.return_value = Error(
                "Resource not found", original_exit_code=1
            )

            result = await _fetch_resource("deployment", ("nginx",), config)

            assert isinstance(result, Error)
            assert "Resource not found" in result.error

    @pytest.mark.asyncio
    async def test_fetch_resource_exception(self, config: Config) -> None:
        """Test _fetch_resource when an exception occurs."""
        with patch("vibectl.execution.edit.run_kubectl") as mock_kubectl:
            mock_kubectl.side_effect = Exception("Network error")

            result = await _fetch_resource("deployment", ("nginx",), config)

            assert isinstance(result, Error)
            assert "Failed to fetch resource: Network error" in result.error

    @pytest.mark.asyncio
    async def test_summarize_resource_empty_response(
        self, output_flags: OutputFlags, config: Config
    ) -> None:
        """Test _summarize_resource when LLM returns empty response."""
        with (
            patch("vibectl.execution.edit.get_model_adapter") as mock_get_adapter,
            patch(
                "vibectl.execution.edit.get_resource_summarization_prompt"
            ) as mock_prompt,
        ):
            mock_adapter = Mock()
            mock_adapter.get_model.return_value = Mock()

            # Create a proper metrics mock instead of Mock()
            from vibectl.types import LLMMetrics

            mock_metrics = LLMMetrics(token_input=10, token_output=5, latency_ms=100.0)

            mock_adapter.execute_and_log_metrics = AsyncMock()
            mock_adapter.execute_and_log_metrics.return_value = ("", mock_metrics)
            mock_get_adapter.return_value = mock_adapter

            mock_prompt.return_value = ([], [])

            result = await _summarize_resource(
                resource_yaml="kind: Deployment\nmetadata:\n  name: test\n",
                output_flags=output_flags,
                config=config,
            )

            assert isinstance(result, Error)
            assert (
                "LLM returned empty response for resource summarization" in result.error
            )

    @pytest.mark.asyncio
    async def test_summarize_resource_invalid_yaml(
        self, output_flags: OutputFlags, config: Config
    ) -> None:
        """Test _summarize_resource with invalid YAML input."""
        result = await _summarize_resource(
            resource_yaml="invalid: yaml: content: [",
            output_flags=output_flags,
            config=config,
        )

        assert isinstance(result, Error)
        assert "Failed to summarize resource" in result.error

    @pytest.mark.asyncio
    async def test_summarize_resource_exception(
        self, output_flags: OutputFlags, config: Config
    ) -> None:
        """Test _summarize_resource when an exception occurs."""
        with patch("vibectl.execution.edit.get_model_adapter") as mock_get_adapter:
            mock_get_adapter.side_effect = Exception("Model error")

            result = await _summarize_resource(
                resource_yaml="kind: Deployment\nmetadata:\n  name: test\n",
                output_flags=output_flags,
                config=config,
            )

            assert isinstance(result, Error)
            assert "Failed to summarize resource: Model error" in result.error

    def test_invoke_editor_cancelled(self) -> None:
        """Test _invoke_editor when user cancels (None returned)."""
        with patch("vibectl.execution.edit.click.edit") as mock_edit:
            mock_edit.return_value = None

            result = _invoke_editor("Original content")

            assert isinstance(result, Error)
            assert "Editor was cancelled" in result.error

    def test_invoke_editor_no_content(self) -> None:
        """Test _invoke_editor when no content is provided."""
        with patch("vibectl.execution.edit.click.edit") as mock_edit:
            mock_edit.return_value = "# Comment only\n"

            result = _invoke_editor("Original content")

            assert isinstance(result, Error)
            assert "Edit was cancelled (no content)" in result.error

    def test_invoke_editor_exception(self) -> None:
        """Test _invoke_editor when an exception occurs."""
        with patch("vibectl.execution.edit.click.edit") as mock_edit:
            mock_edit.side_effect = Exception("Editor error")

            result = _invoke_editor("Original content")

            assert isinstance(result, Error)
            assert "Failed to open editor: Editor error" in result.error

    def test_generate_summary_diff_no_changes(self) -> None:
        """Test _generate_summary_diff when no changes are made."""
        original = "This is the original summary."
        modified = "This is the original summary."

        result = _generate_summary_diff(original, modified)

        # This function returns a string, not a Result object
        assert result == ""

    def test_generate_summary_diff_with_changes(self) -> None:
        """Test _generate_summary_diff when changes are made."""
        original = "This is the original summary."
        modified = "This is the modified summary."

        result = _generate_summary_diff(original, modified)

        # This function returns a string, not a Result object
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_generate_patch_empty_response(
        self, output_flags: OutputFlags, config: Config
    ) -> None:
        """Test _generate_patch_from_changes when LLM returns empty response."""
        with (
            patch("vibectl.execution.edit.get_model_adapter") as mock_get_adapter,
            patch("vibectl.execution.edit.get_patch_generation_prompt") as mock_prompt,
        ):
            mock_adapter = Mock()
            mock_adapter.get_model = Mock()
            mock_adapter.execute_and_log_metrics = AsyncMock()
            mock_adapter.execute_and_log_metrics.return_value = (
                "",
                LLMMetrics(token_input=15, token_output=0, latency_ms=150.0),
            )
            mock_get_adapter.return_value = mock_adapter

            mock_prompt.return_value = ([], [])

            result = await _generate_patch_from_changes(
                resource="deployment",
                args=("nginx",),
                original_summary="original",
                summary_diff="some changes",
                original_yaml="kind: Deployment\nmetadata:\n  name: nginx\n",
                output_flags=output_flags,
                config=config,
            )

            assert isinstance(result, Error)
            assert "LLM returned empty response for patch generation" in result.error

    @pytest.mark.asyncio
    async def test_generate_patch_error_action(
        self, output_flags: OutputFlags, config: Config
    ) -> None:
        """Test _generate_patch_from_changes when LLM returns error action."""
        # Create a proper ErrorAction instead of Mock
        error_action = ErrorAction(
            action_type=ActionType.ERROR, message="Cannot patch this resource"
        )
        mock_response = LLMPlannerResponse(action=error_action)
        response_json = mock_response.model_dump_json()

        with (
            patch("vibectl.execution.edit.get_model_adapter") as mock_get_adapter,
            patch("vibectl.execution.edit.get_patch_generation_prompt") as mock_prompt,
        ):
            mock_adapter = Mock()
            mock_adapter.get_model = Mock()
            mock_adapter.execute_and_log_metrics = AsyncMock()
            mock_adapter.execute_and_log_metrics.return_value = (
                response_json,
                LLMMetrics(token_input=20, token_output=25, latency_ms=200.0),
            )
            mock_get_adapter.return_value = mock_adapter

            mock_prompt.return_value = ([], [])

            result = await _generate_patch_from_changes(
                resource="deployment",
                args=("nginx",),
                original_summary="original",
                summary_diff="some changes",
                original_yaml="kind: Deployment\nmetadata:\n  name: nginx\n",
                output_flags=output_flags,
                config=config,
            )

            assert isinstance(result, Error)
            assert (
                "LLM patch generation error: Cannot patch this resource" in result.error
            )

    @pytest.mark.asyncio
    async def test_generate_patch_unexpected_action_type(
        self, output_flags: OutputFlags, config: Config
    ) -> None:
        """Test _generate_patch_from_changes with unexpected action type."""
        # Create a proper ThoughtAction instead of Mock
        thought_action = ThoughtAction(
            action_type=ActionType.THOUGHT, text="I need to think about this"
        )
        mock_response = LLMPlannerResponse(action=thought_action)
        response_json = mock_response.model_dump_json()

        with (
            patch("vibectl.execution.edit.get_model_adapter") as mock_get_adapter,
            patch("vibectl.execution.edit.get_patch_generation_prompt") as mock_prompt,
        ):
            mock_adapter = Mock()
            mock_adapter.get_model = Mock()
            mock_adapter.execute_and_log_metrics = AsyncMock()
            mock_adapter.execute_and_log_metrics.return_value = (
                response_json,
                LLMMetrics(token_input=20, token_output=25, latency_ms=200.0),
            )
            mock_get_adapter.return_value = mock_adapter

            mock_prompt.return_value = ([], [])

            result = await _generate_patch_from_changes(
                resource="deployment",
                args=("nginx",),
                original_summary="original",
                summary_diff="some changes",
                original_yaml="kind: Deployment\nmetadata:\n  name: nginx\n",
                output_flags=output_flags,
                config=config,
            )

            assert isinstance(result, Error)
            assert "ActionType.THOUGHT" in result.error

    @pytest.mark.asyncio
    async def test_generate_patch_no_commands(
        self, output_flags: OutputFlags, config: Config
    ) -> None:
        """Test _generate_patch_from_changes when no commands are generated."""
        # Create a mock action that has empty commands - bypass validation by mocking
        mock_action = Mock()
        mock_action.action_type = ActionType.COMMAND
        mock_action.commands = []  # Empty commands list

        with (
            patch("vibectl.execution.edit.get_model_adapter") as mock_get_adapter,
            patch("vibectl.execution.edit.get_patch_generation_prompt") as mock_prompt,
            patch(
                "vibectl.execution.edit.LLMPlannerResponse.model_validate_json"
            ) as mock_parse,
        ):
            mock_adapter = Mock()
            mock_adapter.get_model = Mock()
            mock_adapter.execute_and_log_metrics = AsyncMock()
            mock_adapter.execute_and_log_metrics.return_value = (
                '{"action": {}}',
                LLMMetrics(token_input=22, token_output=8, latency_ms=220.0),
            )
            mock_get_adapter.return_value = mock_adapter

            mock_prompt.return_value = ([], [])

            # Mock the parsing to return our mock action with empty commands
            mock_response = Mock()
            mock_response.action = mock_action
            mock_parse.return_value = mock_response

            result = await _generate_patch_from_changes(
                resource="deployment",
                args=("nginx",),
                original_summary="original",
                summary_diff="some changes",
                original_yaml="kind: Deployment\nmetadata:\n  name: nginx\n",
                output_flags=output_flags,
                config=config,
            )

            assert isinstance(result, Error)
            assert "No patch commands generated" in result.error

    @pytest.mark.asyncio
    async def test_apply_patch_kubectl_error(
        self, output_flags: OutputFlags, config: Config
    ) -> None:
        """Test _apply_patch when kubectl patch fails."""
        with patch("vibectl.execution.edit.run_kubectl") as mock_kubectl:
            mock_kubectl.return_value = Error("Patch failed", original_exit_code=1)

            result = await _apply_patch(["deployment", "nginx"], output_flags, config)

            assert isinstance(result, Error)
            assert "Patch failed" in result.error

    @pytest.mark.asyncio
    async def test_apply_patch_exception(
        self, output_flags: OutputFlags, config: Config
    ) -> None:
        """Test _apply_patch when an exception occurs."""
        with patch("vibectl.execution.edit.run_kubectl") as mock_kubectl:
            mock_kubectl.side_effect = Exception("Network error")

            result = await _apply_patch(["deployment", "nginx"], output_flags, config)

            assert isinstance(result, Error)
            assert "Failed to apply patch: Network error" in result.error

    @pytest.mark.asyncio
    async def test_apply_patch_with_show_raw(
        self, output_flags: OutputFlags, config: Config
    ) -> None:
        """Test _apply_patch with show_raw flag enabled."""
        output_flags.show_raw_output = True

        with (
            patch("vibectl.execution.edit.run_kubectl") as mock_kubectl,
            patch("vibectl.execution.edit.console_manager") as mock_console,
        ):
            mock_kubectl.return_value = Success(data='{"kind": "Deployment"}')

            result = await _apply_patch(["deployment", "nginx"], output_flags, config)

            assert isinstance(result, Success)
            mock_console.print.assert_called_once_with('{"kind": "Deployment"}')

    @pytest.mark.asyncio
    async def test_apply_patch_with_show_vibe(
        self, output_flags: OutputFlags, config: Config
    ) -> None:
        """Test _apply_patch with show_vibe flag enabled."""
        output_flags.show_vibe = True

        with (
            patch("vibectl.execution.edit.run_kubectl") as mock_kubectl,
            patch("vibectl.execution.edit.handle_command_output") as mock_handle_output,
        ):
            mock_kubectl.return_value = Success(data='{"kind": "Deployment"}')
            mock_handle_output.return_value = Success(
                message="Deployment updated successfully"
            )

            result = await _apply_patch(["deployment", "nginx"], output_flags, config)

            assert isinstance(result, Success)
            assert (
                result.data is not None
                and "Deployment updated successfully" in result.data
            )

    @pytest.mark.asyncio
    async def test_intelligent_edit_workflow_empty_fetch(
        self, output_flags: OutputFlags, config: Config
    ) -> None:
        """Test intelligent edit workflow with empty fetch result."""
        with patch("vibectl.execution.edit._fetch_resource") as mock_fetch:
            mock_fetch.return_value = Success(data="")  # Empty data

            result = await run_intelligent_edit_workflow(
                resource="deployment",
                args=("nginx",),
                output_flags=output_flags,
                config=config,
            )

            assert isinstance(result, Error)
            assert "Failed to fetch resource: empty response" in result.error

    @pytest.mark.asyncio
    async def test_intelligent_edit_workflow_no_changes(
        self, output_flags: OutputFlags, config: Config
    ) -> None:
        """Test intelligent edit workflow when no changes are made."""
        resource_yaml = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx
"""
        summary = "Nginx deployment with default configuration"

        with (
            patch("vibectl.execution.edit._fetch_resource") as mock_fetch,
            patch("vibectl.execution.edit._summarize_resource") as mock_summarize,
            patch("vibectl.execution.edit._invoke_editor") as mock_editor,
            patch("vibectl.execution.edit.console_manager") as mock_console,
        ):
            mock_fetch.return_value = Success(data=resource_yaml)
            mock_summarize.return_value = Success(data=summary)
            mock_editor.return_value = Success(data=summary)  # No changes

            result = await run_intelligent_edit_workflow(
                resource="deployment",
                args=("nginx",),
                output_flags=output_flags,
                config=config,
            )

            assert isinstance(result, Success)
            assert "No changes made" in result.message
            mock_console.print_note.assert_called_once_with(
                "No changes made to the resource"
            )

    @pytest.mark.asyncio
    async def test_vibe_edit_workflow_empty_response(
        self, output_flags: OutputFlags, config: Config
    ) -> None:
        """Test intelligent vibe edit workflow with empty LLM response."""
        with (
            patch("vibectl.execution.edit.get_model_adapter") as mock_get_adapter,
            patch("vibectl.execution.edit.plan_edit_scope") as mock_plan_scope,
            patch("vibectl.execution.edit.get_memory") as mock_get_memory,
        ):
            mock_adapter = Mock()
            mock_adapter.get_model = Mock()
            mock_adapter.execute_and_log_metrics = AsyncMock()
            mock_adapter.execute_and_log_metrics.return_value = (
                "",
                LLMMetrics(token_input=15, token_output=0, latency_ms=150.0),
            )
            mock_get_adapter.return_value = mock_adapter

            mock_plan_scope.return_value = ([], [])
            mock_get_memory.return_value = "test memory"

            result = await run_intelligent_vibe_edit_workflow(
                request="edit nginx deployment",
                output_flags=output_flags,
                config=config,
            )

            assert isinstance(result, Error)
            assert "LLM returned an empty response for resource scoping" in result.error

    @pytest.mark.asyncio
    async def test_vibe_edit_workflow_no_resources(
        self, output_flags: OutputFlags, config: Config
    ) -> None:
        """Test intelligent vibe edit workflow when no resources are scoped."""
        mock_response = EditResourceScopeResponse(
            resource_selectors=[],  # Empty list
            kubectl_arguments=[],
            edit_context="",
        )
        response_json = mock_response.model_dump_json()

        with (
            patch("vibectl.execution.edit.get_model_adapter") as mock_get_adapter,
            patch("vibectl.execution.edit.plan_edit_scope") as mock_plan_scope,
            patch("vibectl.execution.edit.get_memory") as mock_get_memory,
        ):
            mock_adapter = Mock()
            mock_adapter.get_model = Mock()
            mock_adapter.execute_and_log_metrics = AsyncMock()
            mock_adapter.execute_and_log_metrics.return_value = (
                response_json,
                LLMMetrics(token_input=25, token_output=30, latency_ms=250.0),
            )
            mock_get_adapter.return_value = mock_adapter

            mock_plan_scope.return_value = ([], [])
            mock_get_memory.return_value = "test memory"

            result = await run_intelligent_vibe_edit_workflow(
                request="edit something unclear",
                output_flags=output_flags,
                config=config,
            )

            assert isinstance(result, Error)
            assert "No resources were identified in the request" in result.error

    @pytest.mark.asyncio
    async def test_vibe_edit_workflow_exception(
        self, output_flags: OutputFlags, config: Config
    ) -> None:
        """Test intelligent vibe edit workflow when exception occurs during scoping."""
        with patch("vibectl.execution.edit.get_model_adapter") as mock_get_adapter:
            mock_get_adapter.side_effect = Exception("Model connection error")

            try:
                result = await run_intelligent_vibe_edit_workflow(
                    request="edit nginx deployment",
                    output_flags=output_flags,
                    config=config,
                )

                assert isinstance(result, Error)
                assert (
                    "Failed to scope resources from request" in result.error
                    or "Model connection error" in result.error
                )
            except Exception as e:
                # If the exception propagates, check that it's the expected one
                assert "Model connection error" in str(e)
