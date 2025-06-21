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
from unittest.mock import Mock, patch

import pytest

from vibectl.config import Config
from vibectl.prompts.cluster_info import cluster_info_plan_prompt, cluster_info_prompt
from vibectl.prompts.create import PLAN_CREATE_PROMPT, create_resource_prompt
from vibectl.prompts.delete import PLAN_DELETE_PROMPT, delete_resource_prompt
from vibectl.prompts.describe import PLAN_DESCRIBE_PROMPT, describe_resource_prompt
from vibectl.prompts.events import events_plan_prompt, events_prompt
from vibectl.prompts.get import get_plan_prompt, get_resource_prompt
from vibectl.prompts.logs import logs_plan_prompt, logs_prompt
from vibectl.prompts.memory import memory_fuzzy_update_prompt, memory_update_prompt
from vibectl.prompts.port_forward import PLAN_PORT_FORWARD_PROMPT, port_forward_prompt
from vibectl.prompts.recovery import recovery_prompt
from vibectl.prompts.rollout import (
    PLAN_ROLLOUT_PROMPT,
    rollout_general_prompt,
    rollout_history_prompt,
    rollout_status_prompt,
)
from vibectl.prompts.scale import (
    PLAN_SCALE_PROMPT,
    scale_resource_prompt,
)
from vibectl.prompts.shared import create_planning_prompt
from vibectl.prompts.version import version_plan_prompt, version_prompt
from vibectl.prompts.wait import wait_plan_prompt, wait_resource_prompt
from vibectl.schema import ActionType, LLMPlannerResponse

# Import new types
from vibectl.types import (
    Examples,
    PromptFragments,
)

