"""Tests for prompt module.

This module tests the prompt templates and formatting functions used for LLM
interactions.

Test Policy:
1. Structural Tests:
   - Focus on existence of prompts and their basic structure
   - Verify presence of required placeholders (e.g. {output}, {request})
   - Check that prompts are non-empty and reasonably sized
   - Avoid testing specific wording/phrasing which may change frequently

2. Semantic Tests:
   - Use parametrized tests to enforce consistent requirements across prompts
   - Focus on critical elements that must be present (e.g. formatting instructions)
   - Minimize coupling to specific phrasings
   - Document any semantic requirements that are enforced
"""

import datetime
import json
from unittest.mock import patch

import pytest

from vibectl.config import Config
from vibectl.prompt import (
    PLAN_CLUSTER_INFO_PROMPT,
    PLAN_CREATE_PROMPT,
    PLAN_DELETE_PROMPT,
    PLAN_DESCRIBE_PROMPT,
    PLAN_EVENTS_PROMPT,
    PLAN_GET_PROMPT,
    PLAN_LOGS_PROMPT,
    PLAN_PORT_FORWARD_PROMPT,
    PLAN_ROLLOUT_PROMPT,
    PLAN_SCALE_PROMPT,
    PLAN_VERSION_PROMPT,
    PLAN_WAIT_PROMPT,
    create_planning_prompt,
    get_formatting_fragments,
    memory_fuzzy_update_prompt,
    memory_update_prompt,
    port_forward_prompt,
    recovery_prompt,
    vibe_autonomous_prompt,
    wait_resource_prompt,
)
from vibectl.schema import LLMPlannerResponse, CommandAction, ActionType

# Import new types
from vibectl.types import (
    Examples,
    Fragment,
    PromptFragments,
    SystemFragments,
    UserFragments,
)

_TEST_SCHEMA_JSON = json.dumps(LLMPlannerResponse.model_json_schema())


# TODO: replace with fragment_current_time test...
# def test_refresh_datetime() -> None:
#     """Test refresh_datetime returns correct format."""
#     # Mock datetime to ensure consistent test
#     mock_now = datetime.datetime(2024, 3, 20, 10, 30, 45)
#     with patch("datetime.datetime") as mock_datetime:
#         mock_datetime.now.return_value = mock_now
#         result = refresh_datetime()
#         assert result == "2024-03-20 10:30:45"


def test_get_formatting_fragments_no_custom(test_config: Config) -> None:
    """Test get_formatting_fragments without custom instructions."""
    fixed_dt = datetime.datetime(2024, 3, 20, 10, 30, 45)
    fixed_dt_str = fixed_dt.strftime("%Y-%m-%d %H:%M:%S")
    test_config.set("custom_instructions", None)
    test_config.set(
        "memory_enabled", False
    )  # This doesn't affect get_formatting_fragments directly

    # Patch datetime.now specifically within the vibectl.prompt module
    with patch("vibectl.prompt.datetime") as mock_prompt_datetime:
        mock_prompt_datetime.now.return_value = fixed_dt
        system_fragments, user_fragments = get_formatting_fragments(test_config)

        all_fragments = system_fragments + user_fragments
        assert len(all_fragments) > 1  # Expect at least base formatting and time
        combined_text = "\n".join(all_fragments)

        assert len(combined_text) > 100
        assert "rich.Console() markup syntax" in combined_text
        assert (
            f"Current time is {fixed_dt_str}." in combined_text
        )  # Check for specific time string
        assert "Custom instructions:" not in combined_text
        assert (
            "Memory context:" not in combined_text
        )  # Explicitly does not include memory


def test_get_formatting_fragments_with_custom(test_config: Config) -> None:
    """Test get_formatting_fragments with custom instructions."""
    fixed_dt = datetime.datetime(2024, 3, 20, 10, 30, 45)
    fixed_dt_str = fixed_dt.strftime("%Y-%m-%d %H:%M:%S")
    test_config.set("custom_instructions", "Test custom instruction")
    test_config.set("memory_enabled", False)

    with patch("vibectl.prompt.datetime") as mock_prompt_datetime:
        mock_prompt_datetime.now.return_value = fixed_dt
        system_fragments, user_fragments = get_formatting_fragments(test_config)
        combined_text = "\n".join(system_fragments + user_fragments)

        assert "Custom instructions:" in combined_text
        assert "Test custom instruction" in combined_text
        assert f"Current time is {fixed_dt_str}." in combined_text
        assert (
            "Memory context:" not in combined_text
        )  # Explicitly does not include memory


