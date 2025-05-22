"""Tests for memory integration with model adapter.

This module tests the integration between the memory functions and the model adapter
for operations that require LLM calls.
"""

import os
from collections.abc import Generator
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from vibectl.config import Config
from vibectl.memory import get_memory, is_memory_enabled, set_memory, update_memory
from vibectl.model_adapter import ModelAdapter, reset_model_adapter, set_model_adapter


@pytest.fixture
def mock_model_adapter() -> Generator[Mock, None, None]:
    """Fixture for a mocked model adapter."""
    mock_adapter = Mock(spec=ModelAdapter)
    # Setup mock model
    mock_model = Mock()
    mock_adapter.get_model.return_value = mock_model
    # Setup default response for execute_and_log_metrics
    mock_adapter.execute_and_log_metrics.return_value = "Updated memory content"

    # Save original adapter
    with patch("vibectl.memory.get_model_adapter", return_value=mock_adapter):
        yield mock_adapter

    # Reset adapter after test
    reset_model_adapter()


@pytest.fixture
def test_config() -> Generator[Config, None, None]:
    """Create a test configuration with a temporary directory."""
    # Create a temporary config directory
    test_dir = Path("/tmp/vibectl-test-" + os.urandom(4).hex())
    test_dir.mkdir(parents=True, exist_ok=True)

    # Initialize config with test directory
    config = Config(base_dir=test_dir)

    # Ensure memory is enabled
    config.set("memory_enabled", True)

    # Return the config for use in tests
    yield config


async def test_update_memory_basic(
    mock_model_adapter: Mock, test_config: Config
) -> None:
    """Test basic memory update functionality with mocked model adapter."""
    # Test data
    command = "kubectl get pods"
    command_output = (
        "NAME    READY   STATUS    RESTARTS   AGE\n"
        "nginx-1   1/1     Running   0          10m"
    )
    vibe_output = "1 pod running: nginx-1"

    # Configure the mock adapter to return the expected memory content and None metrics
    expected_memory_text = "Updated memory content"
    mock_model_adapter.execute_and_log_metrics.return_value = (
        expected_memory_text,
        None,
    )

    # Call update_memory
    await update_memory(
        command_message=command,
        command_output=command_output,
        vibe_output=vibe_output,
        model_name="claude-3.7-sonnet",
        config=test_config,
    )

    # Verify model adapter was called with correct parameters
    mock_model_adapter.get_model.assert_called_once_with("claude-3.7-sonnet")
    mock_model_adapter.execute_and_log_metrics.assert_called_once()

    # Verify prompt contains command, output and vibe_output
    kwargs_passed = mock_model_adapter.execute_and_log_metrics.call_args[1]
    user_fragments_passed = kwargs_passed["user_fragments"]

    # The command, command_output, and vibe_output are now in the fragment
    # created by fragment_interaction
    # This is typically the third user fragment after current_time and memory_context
    interaction_fragment_content = ""
    for fragment in user_fragments_passed:
        if "Interaction:" in fragment:
            interaction_fragment_content = fragment
            break

    assert interaction_fragment_content, (
        "Interaction fragment not found in user_fragments"
    )
    assert command in interaction_fragment_content
    assert command_output in interaction_fragment_content
    assert vibe_output in interaction_fragment_content

    # Verify memory was updated
    assert get_memory(test_config) == expected_memory_text

    mock_model_adapter.execute_and_log_metrics.assert_called_once()


@patch("vibectl.memory.is_memory_enabled")
async def test_update_memory_disabled(
    mock_is_enabled: Mock, mock_model_adapter: Mock, test_config: Config
) -> None:
    """Test update_memory is skipped when memory is disabled."""
    # Setup mock to return disabled
    mock_is_enabled.return_value = False

    # Call update_memory
    await update_memory(
        command_message="kubectl get pods",
        command_output="No resources found",
        vibe_output="No pods found",
        config=test_config,
    )

    # Verify model adapter was not called
    mock_model_adapter.get_model.assert_not_called()
    mock_model_adapter.execute_and_log_metrics.assert_not_called()


