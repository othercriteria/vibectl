"""
Tests for coverage gaps in memory functionality.
"""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vibectl.cli import memory_group
from vibectl.memory import (
    clear_memory,
    disable_memory,
    enable_memory,
    get_memory,
    set_memory,
)
from vibectl.types import LLMMetrics, Success


@pytest.fixture
def setup_and_cleanup_memory() -> Generator[None, None, None]:
    """Set up by setting a known memory state and clean up after test."""
    # Save original memory
    original_memory = get_memory()

    # Set test memory
    set_memory("Test memory content")

    yield

    # Restore original memory
    if original_memory:
        set_memory(original_memory)
    else:
        clear_memory()


# Marker for consistency, even if underlying funcs are sync
@pytest.mark.asyncio
async def test_memory_freeze_unfreeze() -> None:
    """Test memory freeze and unfreeze functions."""
    # Test disabling (freezing) memory
    disable_memory()

    # Verify memory is disabled - pass no arguments to get_memory
    memory_disabled = get_memory()
    assert not memory_disabled or memory_disabled.startswith("[DISABLED]")

    # Enable memory
    enable_memory()

    # Verify memory is enabled
    memory = get_memory()
    assert memory is not None


# Marker for consistency, even if underlying funcs are sync
@pytest.mark.asyncio
async def test_memory_clear(
    setup_and_cleanup_memory: Generator[None, None, None],
) -> None:
    """Test memory clear functionality."""
    # Verify memory has content
    assert get_memory() is not None

    # Clear memory
    clear_memory()

    # Verify memory was cleared (None or empty string)
    memory = get_memory()
    assert not memory


@pytest.mark.asyncio
@patch("vibectl.cli.click.edit")  # Patch click.edit used within the command
async def test_memory_set_with_editor(
    mock_edit: MagicMock, setup_and_cleanup_memory: Generator[None, None, None]
) -> None:
    """Test memory set using the editor."""
    set_cmd = memory_group.commands["set"]  # Get the set command object

    # Mock the editor return value
    edited_content = "This is the edited memory content"
    mock_edit.return_value = edited_content

    # Run the memory_set command directly
    with patch("vibectl.cli.console_manager"):  # Mock console if needed by command
        await set_cmd.main(["--edit"], standalone_mode=False)  # Use await and call main

    # Check the memory was updated with edited content
    assert get_memory() == edited_content

    # Verify mock was called
    mock_edit.assert_called_once()


@pytest.mark.asyncio
# Patch the function called by the CLI command and sys.exit
@patch("vibectl.cli.run_memory_update_logic", new_callable=AsyncMock)
@patch("sys.exit")  # To prevent the test from exiting prematurely
async def test_memory_update(
    mock_sys_exit: MagicMock,  # Mock for sys.exit
    mock_run_memory_update_logic: AsyncMock,  # Mock for the core logic function
    setup_and_cleanup_memory: Generator[None, None, None],
) -> None:
    """Test memory update functionality by invoking the CLI command directly."""
    update_cmd = memory_group.commands["update"]  # Get the update command object

    # Configure the mock for run_memory_update_logic
    expected_updated_memory_content = "Updated memory via mock logic"
    # Simulate the metrics object that run_memory_update_logic would include
    mock_llm_metrics = MagicMock(
        spec=LLMMetrics
    )  # Use MagicMock if LLMMetrics isn't easily importable or to simplify
    mock_llm_metrics.latency_ms = 100.0
    mock_llm_metrics.token_input = 10
    mock_llm_metrics.token_output = 20
    # Other LLMMetrics attributes if they are accessed by handle_result
    # or Success string formatting
    mock_llm_metrics.total_processing_duration_ms = None
    mock_llm_metrics.fragments_used = None
    mock_llm_metrics.call_count = 1

    # Construct the data string as the real function would, for the Success object
    success_data_str = (
        f"Memory updated successfully.\\nUpdated Memory Content:\\n"
        f"{expected_updated_memory_content}"
    )
    total_tokens = mock_llm_metrics.token_input + mock_llm_metrics.token_output
    if total_tokens > 0:
        success_data_str += (
            f"\\nLLM Metrics: Latency={mock_llm_metrics.latency_ms:.2f}ms, "
            f"Tokens={total_tokens}"
        )
    else:
        success_data_str += (
            f"\\nLLM Metrics: Latency={mock_llm_metrics.latency_ms:.2f}ms"
        )

    mock_run_memory_update_logic.return_value = Success(
        data=success_data_str, metrics=mock_llm_metrics
    )

    # We also need to mock set_memory if run_memory_update_logic is expected to call it
    # and we want to verify its effect using get_memory() after the command.
    # For this test structure, let's assume run_memory_update_logic's mock will
    # simulate this.
    # To do that, we can make the mock_run_memory_update_logic also call set_memory.

    async def side_effect_for_run_logic(*args: Any, **kwargs: Any) -> Success:
        # Simulate the core logic's call to set_memory
        set_memory(expected_updated_memory_content)
        return Success(data=success_data_str, metrics=mock_llm_metrics)

    mock_run_memory_update_logic.side_effect = side_effect_for_run_logic

    # Run the memory_update command directly
    with patch(
        "vibectl.cli.console_manager"
    ):  # Mock console if used by CLI layer before handle_result
        await update_cmd.main(
            ["Add", "new", "information", "--show-streaming"], standalone_mode=False
        )

    # Verify memory was updated by checking get_memory()
    assert get_memory() == expected_updated_memory_content

    # Verify mocks
    mock_run_memory_update_logic.assert_called_once()
    called_args_kwargs = mock_run_memory_update_logic.call_args.kwargs
    assert called_args_kwargs.get("update_text_str") == "Add new information"
    assert called_args_kwargs.get("model_name") is None

    mock_sys_exit.assert_called_once_with(
        0
    )  # handle_result should exit with 0 for Success