def test_get_formatting_fragments_with_memory(test_config: Config) -> None:
    """Test get_formatting_fragments correctly excludes memory."""
    fixed_dt = datetime.datetime(2024, 3, 20, 10, 30, 45)
    test_config.set("custom_instructions", None)
    test_config.set(
        "memory_enabled", True
    )  # This setting is for callers, not get_formatting_fragments

    with patch("vibectl.prompt.datetime") as mock_prompt_datetime:
        mock_prompt_datetime.now.return_value = fixed_dt
        # Mocking get_memory and is_memory_enabled is not needed here as
        # get_formatting_fragments is documented to exclude memory.
        system_fragments, user_fragments = get_formatting_fragments(test_config)
        combined_text = "\n".join(system_fragments + user_fragments)

        assert (
            "Memory context:" not in combined_text
        )  # Verify memory is NOT included by this function


# Semantic requirements that all prompts must meet
@pytest.mark.parametrize(
    "prompt_func_name",  # Test against name to fetch func, helps with typing
    [
        "get_resource_prompt",
        "describe_resource_prompt",
        "logs_prompt",
        "create_resource_prompt",
        "cluster_info_prompt",
        "version_prompt",
        "events_prompt",
        "delete_resource_prompt",
        "scale_resource_prompt",
        "wait_resource_prompt",
        "rollout_status_prompt",
        "rollout_history_prompt",
        "rollout_general_prompt",
        "port_forward_prompt",
    ],
)
def test_prompt_semantic_requirements(
    prompt_func_name: str, test_config: Config
) -> None:
    """Test semantic requirements for various prompt functions.

    These functions primarily use create_summary_prompt, which in turn uses
    get_formatting_fragments. So, they should return PromptFragments and
    include base formatting and time.
    port_forward_prompt takes an optional config and returns PromptFragments,
    similar to other summarized prompts.
    """
    # Dynamically get the function from vibectl.prompt
    # Ensure vibectl.prompt is imported or use getattr on the imported module
    import vibectl.prompt

    prompt_func = getattr(vibectl.prompt, prompt_func_name)

    fixed_dt = datetime.datetime(2024, 3, 20, 10, 30, 45)
    fixed_dt_str = fixed_dt.strftime("%Y-%m-%d %H:%M:%S")

    with patch("vibectl.prompt.datetime") as mock_prompt_datetime:
        mock_prompt_datetime.now.return_value = fixed_dt

        # All listed prompt functions take optional config and return PromptFragments.
        system_fragments, user_fragments = prompt_func(config=test_config)

        combined_text = "\n".join(system_fragments + user_fragments)

        assert "rich.Console() markup syntax" in combined_text
        assert f"Current time is {fixed_dt_str}." in combined_text
        assert 100 < len(combined_text) < 3000  # Reasonable size limits
        # Memory context should NOT be here unless the specific prompt adds it,
        # or its test explicitly sets it up and calls a higher-level assembler.
        # create_summary_prompt relies on its caller for memory.
        assert "Memory context:" not in combined_text


@pytest.mark.parametrize(
    "prompt_func_name,required_placeholder",
    [
        ("get_resource_prompt", "{output}"),
        ("describe_resource_prompt", "{output}"),
        ("logs_prompt", "{output}"),
        ("create_resource_prompt", "{output}"),
        ("cluster_info_prompt", "{output}"),
        ("version_prompt", "{output}"),
        ("events_prompt", "{output}"),
        ("delete_resource_prompt", "{output}"),
        ("scale_resource_prompt", "{output}"),
        ("wait_resource_prompt", "{output}"),
        ("rollout_status_prompt", "{output}"),
        ("rollout_history_prompt", "{output}"),
        ("rollout_general_prompt", "{output}"),
        ("port_forward_prompt", "{output}"),
    ],
)
def test_prompt_structure(
    prompt_func_name: str, required_placeholder: str, test_config: Config
) -> None:
    """Test basic structure of prompts that return PromptFragments."""
    import vibectl.prompt

    prompt_func = getattr(vibectl.prompt, prompt_func_name)

    if prompt_func_name == "port_forward_prompt":
        system_fragments, user_fragments = prompt_func(config=test_config)  # type: ignore[operator]
    else:
        system_fragments, user_fragments = prompt_func(config=test_config)  # type: ignore[operator]

    combined_text = "\n".join(system_fragments + user_fragments)

    assert len(combined_text) > 100  # Should be reasonably sized
    assert required_placeholder in combined_text  # Required placeholder