async def test_update_memory_with_error(
    mock_model_adapter: Mock, test_config: Config
) -> None:
    """Test memory update with error output is handled correctly."""
    # Setup
    command = "kubectl get pods"
    command_output = "Error: the server doesn't have a resource type 'pod'"
    vibe_output = "Error: invalid resource type"

    # Configure mock to return error-focused memory
    mock_model_adapter.execute_and_log_metrics.return_value = (
        "Error occurred: invalid resource type 'pod'",
        None,
    )

    # Call update_memory
    await update_memory(
        command_message=command,
        command_output=command_output,
        vibe_output=vibe_output,
        config=test_config,
    )

    # Verify prompt emphasizes the error
    kwargs_passed_error = mock_model_adapter.execute_and_log_metrics.call_args[1]
    user_fragments_passed_error = kwargs_passed_error["user_fragments"]
    system_fragments_passed_error = kwargs_passed_error["system_fragments"]
    # Check user fragment for basic error content
    # The error content is in the interaction fragment
    interaction_fragment_content_error = ""
    for fragment in user_fragments_passed_error:
        if "Interaction:" in fragment:
            interaction_fragment_content_error = fragment
            break

    assert interaction_fragment_content_error, (
        "Interaction fragment not found in error user_fragments"
    )
    assert "Error:" in interaction_fragment_content_error
    assert (
        command_output in interaction_fragment_content_error
    )  # Check for the raw error output

    # Check system fragment for general memory assistant role
    # FRAGMENT_MEMORY_ASSISTANT is the first system fragment usually.
    # Its content starts with "You are an AI agent..."
    found_memory_assistant_role = False
    for fragment_str in system_fragments_passed_error:
        if "You are an AI agent maintaining memory state" in fragment_str:
            found_memory_assistant_role = True
            break
    assert found_memory_assistant_role, (
        "Key phrase from FRAGMENT_MEMORY_ASSISTANT not found in system_fragments"
    )

    # Verify memory captures the error
    assert "Error occurred" in get_memory(test_config)


async def test_update_memory_model_error(
    mock_model_adapter: Mock, test_config: Config
) -> None:
    """Test handling when model adapter raises an exception."""
    # Setup model adapter to raise exception
    mock_model_adapter.execute_and_log_metrics.side_effect = ValueError(
        "Model execution failed"
    )

    # Patch set_memory to verify it's not called
    with patch("vibectl.memory.set_memory") as mock_set_mem:
        # Call update_memory - should catch the exception internally
        await update_memory(
            command_message="kubectl get pods",
            command_output="output",
            vibe_output="vibe",
            config=test_config,
        )

        # Verify execute_and_log_metrics was called (and raised error)
        mock_model_adapter.execute_and_log_metrics.assert_called_once()
        # Verify set_memory was NOT called because of the error
        mock_set_mem.assert_not_called()


async def test_update_memory_integration(test_config: Config) -> None:
    """Test full integration of update_memory with a real model adapter.

    This test uses a mock adapter but verifies the full flow from update_memory
    through prompt creation, execution, and memory setting.
    """
    # Create a custom mock adapter that will be used instead of the real one
    mock_adapter = Mock(spec=ModelAdapter)
    mock_model = Mock()
    mock_adapter.get_model.return_value = mock_model
    # Set the expected final memory content
    expected_memory_text = "Cluster has 3 pods running in namespace default"
    mock_adapter.execute_and_log_metrics.return_value = (
        expected_memory_text,
        None,
    )

    # Set our mock as the global adapter
    set_model_adapter(mock_adapter)

    try:
        # Start with some initial memory
        set_memory("Initial cluster state: unknown", test_config)

        # Call update_memory
        await update_memory(
            command_message="kubectl get pods",
            command_output="3 pods running",
            vibe_output="3 pods are running",
            config=test_config,
        )

        # Verify execute_and_log_metrics was called
        mock_adapter.execute_and_log_metrics.assert_called_once()

        # Verify memory was updated correctly
        assert get_memory(test_config) == expected_memory_text

        # Verify memory is used in prompts (optional check)
        assert is_memory_enabled(test_config)
    finally:
        # Clean up
        reset_model_adapter()
