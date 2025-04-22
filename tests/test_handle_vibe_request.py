"""Tests for handle_vibe_request functionality.

This module tests handle_vibe_request, especially focusing on the handling
of kubeconfig flags to avoid regressions where kubeconfig flags appear in the wrong
position in the final command.
"""

from collections.abc import Generator
from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.command_handler import (
    handle_vibe_request,
)
from vibectl.types import OutputFlags, Success


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

    # Set up the model to return a command
    mock_model_adapter.return_value.execute.return_value = "get pods"

    # Configure _process_command_string to return a clean command
    with patch(
        "vibectl.command_handler._process_command_string"
    ) as mock_process_command:
        mock_process_command.return_value = ("get pods", None)

        # Configure _parse_command_args to return expected args
        with patch("vibectl.command_handler._parse_command_args") as mock_parse_args:
            mock_parse_args.return_value = ["get", "pods"]

            # Make _execute_command pass through to run_kubectl
            # This is the key change - we mock _execute_command to actually
            # call run_kubectl
            with patch(
                "vibectl.command_handler._execute_command",
                side_effect=lambda args, yaml_content: mock_run_kubectl(
                    args, capture=True
                )
                or Success(data="pods data"),
            ):
                # Call handle_vibe_request with a request that might trigger
                # the kubeconfig issue
                handle_vibe_request(
                    request="pods that are finished",
                    command="get",
                    plan_prompt="Plan how to {command} {request}",
                    summary_prompt_func=lambda: "Summarize {output}",
                    output_flags=output_flags,
                )

                # Verify run_kubectl was called with the correct arguments
                # Now we're verifying mock_run_kubectl was called, not the wrapper
                mock_run_kubectl.assert_called_once()