def test_create_planning_prompt_structure_and_content() -> None:
    """Verify the structure and content generated by create_planning_prompt."""
    command = "test-cmd"
    description = "testing the command"
    examples_data = [
        (
            "request 1",
            {
                "action_type": ActionType.COMMAND.value,
                "commands": ["arg1", "val1"],
            },
        ),
        (
            "request 2",
            {
                "action_type": ActionType.COMMAND.value,
                "commands": ["arg2", "--flag"],
            },
        ),
    ]

    system_fragments, user_fragments = create_planning_prompt(
        command=command,
        description=description,
        examples=Examples(examples_data),
        schema_definition=_TEST_SCHEMA_JSON,
    )

    combined_prompt = "\n".join(system_fragments + user_fragments)

    assert isinstance(system_fragments, list)
    assert isinstance(user_fragments, list)
    assert len(combined_prompt) > 100

    assert (
        f"You are planning arguments for the 'kubectl {command}' command"
        in combined_prompt
    )
    assert f"which is used for {description}." in combined_prompt
    assert (
        "respond with a JSON\nobject matching the provided schema." in combined_prompt
    )
    # __MEMORY_CONTEXT_PLACEHOLDER__ is NOT added by create_planning_prompt itself.
    # It's added by the assembler (e.g. plan_vibe_fragments)
    assert "__MEMORY_CONTEXT_PLACEHOLDER__" not in combined_prompt
    assert "__REQUEST_PLACEHOLDER__" not in combined_prompt  # Also added by assembler

    # Verify example formatting
    assert '- Target: "request 1" -> \nExpected JSON output:' in combined_prompt
    assert '"action_type": "COMMAND"' in combined_prompt

    assert _TEST_SCHEMA_JSON in combined_prompt


def test_create_planning_prompt_raises_without_schema() -> None:
    """Verify create_planning_prompt raises ValueError if schema is missing."""
    with pytest.raises(ValueError, match="schema_definition must be provided"):
        create_planning_prompt(
            command="test",
            description="test",
            examples=Examples([]),
            schema_definition=None,
        )


@pytest.mark.parametrize(
    "plan_prompt_constant_fragments",
    [
        PLAN_GET_PROMPT,
        PLAN_DESCRIBE_PROMPT,
        PLAN_LOGS_PROMPT,
        PLAN_VERSION_PROMPT,
        PLAN_CLUSTER_INFO_PROMPT,
        PLAN_EVENTS_PROMPT,
        PLAN_DELETE_PROMPT,
        PLAN_SCALE_PROMPT,
        PLAN_WAIT_PROMPT,
        PLAN_ROLLOUT_PROMPT,
        PLAN_PORT_FORWARD_PROMPT,
    ],
)
def test_plan_prompt_constants_are_generated(
    plan_prompt_constant_fragments: PromptFragments,
) -> None:
    """Test that all plan prompt constants are generated correctly.
    These constants are defined by calling create_planning_prompt.
    """
    system_fragments, user_fragments = plan_prompt_constant_fragments
    combined_text = "\n".join(system_fragments + user_fragments)

    assert isinstance(system_fragments, list)
    assert isinstance(user_fragments, list)
    assert len(combined_text) > 100

    assert "You are planning arguments for the 'kubectl" in combined_text
    assert "respond with a JSON\nobject matching the provided schema." in combined_text


def test_plan_create_prompt_structure() -> None:
    """Basic structural check for the unique PLAN_CREATE_PROMPT."""
    system_fragments, user_fragments = PLAN_CREATE_PROMPT
    combined_text = "\n".join(system_fragments + user_fragments)
    assert isinstance(combined_text, str)
    # Request placeholder is NOT part of create_planning_prompt's direct output
    assert "__REQUEST_PLACEHOLDER__" not in combined_text
    assert "YAML manifest" in combined_text


