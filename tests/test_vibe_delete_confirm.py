"""Tests for the vibe delete confirmation functionality.

This module tests the confirmation functionality in handle_vibe_request for
delete commands.
"""

from unittest.mock import MagicMock, Mock, patch

from vibectl.command_handler import handle_vibe_request


# Note: We need to patch click at the proper import location
@patch("click.confirm")  # Patch the actual click module
@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.command_handler.llm.get_model")
def test_vibe_delete_with_confirmation(
    mock_get_model: MagicMock, mock_run_kubectl: MagicMock, mock_confirm: MagicMock
) -> None:
    """Test delete command with confirmation that gets confirmed."""
    # Setup mocks
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: "pod\nnginx")
    mock_get_model.return_value = mock_model
    mock_confirm.return_value = True  # User confirms deletion
    mock_run_kubectl.return_value = 'pod "nginx" deleted'

    # Execute vibe request with delete command
    handle_vibe_request(
        request="delete the nginx pod",
        command="delete",
        plan_prompt="test prompt {request}",
        summary_prompt_func=lambda: "summary template",
        yes=False,  # Do not skip confirmation
    )

    # Assert
    mock_confirm.assert_called_once()
    mock_run_kubectl.assert_called_once()


@patch("click.confirm")  # Patch the actual click module
@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.command_handler.llm.get_model")
def test_vibe_delete_with_confirmation_cancelled(
    mock_get_model: MagicMock, mock_run_kubectl: MagicMock, mock_confirm: MagicMock
) -> None:
    """Test delete command with confirmation that gets cancelled."""
    # Setup mocks
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: "pod\nnginx")
    mock_get_model.return_value = mock_model
    mock_confirm.return_value = False  # User cancels deletion

    # Execute vibe request with delete command
    handle_vibe_request(
        request="delete the nginx pod",
        command="delete",
        plan_prompt="test prompt {request}",
        summary_prompt_func=lambda: "summary template",
        yes=False,  # Do not skip confirmation
    )

    # Assert
    mock_confirm.assert_called_once()
    # Command should not be executed if cancelled
    mock_run_kubectl.assert_not_called()


@patch("click.confirm")  # Patch the actual click module
@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.command_handler.llm.get_model")
def test_vibe_delete_yes_flag_bypasses_confirmation(
    mock_get_model: MagicMock, mock_run_kubectl: MagicMock, mock_confirm: MagicMock
) -> None:
    """Test that yes flag bypasses confirmation for delete commands."""
    # Setup mocks
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: "pod\nnginx")
    mock_get_model.return_value = mock_model
    mock_run_kubectl.return_value = 'pod "nginx" deleted'

    # Execute vibe request with delete command and yes flag
    handle_vibe_request(
        request="delete the nginx pod",
        command="delete",
        plan_prompt="test prompt {request}",
        summary_prompt_func=lambda: "summary template",
        yes=True,  # Skip confirmation
    )

    # Assert
    mock_confirm.assert_not_called()  # Confirmation should be skipped
    mock_run_kubectl.assert_called_once()  # Command should be executed


@patch("click.confirm")  # Patch the actual click module
@patch("vibectl.command_handler.run_kubectl")
@patch("vibectl.command_handler.llm.get_model")
def test_vibe_non_delete_commands_skip_confirmation(
    mock_get_model: MagicMock, mock_run_kubectl: MagicMock, mock_confirm: MagicMock
) -> None:
    """Test that non-delete commands skip confirmation regardless of yes flag."""
    # Setup mocks
    mock_model = Mock()
    mock_model.prompt.return_value = Mock(text=lambda: "pod\nnginx")
    mock_get_model.return_value = mock_model
    output = "NAME    READY   STATUS    RESTARTS   AGE\n"
    output += "nginx   1/1     Running   0          1h"
    mock_run_kubectl.return_value = output

    # Execute vibe request with get command (not delete)
    handle_vibe_request(
        request="show me the nginx pod",
        command="get",
        plan_prompt="test prompt {request}",
        summary_prompt_func=lambda: "summary template",
        # Even though False, confirmation should be skipped for non-delete
        yes=False,
    )

    # Assert
    # Confirmation should be skipped for non-delete
    mock_confirm.assert_not_called()
    mock_run_kubectl.assert_called_once()  # Command should be executed
