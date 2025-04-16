"""Tests for handle_vibe_request functionality.

This module tests handle_vibe_request, especially focusing on the handling
of kubeconfig flags to avoid regressions where kubeconfig flags appear in the wrong
position in the final command.
"""

from collections.abc import Generator
from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.command_handler import OutputFlags, handle_vibe_request


@pytest.fixture
def mock_model_adapter() -> Generator[MagicMock, None, None]:
    """Mock the model adapter to return predictable responses."""
    with patch("vibectl.command_handler.get_model_adapter") as mock_adapter:
        mock_model = Mock()
        mock_adapter.return_value.get_model.return_value = mock_model
        mock_adapter.return_value.execute.return_value = (
            "pods --field-selector=status.phase=Succeeded -n sandbox"
        )
        yield mock_adapter


@pytest.fixture
def mock_run_kubectl() -> Generator[Mock, None, None]:
    """Mock run_kubectl to avoid actual command execution."""
    with patch("vibectl.command_handler.run_kubectl") as mock:
        mock.return_value = (
            "NAME   READY   STATUS      RESTARTS   AGE\n"
            "pod-1   1/1     Succeeded   0          1h"
        )
        yield mock


@pytest.fixture
def mock_console() -> Generator[Mock, None, None]:
    """Mock the console manager to avoid output during tests."""
    with patch("vibectl.command_handler.console_manager") as mock:
        yield mock


@pytest.fixture
def mock_handle_output() -> Generator[Mock, None, None]:
    """Mock handle_command_output to avoid actual output handling."""
    with patch("vibectl.command_handler.handle_command_output") as mock:
        yield mock


def test_handle_vibe_request_kubeconfig_handling(
    mock_model_adapter: MagicMock,
    mock_run_kubectl: Mock,
    mock_console: Mock,
    mock_handle_output: Mock,
) -> None:
    """Test that handle_vibe_request properly handles kubeconfig flags.

    This test verifies that:
    1. The kubeconfig flag is not part of the command passed to run_kubectl
    2. run_kubectl gets a properly filtered command without kubeconfig flags
    """
    # Create output flags
    output_flags = OutputFlags(
        show_raw=True,
        show_vibe=True,
        warn_no_output=False,
        model_name="claude-3-sonnet",
    )

    # Call handle_vibe_request with a request that might trigger the kubeconfig issue
    handle_vibe_request(
        request="pods that are finished",
        command="get",
        plan_prompt="Plan how to {command} {request}",
        summary_prompt_func=lambda: "Summarize {output}",
        output_flags=output_flags,
    )

    # Verify run_kubectl was called with the correct arguments
    mock_run_kubectl.assert_called_once()
    args = mock_run_kubectl.call_args[0][0]

    # Check that no kubeconfig flags are in the command passed to run_kubectl
    assert "--kubeconfig" not in args
    assert not any(arg.startswith("--kubeconfig=") for arg in args)

    # Verify the command type ('get') is correctly prepended as the first parameter
    # This is the expected structure: [command_type, *command_args]
    assert args[0] == "get"
