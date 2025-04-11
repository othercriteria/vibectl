"""Tests focused on the delete confirmation behavior in vibe delete commands."""

from collections.abc import Generator
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from vibectl.command_handler import handle_vibe_request


@pytest.fixture
def mock_confirm() -> Generator[MagicMock, None, None]:
    """Mock click.confirm function."""
    with patch("click.confirm") as mock:
        yield mock


@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.model_adapter.llm")
def test_vibe_delete_with_confirmation(
    mock_llm: MagicMock, 
    mock_run_kubectl: MagicMock,
    mock_console: MagicMock, 
    mock_confirm: MagicMock
) -> None:
    """Test delete command with confirmation dialog."""
    # Set up mocks
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: "kubectl delete pod test-pod")
    mock_llm.get_model.return_value = mock_model
    
    # Set confirmation to True (accept)
    mock_confirm.return_value = True

    # Call function
    handle_vibe_request(
        request="delete the test pod",
        command="delete",  # The actual command, not "delete vibe"
        plan_prompt="Test plan prompt",
        summary_prompt_func=lambda: "Test summary prompt",
        yes=False,  # Confirm before executing
    )

    # Verify confirmation was shown
    mock_confirm.assert_called_once()
    
    # Verify kubectl was called with delete command
    mock_run_kubectl.assert_called_once()


@patch("vibectl.command_handler.console_manager") 
@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.model_adapter.llm")
def test_vibe_delete_with_confirmation_cancelled(
    mock_llm: MagicMock,
    mock_run_kubectl: MagicMock,
    mock_console: MagicMock, 
    mock_confirm: MagicMock
) -> None:
    """Test delete command with confirmation dialog cancelled."""
    # Set up mocks
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: "kubectl delete pod test-pod")
    mock_llm.get_model.return_value = mock_model
    
    # Set confirmation to False (cancel)
    mock_confirm.return_value = False

    # Call function
    handle_vibe_request(
        request="delete the test pod",
        command="delete",  # The actual command, not "delete vibe"
        plan_prompt="Test plan prompt",
        summary_prompt_func=lambda: "Test summary prompt",
        yes=False,  # Confirm before executing
    )

    # Verify confirmation was shown
    mock_confirm.assert_called_once()
    
    # Verify cancelled message was shown
    mock_console.print_cancelled.assert_called_once()
    
    # Verify kubectl was NOT called 
    mock_run_kubectl.assert_not_called()


@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.model_adapter.llm")
def test_vibe_delete_yes_flag_bypasses_confirmation(
    mock_llm: MagicMock,
    mock_run_kubectl: MagicMock,
    mock_console: MagicMock,
    mock_confirm: MagicMock,
) -> None:
    """Test delete command with --yes flag that bypasses confirmation."""
    # Set up mocks
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: "kubectl delete pod test-pod")
    mock_llm.get_model.return_value = mock_model

    # Call function with yes=True
    handle_vibe_request(
        request="delete the test pod",
        command="delete",  # The actual command, not "delete vibe"
        plan_prompt="Test plan prompt",
        summary_prompt_func=lambda: "Test summary prompt",
        yes=True,  # Skip confirmation
    )

    # Verify confirmation was NOT shown
    mock_confirm.assert_not_called()
    
    # Verify kubectl was called
    mock_run_kubectl.assert_called_once()


@patch("vibectl.command_handler.console_manager")
@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.model_adapter.llm")
def test_vibe_non_delete_commands_skip_confirmation(
    mock_llm: MagicMock,
    mock_run_kubectl: MagicMock,
    mock_console: MagicMock,
    mock_confirm: MagicMock,
) -> None:
    """Test non-delete commands don't require confirmation."""
    # Set up mocks
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: "kubectl get pods")
    mock_llm.get_model.return_value = mock_model

    # Call function with a non-delete command
    handle_vibe_request(
        request="get all pods",
        command="get",  # The actual command, not "get vibe"
        plan_prompt="Test plan prompt",
        summary_prompt_func=lambda: "Test summary prompt",
        yes=False,  # Even with yes=False, non-delete commands don't need confirmation
    )

    # Verify confirmation was NOT shown for get command
    mock_confirm.assert_not_called()
    
    # Verify kubectl was called
    mock_run_kubectl.assert_called_once()