def test_memory_update_prompt(test_config: Config) -> None:
    """Verify memory_update_prompt structure."""
    test_config.set("memory_max_chars", 300)
    fixed_dt = datetime.datetime(2024, 3, 20, 10, 30, 45)
    fixed_dt_str = fixed_dt.strftime("%Y-%m-%d %H:%M:%S")
    dummy_memory_content = "dummy_current_memory"
    expected_memory_fragment_str = f"Previous Memory:\n{dummy_memory_content}"

    with patch("vibectl.prompt.datetime") as mock_prompt_datetime:
        mock_prompt_datetime.now.return_value = fixed_dt
        system_fragments, user_fragments = memory_update_prompt(
            command_message="dummy_command",
            command_output="dummy_command_output",
            vibe_output="dummy_vibe_output",
            current_memory=dummy_memory_content,
            config=test_config,
        )

    # Ensure the fragment exists as expected in the list of user fragments
    assert expected_memory_fragment_str in user_fragments, (
        "Expected memory fragment not found in user_fragments. "
        f"User fragments: {user_fragments}"
    )

    combined_text = "\n".join(system_fragments + user_fragments)

    assert (
        "update the memory" in combined_text
    )  # From FRAGMENT_MEMORY_ASSISTANT or specific instruction
    assert (
        "Be concise. Limit your response to 300 characters." in combined_text
    )  # From fragment_concision
    assert (
        f"Current time is {fixed_dt_str}." in combined_text
    )  # From fragment_current_time
    # Check if the exact string is in the combined text
    assert expected_memory_fragment_str in combined_text  # From fragment_memory_context
    assert (
        "Interaction:\nAction: dummy_command" in combined_text
    )  # From fragment_interaction


def test_memory_fuzzy_update_prompt(test_config: Config) -> None:
    """Verify memory_fuzzy_update_prompt structure."""
    test_config.set("memory_max_chars", 400)
    fixed_dt = datetime.datetime(2024, 3, 20, 10, 30, 45)
    fixed_dt_str = fixed_dt.strftime("%Y-%m-%d %H:%M:%S")
    fuzzy_memory_content = "fuzzy_current_memory"
    expected_fuzzy_memory_fragment_str = f"Previous Memory:\n{fuzzy_memory_content}"

    with patch("vibectl.prompt.datetime") as mock_prompt_datetime:
        mock_prompt_datetime.now.return_value = fixed_dt
        system_fragments, user_fragments = memory_fuzzy_update_prompt(
            current_memory=fuzzy_memory_content,
            update_text="fuzzy_update_text",
            config=test_config,
        )

    # Ensure the fragment exists as expected in the list of user fragments
    assert expected_fuzzy_memory_fragment_str in user_fragments, (
        "Expected memory fragment not found in user_fragments. "
        f"User fragments: {user_fragments}"
    )

    combined_text = "\n".join(system_fragments + user_fragments)

    assert "update the memory" in combined_text
    assert "Be concise. Limit your response to 400 characters." in combined_text
    assert f"Current time is {fixed_dt_str}." in combined_text
    # Check if the exact string is in the combined text
    assert expected_fuzzy_memory_fragment_str in combined_text
    assert "User Update: fuzzy_update_text" in combined_text


def test_recovery_prompt(test_config: Config) -> None:  # Added test_config
    """Test recovery prompt generation."""
    command = "get pods"
    error = "Error: the server doesn't have a resource type 'pods'"
    current_memory_dummy = "Previous attempt context."
    fixed_dt = datetime.datetime(2024, 3, 20, 10, 30, 45)
    fixed_dt_str = fixed_dt.strftime("%Y-%m-%d %H:%M:%S")
    test_config.set("memory_max_chars", 250)

    with patch("vibectl.prompt.datetime") as mock_prompt_datetime:
        mock_prompt_datetime.now.return_value = fixed_dt
        system_fragments, user_fragments = recovery_prompt(
            failed_command=command,
            error_output=error,
            current_memory=current_memory_dummy,  # Not used by current recovery_prompt
            original_explanation=None,
            config=test_config,
        )
    combined_result = "\n".join(system_fragments + user_fragments)

    assert "Failed Command:" in combined_result
    assert command in combined_result
    assert "Error Output:" in combined_result
    assert "suggest potential next steps" in combined_result  # Changed assertion
    assert f"Current time is {fixed_dt_str}." in combined_result
    assert "Be concise. Limit your response to 250 characters." in combined_result


