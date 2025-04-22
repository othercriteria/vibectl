from unittest.mock import MagicMock, patch

from vibectl.command_handler import (
    OutputFlags,
    _display_kubectl_command,
    configure_output_flags,
    handle_vibe_request,
)


def test_handle_vibe_request_with_preformatted_prompt() -> None:
    """Test handle_vibe_request with prompt that's already formatted.

    This test characterizes the bug where the prompt is formatted twice, once by the
    caller (like in vibe_cmd.py) and then again in handle_vibe_request, leading to
    an IndexError.
    """
    # Create a simplified version of the PLAN_VIBE_PROMPT template
    vibe_prompt_template = """This is a test prompt.

Memory: "{memory_context}"
Request: "{request}"
"""

    # Format the template with memory_context and request (as in vibe_cmd.py)
    formatted_prompt = vibe_prompt_template.format(
        memory_context="test memory", request="test request"
    )

    # Now the template has literal quotes around the values
    assert 'Memory: "test memory"' in formatted_prompt
    assert 'Request: "test request"' in formatted_prompt

    # In handle_vibe_request, it attempts to format with request and command
    try:
        # The bug only happens when a string with quotes has braces like "{0}"
        # Let's modify our prompt to trigger the issue
        modified_prompt = formatted_prompt + "Command: {0}"

        # This is what happens in handle_vibe_request - format with named arguments
        modified_prompt.format(request="new request", command="test command")

        # If a bug happened, we wouldn't get here, so we fail the test
        raise AssertionError("Expected an IndexError but none was raised")
    except IndexError as e:
        # This is the exact error we expect
        assert "Replacement index 0 out of range for positional args tuple" in str(e)

    # Now let's test what actually happens in the original error
    try:
        # Create a string with a format specifier that expects a positional arg
        weird_template = "Test {0} template with {request} and {command}"

        # Format it with keyword args as happens in handle_vibe_request
        weird_template.format(request="test request", command="test command")

        # If we get here, we got lucky and it still worked
        raise AssertionError("Expected an IndexError but none was raised")
    except IndexError as e:
        # This is the exact error from the bug
        assert "Replacement index 0 out of range for positional args tuple" in str(e)


def test_handle_vibe_request_real_world_failure() -> None:
    """Test the specific real-world failure mode seen in production.

    This test reproduces the failure in handle_vibe_request when a prompt
    contains a positional format specifier like {0} and is formatted with
    keyword arguments, leading to an IndexError.

    This test should FAIL with the current implementation and PASS after
    implementing the fix.
    """
    # Setup mocks to avoid actual command execution
    model_adapter_mock = MagicMock()
    model_mock = MagicMock()
    model_adapter_mock.get_model.return_value = model_mock
    model_adapter_mock.execute.return_value = "get pods"

    # Create a prompt template that has a positional format specifier {0}
    # which could be from user-provided text or model output
    prompt_with_positional_specifier = """Planning command for:
Request: "{request}"
Command: "{command}"

Example output format: {0}
"""

    output_flags = configure_output_flags(
        show_raw_output=False,
        show_vibe=True,
        model=None,
    )

    # Mock additional functions to prevent actual command execution
    with (
        patch(
            "vibectl.command_handler.get_model_adapter", return_value=model_adapter_mock
        ),
        patch(
            "vibectl.command_handler._execute_command",
            side_effect=RuntimeError("error: unknown command"),
        ),
        patch("vibectl.command_handler.handle_command_output"),
        patch("vibectl.command_handler.console_manager"),
        patch("vibectl.command_handler.update_memory"),
    ):
        # Attempt to call handle_vibe_request with a prompt containing
        # positional format specifier
        # This should no longer raise an IndexError after our fix
        handle_vibe_request(
            request="test request",
            command="vibe",
            plan_prompt=prompt_with_positional_specifier,
            summary_prompt_func=lambda: "test prompt",
            output_flags=output_flags,
        )

        # After our fix, the code should successfully execute without IndexError
        # and format the template properly
        model_adapter_mock.execute.assert_any_call(
            model_mock,
            # The formatted prompt should have the {0} removed or replaced
            prompt_with_positional_specifier.replace("{0}", "").format(
                request="test request", command="vibe"
            ),
        )


def test_display_kubectl_command_with_vibe() -> None:
    """Test that command display works correctly with the vibe command."""
    with patch("vibectl.command_handler.console_manager") as mock_console:
        # Create output flags with show_kubectl=True
        output_flags = OutputFlags(
            show_raw=True,
            show_vibe=True,
            warn_no_output=True,
            model_name="test-model",
            show_kubectl=True,
        )

        # Test with just "vibe" command (no request)
        _display_kubectl_command(output_flags, "vibe")
        mock_console.print_note.assert_called_with(
            "Planning next steps based on memory context..."
        )

        # Reset mock for next test
        mock_console.reset_mock()

        # Test with "vibe" plus a request
        _display_kubectl_command(output_flags, "vibe find pods")
        mock_console.print_note.assert_called_with("Note: find pods")

        # Reset mock for next test
        mock_console.reset_mock()

        # Test with non-vibe command
        _display_kubectl_command(output_flags, "get pods")
        mock_console.print_note.assert_called_with("[kubectl] get pods")
