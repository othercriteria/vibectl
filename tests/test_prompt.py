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
from collections.abc import Callable
from unittest.mock import Mock, patch

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
    cluster_info_prompt,
    create_planning_prompt,
    create_resource_prompt,
    delete_resource_prompt,
    describe_resource_prompt,
    events_prompt,
    get_formatting_instructions,
    get_resource_prompt,
    logs_prompt,
    memory_fuzzy_update_prompt,
    memory_update_prompt,
    port_forward_prompt,
    recovery_prompt,
    refresh_datetime,
    rollout_general_prompt,
    rollout_history_prompt,
    rollout_status_prompt,
    scale_resource_prompt,
    version_prompt,
    vibe_autonomous_prompt,
    wait_resource_prompt,
)
from vibectl.schema import LLMCommandResponse

_TEST_SCHEMA_JSON = json.dumps(LLMCommandResponse.model_json_schema())


def test_refresh_datetime() -> None:
    """Test refresh_datetime returns correct format."""
    # Mock datetime to ensure consistent test
    mock_now = datetime.datetime(2024, 3, 20, 10, 30, 45)
    with patch("datetime.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_now
        result = refresh_datetime()
        assert result == "2024-03-20 10:30:45"


def test_get_formatting_instructions_no_custom(test_config: Config) -> None:
    """Test get_formatting_instructions without custom instructions."""
    mock_now = datetime.datetime(2024, 3, 20, 10, 30, 45)
    test_config.set("custom_instructions", None)  # Clear any custom instructions
    test_config.set("memory_enabled", False)  # Ensure memory is disabled

    with patch("datetime.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_now
        result = get_formatting_instructions(test_config)

        # Check basic structure
        assert len(result) > 100  # Should be reasonably sized
        assert "rich.Console() markup syntax" in result  # Core requirement
        assert "Current date and time is" in result  # Required timestamp
        assert "Custom instructions:" not in result  # No custom section
        assert "Memory context:" not in result  # No memory section


def test_get_formatting_instructions_with_custom(test_config: Config) -> None:
    """Test get_formatting_instructions with custom instructions."""
    mock_now = datetime.datetime(2024, 3, 20, 10, 30, 45)
    test_config.set("custom_instructions", "Test custom instruction")
    test_config.set("memory_enabled", False)  # Ensure memory is disabled

    with patch("datetime.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_now
        result = get_formatting_instructions(test_config)

        # Check custom instructions section exists
        assert "Custom instructions:" in result
        assert "Test custom instruction" in result
        assert "Memory context:" not in result  # No memory section


def test_get_formatting_instructions_with_memory(test_config: Config) -> None:
    """Test get_formatting_instructions with memory enabled."""
    mock_now = datetime.datetime(2024, 3, 20, 10, 30, 45)
    test_config.set("custom_instructions", None)  # Clear any custom instructions
    test_config.set("memory_enabled", True)  # Enable memory

    with (
        patch("datetime.datetime") as mock_datetime,
        patch("vibectl.memory.get_memory") as mock_get_memory,
        patch("vibectl.memory.is_memory_enabled") as mock_is_memory_enabled,
    ):
        mock_datetime.now.return_value = mock_now
        mock_is_memory_enabled.return_value = True
        mock_get_memory.return_value = "Test memory content"

        result = get_formatting_instructions(test_config)

        # Check memory section exists
        assert "Memory context:" in result
        assert "Test memory content" in result


# Semantic requirements that all prompts must meet
@pytest.mark.parametrize(
    "prompt_func",
    [
        get_resource_prompt,
        describe_resource_prompt,
        logs_prompt,
        create_resource_prompt,
        cluster_info_prompt,
        version_prompt,
        events_prompt,
        delete_resource_prompt,
        scale_resource_prompt,
        wait_resource_prompt,
        rollout_status_prompt,
        rollout_history_prompt,
        rollout_general_prompt,
        vibe_autonomous_prompt,
    ],
)
def test_prompt_semantic_requirements(prompt_func: Callable[[], str]) -> None:
    """Test semantic requirements that all prompts must meet.

    Requirements:
    1. Must include rich.Console() markup syntax instructions
    2. Must include current datetime for timestamp context
    3. Must have reasonable length (not too short/long)

    TODO: Add more semantic requirements as needed, but keep them minimal
    and focused on critical elements that must be present.
    """
    with patch("datetime.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime.datetime(2024, 3, 20, 10, 30, 45)
        result = prompt_func()

        # Core requirements
        assert "rich.Console() markup syntax" in result
        assert "Current date and time is" in result
        assert 100 < len(result) < 3000  # Reasonable size limits


@pytest.mark.parametrize(
    "prompt_func,required_placeholder",
    [
        (get_resource_prompt, "{output}"),
        (describe_resource_prompt, "{output}"),
        (logs_prompt, "{output}"),
        (create_resource_prompt, "{output}"),
        (cluster_info_prompt, "{output}"),
        (version_prompt, "{output}"),
        (events_prompt, "{output}"),
        (delete_resource_prompt, "{output}"),
        (scale_resource_prompt, "{output}"),
        (wait_resource_prompt, "{output}"),
        (rollout_status_prompt, "{output}"),
        (rollout_history_prompt, "{output}"),
        (rollout_general_prompt, "{output}"),
        (vibe_autonomous_prompt, "{output}"),
    ],
)
def test_prompt_structure(
    prompt_func: Callable[[], str], required_placeholder: str
) -> None:
    """Test basic structure of prompts."""
    result = prompt_func()

    # Check basic structure
    assert len(result) > 100  # Should be reasonably sized
    assert required_placeholder in result  # Required placeholder


def test_create_planning_prompt_structure_and_content() -> None:
    """Verify the structure and content generated by create_planning_prompt."""
    command = "test-cmd"
    description = "testing the command"
    examples = [
        (
            "request 1",
            {
                "action_type": "COMMAND",
                "commands": ["arg1", "val1"],
                "explanation": "Explanation for request 1.",
            },
        ),
        (
            "request 2",
            {
                "action_type": "COMMAND",
                "commands": ["arg2", "--flag"],
                "explanation": "Explanation for request 2.",
            },
        ),
    ]

    prompt = create_planning_prompt(
        command=command,
        description=description,
        examples=examples,
        schema_definition=_TEST_SCHEMA_JSON,
    )

    # Basic checks
    assert isinstance(prompt, str)
    assert len(prompt) > 100

    # Verify the basic structure and key phrases
    assert f"You are planning arguments for the 'kubectl {command}' command." in prompt
    assert "determine the\nappropriate arguments *following*" in prompt
    assert "respond with a JSON\nobject matching the provided schema." in prompt
    assert "Focus on extracting resource names, types, namespaces" in prompt
    assert f"The action '{command}' is implied." in prompt
    assert "Your response MUST be a valid JSON object" in prompt
    assert "Key fields:" in prompt
    assert "Example inputs (natural language target descriptions)" in prompt
    assert "__MEMORY_CONTEXT_PLACEHOLDER__" in prompt

    # Verify placeholders
    assert "__MEMORY_CONTEXT_PLACEHOLDER__" in prompt
    assert "__REQUEST_PLACEHOLDER__" in prompt

    # Verify example formatting (updated to check for JSON structure)
    # Check if the prompt contains the start of the JSON example block
    assert '- Target: "request 1" -> Expected JSON output:' in prompt
    # Check if it contains parts of the expected JSON for the first example
    assert '"action_type": "COMMAND"' in prompt
    assert '"commands": [' in prompt
    assert '"arg1"' in prompt
    assert '"val1"' in prompt

    # Verify key instructions related to schema fields are present
    assert "`action_type`" in prompt
    assert "`commands`: List of string arguments" in prompt
    assert "`explanation`: Brief explanation of the planned arguments." in prompt
    assert "`error`: Required if action_type is ERROR" in prompt
    assert "`wait_duration_seconds`: Required if action_type is WAIT" in prompt

    # Verify inclusion of dynamic parts
    assert _TEST_SCHEMA_JSON in prompt  # Check schema is included


def test_create_planning_prompt_raises_without_schema() -> None:
    """Verify create_planning_prompt raises ValueError if schema is missing."""
    with pytest.raises(ValueError, match="schema_definition must be provided"):
        create_planning_prompt(
            command="test",
            description="test",
            examples=[],
            schema_definition=None,  # Explicitly pass None
        )


@pytest.mark.parametrize(
    "plan_prompt_constant",
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
def test_plan_prompt_constants_are_generated(plan_prompt_constant: str) -> None:
    """Test that all plan prompt constants are generated correctly."""
    assert isinstance(plan_prompt_constant, str)
    assert len(plan_prompt_constant) > 100  # Basic check for content

    # Check for updated key phrases common to all planning prompts
    assert "You are planning arguments for the 'kubectl" in plan_prompt_constant
    assert (
        "respond with a JSON\nobject matching the provided schema."
        in plan_prompt_constant
    )
    assert "Key fields:" in plan_prompt_constant
    assert (
        "Example inputs (natural language target descriptions)" in plan_prompt_constant
    )
    assert "__MEMORY_CONTEXT_PLACEHOLDER__" in plan_prompt_constant
    assert "__REQUEST_PLACEHOLDER__" in plan_prompt_constant
    assert "action_type" in plan_prompt_constant  # Ensure schema elements are present
    assert "commands" in plan_prompt_constant


def test_plan_create_prompt_structure() -> None:
    """Basic structural check for the unique PLAN_CREATE_PROMPT."""
    assert isinstance(PLAN_CREATE_PROMPT, str)
    assert "__REQUEST_PLACEHOLDER__" in PLAN_CREATE_PROMPT
    assert "YAML manifest" in PLAN_CREATE_PROMPT  # Check for create-specific content


def test_memory_update_prompt() -> None:
    """Test memory update prompt with config-provided max chars limit."""
    # Setup
    mock_config = Mock(spec=Config)
    mock_config.get.return_value = 500

    # Need to patch inside the function with context manager
    with patch("vibectl.memory.get_memory", return_value="Previous cluster state"):
        # Execute
        prompt = memory_update_prompt(
            command="kubectl get pods",
            command_output="pod1 Running",
            vibe_output="1 pod running",
            config=mock_config,
        )

    # Assert
    mock_config.get.assert_called_once_with("memory_max_chars", 500)
    assert "Previous cluster state" in prompt
    assert "memory is limited to 500 characters" in prompt
    assert "kubectl get pods" in prompt
    assert "pod1 Running" in prompt
    assert "1 pod running" in prompt


def test_memory_fuzzy_update_prompt() -> None:
    """Test memory fuzzy update prompt with user-provided update text."""
    # Setup
    mock_config = Mock(spec=Config)
    mock_config.get.return_value = 500
    current_memory = "Previous cluster state with 3 pods running"
    update_text = "Deployment xyz scaled to 5 replicas"

    # Execute
    prompt = memory_fuzzy_update_prompt(
        current_memory=current_memory,
        update_text=update_text,
        config=mock_config,
    )

    # Assert
    mock_config.get.assert_called_once_with("memory_max_chars", 500)
    assert "Previous cluster state with 3 pods running" in prompt
    assert "Deployment xyz scaled to 5 replicas" in prompt
    assert "memory is limited to 500 characters" in prompt
    assert "integrate this information" in prompt.lower()


def test_recovery_prompt() -> None:
    """Test recovery prompt generation."""
    # Test with a simple command and error
    command = "get pods"
    error = "Error: the server doesn't have a resource type 'pods'"

    # Test with default max_chars
    result = recovery_prompt(command, error)

    # Check basic structure
    assert len(result) > 100  # Should be reasonably sized
    assert command in result
    assert f"Error:\n```\n{error}\n```" in result
    assert "Explain the error in simple terms" in result
    assert "alternative approaches" in result
    assert "Keep your response under 1500 characters." in result

    # Test with custom token limit
    max_chars = 500
    result_custom = recovery_prompt(command, error, max_chars)
    assert f"Keep your response under {max_chars} characters." in result_custom


def test_vibe_autonomous_prompt() -> None:
    """Test vibe autonomous prompt generation."""
    result = vibe_autonomous_prompt()

    # Check basic structure
    assert len(result) > 100  # Should be reasonably sized
    assert "Analyze this kubectl command output" in result
    assert "Focus on the state of the resources" in result
    assert "rich.Console() markup syntax" in result
    assert "Next steps:" in result
    assert "{output}" in result


def test_wait_resource_prompt() -> None:
    """Test wait_resource_prompt has correct format."""
    prompt = wait_resource_prompt()
    assert "Summarize this kubectl wait output" in prompt
    assert "whether resources met their conditions" in prompt
    assert "{output}" in prompt


def test_port_forward_prompt() -> None:
    """Test port_forward_prompt has correct format."""
    prompt = port_forward_prompt()
    assert "Summarize this kubectl port-forward output" in prompt
    assert "connection status" in prompt
    assert "port mappings" in prompt
    assert "{output}" in prompt


def test_plan_port_forward_prompt() -> None:
    """Test specific content of the PLAN_PORT_FORWARD_PROMPT."""
    prompt = PLAN_PORT_FORWARD_PROMPT
    # Check for updated key phrases and specific content
    assert (
        "You are planning arguments for the 'kubectl port-forward' command." in prompt
    )
    assert "respond with a JSON\nobject matching the provided schema." in prompt
    assert (
        '- Target: "port 8080 of pod nginx to my local 8080"' in prompt
    )  # Check example
    assert "8080:8080" in prompt  # Check example command part