def test_vibe_autonomous_prompt(test_config: Config) -> None:
    """Verify the structure of the vibe autonomous prompt."""
    # vibe_autonomous_prompt uses get_formatting_fragments, which includes time.
    # It does NOT include memory from get_formatting_fragments; it would need to add it.
    # The user fragment for {output} is added by vibe_autonomous_prompt itself.
    fixed_dt = datetime.datetime(2024, 3, 20, 10, 30, 45)
    fixed_dt_str = fixed_dt.strftime("%Y-%m-%d %H:%M:%S")

    with patch("vibectl.prompt.datetime") as mock_prompt_datetime:
        mock_prompt_datetime.now.return_value = fixed_dt
        system_fragments, user_fragments = vibe_autonomous_prompt(config=test_config)

    combined_text = "\n".join(system_fragments + user_fragments)

    assert "Analyze this kubectl command output" in combined_text
    assert (
        f"Current time is {fixed_dt_str}." in combined_text
    )  # From get_formatting_fragments
    assert (
        "Memory context:" not in combined_text
    )  # As get_formatting_fragments excludes it
    assert "{output}" in combined_text


def test_vibe_autonomous_prompt_formatting(test_config: Config) -> None:
    """Test that the vibe autonomous prompt can be formatted correctly,
    even when formatting instructions contain braces (simulating memory context).
    """
    mock_memory_content_in_formatting = '{"key": "value with {braces}"}'
    fixed_dt = datetime.datetime(2024, 3, 20, 10, 30, 45)

    # Mock get_formatting_fragments to simulate it returning some base system fragments
    # (including the custom one with braces) and the standard user fragment it produces.
    # vibe_autonomous_prompt itself will add {output} to user_fragments.
    def mock_gff_side_effect(
        config: Config | None = None,
    ) -> tuple[SystemFragments, UserFragments]:
        # Simulate datetime.now being called inside the real get_formatting_fragments
        # or rather, fragment_current_time which it calls.
        # This mock needs to be for vibectl.prompt.datetime.now if
        # fragment_current_time calls it directly.
        with patch("vibectl.prompt.datetime") as mock_inner_dt:
            mock_inner_dt.now.return_value = fixed_dt
            # Construct what get_formatting_fragments would return
            # Base formatting + custom + time
            mock_sys_frags = SystemFragments(
                [
                    Fragment(
                        "Format your response using rich.Console() markup syntax..."
                    ),
                    Fragment(
                        f"Custom instructions:\\n{mock_memory_content_in_formatting}"
                    ),
                    Fragment(
                        f"Current time is {fixed_dt.strftime('%Y-%m-%d %H:%M:%S')}."
                    ),
                ]
            )
            # Standard user fragment from get_formatting_fragments
            mock_user_frags = UserFragments(
                [Fragment("Important:\\n- Timestamps in the future...")]
            )
        return mock_sys_frags, mock_user_frags

    with patch(
        "vibectl.prompt.get_formatting_fragments", side_effect=mock_gff_side_effect
    ):
        system_fragments, user_fragments_template = vibe_autonomous_prompt(
            config=test_config
        )

    test_output = "This is some test output."
    filled_user_fragments = [
        frag.format(output=test_output) if "{output}" in frag else frag
        for frag in user_fragments_template
    ]

    formatted_prompt = "\n".join(system_fragments + filled_user_fragments)

    assert "Format your response using rich.Console() markup syntax" in formatted_prompt
    assert (
        f"Custom instructions:\\n{mock_memory_content_in_formatting}"
        in formatted_prompt
    )
    assert (
        f"Current time is {fixed_dt.strftime('%Y-%m-%d %H:%M:%S')}." in formatted_prompt
    )
    assert (
        "This is some test output." in formatted_prompt
    )  # Check {output} was formatted


def test_wait_resource_prompt(
    test_config: Config,
) -> None:  # Uses create_summary_prompt
    """Test wait_resource_prompt has correct format."""
    fixed_dt = datetime.datetime(2024, 3, 20, 10, 30, 45)
    fixed_dt_str = fixed_dt.strftime("%Y-%m-%d %H:%M:%S")

    with patch("vibectl.prompt.datetime") as mock_prompt_datetime:
        mock_prompt_datetime.now.return_value = fixed_dt
        system_fragments, user_fragments = wait_resource_prompt(config=test_config)

    combined_text = "\n".join(system_fragments + user_fragments)
    assert "Summarize this kubectl wait output" in combined_text
    assert "whether resources met their conditions" in combined_text
    assert (
        f"Current time is {fixed_dt_str}." in combined_text
    )  # From get_formatting_fragments
    assert "{output}" in combined_text