_TEST_SCHEMA_JSON = json.dumps(LLMPlannerResponse.model_json_schema())


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

    These functions use create_summary_prompt; they must include timestamp and
    formatting guidance fragments injected by that helper.
    """
    # Mapping of function names to the actual imported functions
    prompt_functions = {
        "get_resource_prompt": get_resource_prompt,
        "describe_resource_prompt": describe_resource_prompt,
        "logs_prompt": logs_prompt,
        "create_resource_prompt": create_resource_prompt,
        "cluster_info_prompt": cluster_info_prompt,
        "version_prompt": version_prompt,
        "events_prompt": events_prompt,
        "delete_resource_prompt": delete_resource_prompt,
        "scale_resource_prompt": scale_resource_prompt,
        "wait_resource_prompt": wait_resource_prompt,
        "rollout_status_prompt": rollout_status_prompt,
        "rollout_history_prompt": rollout_history_prompt,
        "rollout_general_prompt": rollout_general_prompt,
        "port_forward_prompt": port_forward_prompt,
    }

    prompt_func = prompt_functions[prompt_func_name]

    fixed_dt = datetime.datetime(2024, 3, 20, 10, 30, 45)
    fixed_dt_str = fixed_dt.strftime("%Y-%m-%d %H:%M:%S")

    with patch("vibectl.prompts.shared.datetime") as mock_shared_datetime:
        mock_shared_datetime.now.return_value = fixed_dt

        # All listed prompt functions take optional config and return PromptFragments.
        system_fragments, user_fragments = prompt_func(config=test_config)  # type: ignore[operator]

        combined_text = "\n".join(system_fragments + user_fragments)

        # Summary prompts include standard formatting guidance.
        assert f"Current time is {fixed_dt_str}." in combined_text
        assert "rich.Console() markup syntax" in combined_text
        assert 100 < len(combined_text) < 5000  # updated upper bound
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
    # Mapping of function names to the actual imported functions
    prompt_functions = {
        "get_resource_prompt": get_resource_prompt,
        "describe_resource_prompt": describe_resource_prompt,
        "logs_prompt": logs_prompt,
        "create_resource_prompt": create_resource_prompt,
        "cluster_info_prompt": cluster_info_prompt,
        "version_prompt": version_prompt,
        "events_prompt": events_prompt,
        "delete_resource_prompt": delete_resource_prompt,
        "scale_resource_prompt": scale_resource_prompt,
        "wait_resource_prompt": wait_resource_prompt,
        "rollout_status_prompt": rollout_status_prompt,
        "rollout_history_prompt": rollout_history_prompt,
        "rollout_general_prompt": rollout_general_prompt,
        "port_forward_prompt": port_forward_prompt,
    }

    prompt_func = prompt_functions[prompt_func_name]

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
        "Your response MUST be a valid JSON object conforming to this schema:"
        in combined_prompt
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
        get_plan_prompt(),
        PLAN_DESCRIBE_PROMPT,
        logs_plan_prompt(),
        version_plan_prompt(),
        cluster_info_plan_prompt(),
        events_plan_prompt(),
        PLAN_DELETE_PROMPT,
        PLAN_SCALE_PROMPT,
        wait_plan_prompt(),
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
    assert (
        "Your response MUST be a valid JSON object conforming to this schema:"
        in combined_text
    )


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
    test_config.set("memory.max_chars", 300)
    fixed_dt = datetime.datetime(2024, 3, 20, 10, 30, 45)
    fixed_dt_str = fixed_dt.strftime("%Y-%m-%d %H:%M:%S")
    dummy_memory_content = "dummy_current_memory"
    expected_memory_fragment_str = f"Previous Memory:\n{dummy_memory_content}"

    with patch("vibectl.prompts.shared.datetime") as mock_shared_datetime:
        mock_shared_datetime.now.return_value = fixed_dt
        system_fragments, user_fragments = memory_update_prompt(
            command_message="dummy_command",
            command_output="dummy_command_output",
            vibe_output="dummy_vibe_output",
            current_memory=dummy_memory_content,
            config=test_config,
        )

    # Ensure the fragment exists within the assembled prompt fragments
    combined_text = "\n".join(system_fragments + user_fragments)
    assert expected_memory_fragment_str in combined_text, (
        "Expected memory fragment not found in generated prompt fragments. "
    )

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
    test_config.set("memory.max_chars", 400)
    fixed_dt = datetime.datetime(2024, 3, 20, 10, 30, 45)
    fixed_dt_str = fixed_dt.strftime("%Y-%m-%d %H:%M:%S")
    fuzzy_memory_content = "fuzzy_current_memory"
    expected_fuzzy_memory_fragment_str = f"Previous Memory:\n{fuzzy_memory_content}"

    with patch("vibectl.prompts.shared.datetime") as mock_shared_datetime:
        mock_shared_datetime.now.return_value = fixed_dt
        system_fragments, user_fragments = memory_fuzzy_update_prompt(
            current_memory=fuzzy_memory_content,
            update_text="fuzzy_update_text",
            config=test_config,
        )

    # Check the combined text for the expected content
    combined_text = "\n".join(system_fragments + user_fragments)

    # Ensure the fragment exists as expected in the combined text
    assert expected_fuzzy_memory_fragment_str in combined_text, (
        "Expected memory fragment not found in combined text. "
        f"Combined text: {combined_text}"
    )

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
    fixed_dt = datetime.datetime(2024, 3, 20, 10, 30, 45)
    fixed_dt_str = fixed_dt.strftime("%Y-%m-%d %H:%M:%S")
    test_config.set("memory.max_chars", 250)  # Added config.set for memory_max_chars

    # Mock the plugin system to return no custom mapping, then import
    with (
        patch("vibectl.plugins.PluginStore") as mock_store,
        patch("vibectl.plugins.PromptResolver") as mock_resolver,
        patch("vibectl.prompts.shared.datetime") as mock_shared_datetime,
    ):
        # Configure mocks to return no custom mapping
        mock_store_instance = Mock()
        mock_store.return_value = mock_store_instance
        mock_resolver_instance = Mock()
        mock_resolver.return_value = mock_resolver_instance
        mock_resolver_instance.get_prompt_mapping.return_value = None

        mock_shared_datetime.now.return_value = fixed_dt

        # Import after mocking
        from vibectl.prompts.recovery import recovery_prompt

        system_fragments, user_fragments = recovery_prompt(
            failed_command=command,
            error_output=error,
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
    fixed_dt = datetime.datetime(2024, 3, 20, 10, 30, 45)
    fixed_dt_str = fixed_dt.strftime("%Y-%m-%d %H:%M:%S")

    # Mock the plugin system to return no custom mapping, then import
    with (
        patch("vibectl.plugins.PluginStore") as mock_store,
        patch("vibectl.plugins.PromptResolver") as mock_resolver,
        patch("vibectl.prompts.shared.datetime") as mock_shared_datetime,
    ):
        # Configure mocks to return no custom mapping
        mock_store_instance = Mock()
        mock_store.return_value = mock_store_instance
        mock_resolver_instance = Mock()
        mock_resolver.return_value = mock_resolver_instance
        mock_resolver_instance.get_prompt_mapping.return_value = None

        mock_shared_datetime.now.return_value = fixed_dt

        # Import after mocking
        from vibectl.prompts.vibe import vibe_autonomous_prompt

        system_fragments, user_fragments = vibe_autonomous_prompt(config=test_config)

    combined_text = "\n".join(system_fragments + user_fragments)

    assert "Analyze this kubectl command output" in combined_text
    assert f"Current time is {fixed_dt_str}." in combined_text
    assert "Memory context:" not in combined_text
    assert "{output}" in combined_text


def test_vibe_autonomous_prompt_includes_context(test_config: Config) -> None:
    """Ensure vibe_autonomous_prompt includes standard context fragments
    provided by build_context_fragments (custom instructions + timestamp) and
    correctly preserves the {output} placeholder."""

    # Inject a custom instruction so we can verify it propagates
    test_config.set("system.custom_instructions", "Test custom instruction")

    fixed_dt = datetime.datetime(2024, 3, 20, 10, 30, 45)
    fixed_dt_str = fixed_dt.strftime("%Y-%m-%d %H:%M:%S")

    # Mock plugin resolver (no custom prompts) and datetime for deterministic output
    with (
        patch("vibectl.plugins.PluginStore") as mock_store,
        patch("vibectl.plugins.PromptResolver") as mock_resolver,
        patch("vibectl.prompts.shared.datetime") as mock_shared_datetime,
    ):
        mock_store.return_value = Mock()
        mock_resolver_instance = Mock()
        mock_resolver_instance.get_prompt_mapping.return_value = None
        mock_resolver.return_value = mock_resolver_instance

        mock_shared_datetime.now.return_value = fixed_dt

        from vibectl.prompts.vibe import vibe_autonomous_prompt

        system_fragments, user_fragments_template = vibe_autonomous_prompt(
            config=test_config
        )

    combined_text = "\n".join(system_fragments + user_fragments_template)

    # Custom instruction propagated
    assert "Custom instructions:" in combined_text
    assert "Test custom instruction" in combined_text

    # Timestamp
    assert f"Current time is {fixed_dt_str}." in combined_text

    # Placeholder for caller to fill
    assert "{output}" in combined_text


def test_wait_resource_prompt(
    test_config: Config,
) -> None:  # Uses create_summary_prompt
    """Test wait_resource_prompt has correct format."""
    fixed_dt = datetime.datetime(2024, 3, 20, 10, 30, 45)
    fixed_dt_str = fixed_dt.strftime("%Y-%m-%d %H:%M:%S")

    with patch("vibectl.prompts.shared.datetime") as mock_shared_datetime:
        mock_shared_datetime.now.return_value = fixed_dt
        system_fragments, user_fragments = wait_resource_prompt(config=test_config)

    combined_text = "\n".join(system_fragments + user_fragments)
    assert "Summarize this kubectl wait output" in combined_text
    assert "whether resources met their conditions" in combined_text
    assert f"Current time is {fixed_dt_str}." in combined_text
    assert "{output}" in combined_text


def test_port_forward_prompt(test_config: Config) -> None:  # Uses create_summary_prompt
    """Test port_forward_prompt has correct format."""
    fixed_dt = datetime.datetime(2024, 3, 20, 10, 30, 45)
    fixed_dt_str = fixed_dt.strftime("%Y-%m-%d %H:%M:%S")

    with patch("vibectl.prompts.shared.datetime") as mock_shared_datetime:
        mock_shared_datetime.now.return_value = fixed_dt
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
    fixed_dt = datetime.datetime(2024, 3, 20, 10, 30, 45)
    fixed_dt_str = fixed_dt.strftime("%Y-%m-%d %H:%M:%S")
    test_config.set("memory.max_chars", 200)  # Different from other recovery test

    # Import and access the unwrapped function

    unwrapped_func = recovery_prompt.__wrapped__

    with patch("vibectl.prompts.shared.datetime") as mock_shared_datetime:
        mock_shared_datetime.now.return_value = fixed_dt

        # Test with original_explanation = None
        system_fragments_no_expl, user_fragments_no_expl = unwrapped_func(
            None,  # custom_mapping = None (no plugin)
            failed_command=command,
            error_output=error,
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
        "vibectl.prompts.shared.datetime"
    ) as mock_shared_datetime_2:  # New patch context
        mock_shared_datetime_2.now.return_value = (
            fixed_dt  # Use same fixed_dt for consistency
        )
        system_fragments_expl, user_fragments_expl = unwrapped_func(
            None,  # custom_mapping = None (no plugin)
            failed_command="kubectl create deploy nginx --image=nginx:latest",
            error_output="deploy fail",
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
