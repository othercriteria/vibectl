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
from collections.abc import Callable
from unittest.mock import Mock, patch

import pytest

from vibectl.config import Config
from vibectl.prompt import (
    PLAN_CLUSTER_INFO_PROMPT,
    PLAN_CREATE_PROMPT,
    PLAN_DESCRIBE_PROMPT,
    PLAN_EVENTS_PROMPT,
    PLAN_GET_PROMPT,
    PLAN_LOGS_PROMPT,
    PLAN_VERSION_PROMPT,
    cluster_info_prompt,
    create_resource_prompt,
    describe_resource_prompt,
    events_prompt,
    get_formatting_instructions,
    get_resource_prompt,
    logs_prompt,
    memory_fuzzy_update_prompt,
    memory_update_prompt,
    refresh_datetime,
    version_prompt,
)


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

    with patch("datetime.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_now
        result = get_formatting_instructions(test_config)

        # Check basic structure
        assert len(result) > 100  # Should be reasonably sized
        assert "rich.Console() markup syntax" in result  # Core requirement
        assert "Current date and time is" in result  # Required timestamp
        assert "Custom instructions:" not in result  # No custom section


def test_get_formatting_instructions_with_custom(test_config: Config) -> None:
    """Test get_formatting_instructions with custom instructions."""
    mock_now = datetime.datetime(2024, 3, 20, 10, 30, 45)
    test_config.set("custom_instructions", "Test custom instruction")

    with patch("datetime.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_now
        result = get_formatting_instructions(test_config)

        # Check custom instructions section exists
        assert "Custom instructions:" in result
        assert "Test custom instruction" in result


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


@pytest.mark.parametrize(
    "prompt,required_elements",
    [
        (
            PLAN_GET_PROMPT,
            {
                "placeholder": "{request}",
                "required_phrases": [
                    "Given this natural language request",
                    "Return ONLY the list of arguments",
                    "Do not include 'kubectl' or 'get'",
                ],
                "examples": [
                    "show me pods in kube-system",
                    "get pods with app=nginx label",
                ],
            },
        ),
        (
            PLAN_DESCRIBE_PROMPT,
            {
                "placeholder": "{request}",
                "required_phrases": [
                    "Given this natural language request",
                    "Return ONLY the list of arguments",
                    "Do not include 'kubectl' or 'describe'",
                ],
                "examples": [
                    "tell me about the nginx pod",
                    "describe the deployment in kube-system namespace",
                ],
            },
        ),
        (
            PLAN_LOGS_PROMPT,
            {
                "placeholder": "{request}",
                "required_phrases": [
                    "Given this natural language request",
                    "Return ONLY the list of arguments",
                    "Do not include 'kubectl' or 'logs'",
                ],
                "examples": [
                    "show me logs from the nginx pod",
                    "get logs from the api container in my-app pod",
                ],
            },
        ),
        (
            PLAN_CREATE_PROMPT,
            {
                "placeholder": "{request}",
                "required_phrases": [
                    "Given this natural language request",
                    "Return the list of arguments",
                    "Do not include 'kubectl' or 'create'",
                ],
                "examples": [
                    "create an nginx hello world pod",
                    "create a deployment with 3 nginx replicas in prod namespace",
                ],
            },
        ),
        (
            PLAN_CLUSTER_INFO_PROMPT,
            {
                "placeholder": "{request}",
                "required_phrases": [
                    "Given this natural language request",
                    "Return ONLY the list of arguments",
                    "Do not include 'kubectl' or 'cluster-info'",
                ],
                "examples": [
                    "show cluster info",
                    "show basic cluster info",
                ],
            },
        ),
        (
            PLAN_VERSION_PROMPT,
            {
                "placeholder": "{request}",
                "required_phrases": [
                    "Given this natural language request",
                    "Return ONLY the list of arguments",
                    "Do not include 'kubectl' or 'version'",
                ],
                "examples": [
                    "show version in json format",
                    "get client version only",
                ],
            },
        ),
        (
            PLAN_EVENTS_PROMPT,
            {
                "placeholder": "{request}",
                "required_phrases": [
                    "Given this natural language request",
                    "Return ONLY the list of arguments",
                    "Do not include 'kubectl' or 'get events'",
                ],
                "examples": [
                    "show events in default namespace",
                    "get events for pod nginx",
                ],
            },
        ),
    ],
)
def test_plan_prompts(prompt: str, required_elements: dict) -> None:
    """Test plan prompt templates.

    Tests both structural requirements and critical semantic elements that
    must be present in plan prompts.
    """
    # Check basic structure
    assert len(prompt) > 100  # Should be reasonably sized
    assert required_elements["placeholder"] in prompt

    # Check required semantic elements
    for phrase in required_elements["required_phrases"]:
        assert phrase in prompt

    # Check examples
    for example in required_elements["examples"]:
        assert example in prompt


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
