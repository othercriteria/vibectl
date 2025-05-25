"""Tests for edit command resource summarization functionality."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from vibectl.execution.edit import _summarize_resource
from vibectl.types import Error, LLMMetrics, OutputFlags, Success


@pytest.fixture
def sample_deployment_yaml() -> str:
    """Sample deployment YAML for testing."""
    return """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-demo
  namespace: sandbox
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
        image: nginx:1.20
        ports:
        - containerPort: 80
"""


@pytest.fixture
def output_flags() -> OutputFlags:
    """Standard output flags for testing."""
    return OutputFlags(
        show_raw=False,
        show_vibe=True,
        show_kubectl=False,
        warn_no_output=False,
        model_name="claude-3.7-sonnet",
        show_metrics=False,
        show_streaming=False,
    )


@pytest.fixture
def mock_config() -> Mock:
    """Mock config for testing."""
    config = Mock()
    config.get.return_value = "claude-3.7-sonnet"
    return config


@pytest.mark.asyncio
async def test_summarize_resource_returns_plain_text(
    sample_deployment_yaml: str, output_flags: OutputFlags, mock_config: Mock
) -> None:
    """Test that _summarize_resource returns plain text summary, not JSON."""

    # Mock the model adapter to return plain text (not JSON)
    mock_summary_text = """# [bold]Nginx Deployment Configuration[/bold]

**Application:** nginx web server
**Image:** nginx:1.20
**Replicas:** 3 instances
**Namespace:** [blue]sandbox[/blue]

## Configuration Details
**Resources:** No limits set - [yellow]consider adding memory/CPU limits[/yellow]
**Health Checks:** No readiness/liveness probes configured
**Environment:** No custom environment variables
**Storage:** No persistent volumes attached

## Common Edits
- Change replica count for scaling (currently 3)
- Update image version (currently nginx:1.20)
- Add resource limits/requests for better resource management
- Configure health checks for reliability
- Add environment variables for application configuration"""

    mock_metrics = LLMMetrics(
        token_input=100,
        token_output=200,
        latency_ms=1000,
    )

    with patch("vibectl.execution.edit.get_model_adapter") as mock_get_adapter:
        # Setup mock adapter
        mock_adapter = Mock()
        mock_model = Mock()
        mock_get_adapter.return_value = mock_adapter
        mock_adapter.get_model.return_value = mock_model

        # Mock the execute_and_log_metrics to return plain text
        mock_adapter.execute_and_log_metrics = AsyncMock(
            return_value=(mock_summary_text, mock_metrics)
        )

        # Call the function
        result = await _summarize_resource(
            resource_yaml=sample_deployment_yaml,
            output_flags=output_flags,
            config=mock_config,
        )

        # Verify it succeeded and returned plain text
        assert isinstance(result, Success)
        assert result.data == mock_summary_text
        assert result.metrics == mock_metrics

        # Verify the adapter was called with response_model=None (plain text)
        mock_adapter.execute_and_log_metrics.assert_called_once()
        call_args = mock_adapter.execute_and_log_metrics.call_args
        assert call_args[1]["response_model"] is None


@pytest.mark.asyncio
async def test_summarize_resource_handles_empty_response(
    sample_deployment_yaml: str, output_flags: OutputFlags, mock_config: Mock
) -> None:
    """Test that _summarize_resource handles empty LLM responses."""

    with patch("vibectl.execution.edit.get_model_adapter") as mock_get_adapter:
        # Setup mock adapter to return empty response
        mock_adapter = Mock()
        mock_model = Mock()
        mock_get_adapter.return_value = mock_adapter
        mock_adapter.get_model.return_value = mock_model

        mock_adapter.execute_and_log_metrics = AsyncMock(return_value=("", None))

        # Call the function
        result = await _summarize_resource(
            resource_yaml=sample_deployment_yaml,
            output_flags=output_flags,
            config=mock_config,
        )

        # Verify it returns an error for empty response
        assert isinstance(result, Error)
        assert "LLM returned empty response" in result.error


@pytest.mark.asyncio
async def test_summarize_resource_processes_placeholders_correctly(
    sample_deployment_yaml: str, output_flags: OutputFlags, mock_config: Mock
) -> None:
    """Test that placeholders in prompt fragments are correctly replaced."""

    mock_summary_text = "Test summary for nginx-demo deployment"

    with patch("vibectl.execution.edit.get_model_adapter") as mock_get_adapter:
        # Setup mock adapter
        mock_adapter = Mock()
        mock_model = Mock()
        mock_get_adapter.return_value = mock_adapter
        mock_adapter.get_model.return_value = mock_model

        mock_adapter.execute_and_log_metrics = AsyncMock(
            return_value=(mock_summary_text, None)
        )

        # Call the function
        result = await _summarize_resource(
            resource_yaml=sample_deployment_yaml,
            output_flags=output_flags,
            config=mock_config,
        )

        # Verify it succeeded
        assert isinstance(result, Success)

        # Check that the user fragments were processed with the correct replacements
        call_args = mock_adapter.execute_and_log_metrics.call_args
        user_fragments = call_args[1]["user_fragments"]

        # Convert to string to check replacements were made
        user_fragments_text = str(user_fragments)
        assert "nginx-demo" in user_fragments_text  # resource_name replaced
        assert "Deployment" in user_fragments_text  # resource_kind replaced
        # Check for key parts of the YAML instead of the exact string
        assert (
            "apiVersion: apps/v1" in user_fragments_text
        )  # resource_yaml key parts replaced
        assert "image: nginx:1.20" in user_fragments_text  # another distinctive part


@pytest.mark.asyncio
async def test_summarize_resource_handles_invalid_yaml(
    output_flags: OutputFlags, mock_config: Mock
) -> None:
    """Test that _summarize_resource handles invalid YAML gracefully."""

    invalid_yaml = "this is not valid yaml: [unclosed bracket"

    # Call the function with invalid YAML
    result = await _summarize_resource(
        resource_yaml=invalid_yaml, output_flags=output_flags, config=mock_config
    )

    # Should return an error due to YAML parsing failure
    assert isinstance(result, Error)
    assert "Failed to summarize resource" in result.error