def test_port_forward_prompt(test_config: Config) -> None:  # Uses create_summary_prompt
    """Test port_forward_prompt has correct format."""
    fixed_dt = datetime.datetime(2024, 3, 20, 10, 30, 45)
    fixed_dt_str = fixed_dt.strftime("%Y-%m-%d %H:%M:%S")

    with patch("vibectl.prompt.datetime") as mock_prompt_datetime:
        mock_prompt_datetime.now.return_value = fixed_dt
        system_fragments, user_fragments = port_forward_prompt(config=test_config)

    combined_text = "\n".join(system_fragments + user_fragments)
    assert "Summarize this kubectl port-forward output" in combined_text
    assert "connection status" in combined_text
    assert "port mappings" in combined_text
    assert f"Current time is {fixed_dt_str}." in combined_text
    assert "{output}" in combined_text


def test_plan_port_forward_prompt() -> None:
    """Test the PLAN_PORT_FORWARD_PROMPT specifically."""
    system_fragments, user_fragments = PLAN_PORT_FORWARD_PROMPT
    combined_text = "\n".join(system_fragments + user_fragments)

    assert isinstance(combined_text, str)
    assert len(combined_text) > 100
    assert (
        "You are planning arguments for the 'kubectl port-forward' command"
        in combined_text
    )
    assert "which is used for port-forward connections" in combined_text
    # Placeholders are not part of its direct output
    assert "__MEMORY_CONTEXT_PLACEHOLDER__" not in combined_text
    assert "__REQUEST_PLACEHOLDER__" not in combined_text
    assert "port 8080 of pod nginx to my local 8080" in combined_text


def test_recovery_prompt_with_original_explanation(
    test_config: Config,
) -> None:  # Added config
    """Test recovery prompt generation with original explanation."""
    command = "get pods"
    error = "Error: the server doesn't have a resource type 'pods'"
    current_memory_dummy = "Previous context for recovery."
    fixed_dt = datetime.datetime(2024, 3, 20, 10, 30, 45)
    fixed_dt_str = fixed_dt.strftime("%Y-%m-%d %H:%M:%S")
    test_config.set("memory_max_chars", 200)  # Different from other recovery test

    with patch("vibectl.prompt.datetime") as mock_prompt_datetime:
        mock_prompt_datetime.now.return_value = fixed_dt

        # Test with original_explanation = None
        system_fragments_no_expl, user_fragments_no_expl = recovery_prompt(
            failed_command=command,
            error_output=error,
            current_memory=current_memory_dummy,
            original_explanation=None,
            config=test_config,
        )
    result_no_expl = "\n".join(system_fragments_no_expl + user_fragments_no_expl)

    assert "Failed Command:" in result_no_expl
    assert "suggest potential next steps" in result_no_expl  # Changed assertion
    assert f"Current time is {fixed_dt_str}." in result_no_expl
    assert "Be concise. Limit your response to 200 characters." in result_no_expl
    assert "Explanation:" not in result_no_expl

    # Check prompt when original explanation is available
    mock_error_explanation = "Deploying nginx"
    with patch(
        "vibectl.prompt.datetime"
    ) as mock_prompt_datetime_2:  # New patch context
        mock_prompt_datetime_2.now.return_value = (
            fixed_dt  # Use same fixed_dt for consistency
        )
        system_fragments_expl, user_fragments_expl = recovery_prompt(
            failed_command="kubectl create deploy nginx --image=nginx:latest",
            error_output="deploy fail",
            current_memory=current_memory_dummy,
            original_explanation=mock_error_explanation,
            config=test_config,
        )
    prompt_content_with_expl = "\n".join(system_fragments_expl + user_fragments_expl)

    assert (
        "A command failed during execution." not in prompt_content_with_expl
    )  # This was never in recovery_prompt
    assert "Failed Command:" in prompt_content_with_expl
    assert "Error Output:" in prompt_content_with_expl
    assert (
        "Explanation: Deploying nginx" in prompt_content_with_expl
    )  # Check exact string
    assert "suggest potential next steps" in prompt_content_with_expl
    assert f"Current time is {fixed_dt_str}." in prompt_content_with_expl
    assert (
        "Be concise. Limit your response to 200 characters." in prompt_content_with_expl
    )
