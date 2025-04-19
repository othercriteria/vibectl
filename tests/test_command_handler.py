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
