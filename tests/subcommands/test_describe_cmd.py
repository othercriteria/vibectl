from unittest.mock import ANY, AsyncMock, Mock, patch

import pytest

from vibectl.prompts.describe import describe_resource_prompt
from vibectl.subcommands.describe_cmd import run_describe_command
from vibectl.types import Error, Success


@pytest.mark.asyncio
@patch("vibectl.subcommands.describe_cmd.handle_standard_command")
@patch("vibectl.subcommands.describe_cmd.configure_output_flags")
@patch("vibectl.subcommands.describe_cmd.configure_memory_flags")
@patch("vibectl.subcommands.describe_cmd.logger")
async def test_describe_basic(
    mock_logger: Mock,
    mock_configure_memory: Mock,
    mock_configure_output: Mock,
    mock_handle_standard: Mock,
) -> None:
    """Test basic describe command functionality."""
    # Mock the underlying handler to return success
    mock_handle_standard.return_value = Success(data="test output")

    # Call the function directly
    result = await run_describe_command(
        resource="pod",
        args=("my-pod",),
        show_raw_output=None,
        show_vibe=None,
        freeze_memory=False,
        unfreeze_memory=False,
    )

    # Assert the result and mock calls
    assert isinstance(result, Success)
    mock_handle_standard.assert_called_once_with(
        command="describe",
        resource="pod",
        args=("my-pod",),
        output_flags=ANY,  # Output flags are configured internally
        summary_prompt_func=ANY,
    )
    mock_configure_output.assert_called_once()
    mock_configure_memory.assert_called_once()


@pytest.mark.asyncio
@patch("vibectl.subcommands.describe_cmd.handle_standard_command")
@patch("vibectl.subcommands.describe_cmd.configure_output_flags")
@patch("vibectl.subcommands.describe_cmd.configure_memory_flags")
@patch("vibectl.subcommands.describe_cmd.logger")
@pytest.mark.parametrize(
    "args, should_succeed",
    [
        (["describe", "pod", "my-pod", "--", "-n", "default"], True),  # valid: with --
    ],
)
async def test_describe_args_variants(
    mock_logger: Mock,
    mock_configure_memory: Mock,
    mock_configure_output: Mock,
    mock_handle_standard: Mock,
    args: list[str],
    should_succeed: bool,
) -> None:
    # Extract relevant parts from args for direct function call
    resource = args[1]
    func_args = tuple(args[2:])

    mock_handle_standard.return_value = Success(data="test output")

    # Call run_describe_command directly
    result = await run_describe_command(
        resource=resource,
        args=func_args,
        show_raw_output=None,
        show_vibe=None,
        freeze_memory=False,
        unfreeze_memory=False,
    )

    if should_succeed:
        assert isinstance(result, Success)
        mock_handle_standard.assert_called_once_with(
            command="describe",
            resource=resource,
            args=func_args,
            output_flags=mock_configure_output.return_value,
            summary_prompt_func=ANY,
        )
    else:
        # Direct call might return Error or raise ClickException depending
        # on args validation
        # For simplicity, assume Error for now, adjust if ClickException is expected
        assert isinstance(result, Error) or result is None  # If validation fails early


@pytest.mark.asyncio
@patch("vibectl.subcommands.describe_cmd.handle_standard_command")
@patch("vibectl.subcommands.describe_cmd.configure_output_flags")
@patch("vibectl.subcommands.describe_cmd.configure_memory_flags")
@patch("vibectl.subcommands.describe_cmd.logger")
async def test_describe_with_flags(
    mock_logger: Mock,
    mock_configure_memory: Mock,
    mock_configure_output: Mock,
    mock_handle_standard: Mock,
) -> None:
    """Test describe command with output flags."""
    mock_handle_standard.return_value = Success(data="test output")

    result = await run_describe_command(
        resource="pod",
        args=("my-pod",),  # Flags are handled by configure_output_flags
        show_raw_output=True,
        show_vibe=True,
        freeze_memory=False,
        unfreeze_memory=False,
    )

    assert isinstance(result, Success)
    mock_handle_standard.assert_called_once()
    # show_streaming is no longer a parameter passed to configure_output_flags
    # since it's handled via ContextVar overrides at the CLI level
    mock_configure_output.assert_called_once_with(
        show_raw_output=True,
        show_vibe=True,
    )
    mock_configure_memory.assert_called_once()


@pytest.mark.asyncio
@patch("vibectl.subcommands.describe_cmd.handle_standard_command")
@patch("vibectl.subcommands.describe_cmd.configure_output_flags")
@patch("vibectl.subcommands.describe_cmd.configure_memory_flags")
@patch("vibectl.subcommands.describe_cmd.logger")
async def test_describe_error_handling(
    mock_logger: Mock,
    mock_configure_memory: Mock,
    mock_configure_output: Mock,
    mock_handle_standard: Mock,
) -> None:
    """Test describe command when kubectl returns an error."""
    # Mock the handler to return an Error
    mock_error = Error(error="kubectl error", exception=Exception("kubectl error"))
    mock_handle_standard.return_value = mock_error

    result = await run_describe_command(
        resource="pod",
        args=("my-pod",),
        show_raw_output=None,
        show_vibe=None,
        freeze_memory=False,
        unfreeze_memory=False,
    )

    # Assert Error is returned and mock was called
    assert isinstance(result, Error)  # Check type first
    assert result.error == mock_error.error  # Then check content
    mock_handle_standard.assert_called_once()


@patch("vibectl.subcommands.describe_cmd.handle_vibe_request")
@pytest.mark.asyncio
@patch("vibectl.subcommands.describe_cmd.configure_output_flags")
@patch("vibectl.subcommands.describe_cmd.configure_memory_flags")
@patch("vibectl.subcommands.describe_cmd.logger")
async def test_describe_vibe_request(
    mock_logger: Mock,
    mock_configure_memory: Mock,
    mock_configure_output: Mock,
    mock_handle_vibe: AsyncMock,
) -> None:
    """Test describe command with 'vibe' request."""
    # Mock handle_vibe_request to return Success
    mock_handle_vibe.return_value = Success()

    # Call run_describe_command directly
    result = await run_describe_command(
        resource="vibe",
        args=("show", "me", "the", "nginx", "pod"),
        show_raw_output=None,
        show_vibe=None,
        freeze_memory=False,
        unfreeze_memory=False,
    )

    # Assert Success is returned
    assert isinstance(result, Success)

    mock_handle_vibe.assert_called_once_with(
        request="show me the nginx pod",
        command="describe",
        plan_prompt_func=ANY,
        summary_prompt_func=describe_resource_prompt,
        output_flags=ANY,  # Check specific flags if needed
        semiauto=False,
        config=None,  # Expect config to be None as it's not passed by caller
    )


@pytest.mark.asyncio
@patch("vibectl.subcommands.describe_cmd.configure_output_flags")
@patch("vibectl.subcommands.describe_cmd.configure_memory_flags")
@patch("vibectl.subcommands.describe_cmd.logger")
async def test_describe_vibe_no_request(
    mock_logger: Mock,
    mock_configure_memory: Mock,
    mock_configure_output: Mock,
) -> None:
    """Test describe command with 'vibe' but no request (should error)."""
    # Call run_describe_command directly with vibe and no args
    result = await run_describe_command(
        resource="vibe",
        args=(),
        show_raw_output=None,
        show_vibe=None,
        freeze_memory=False,
        unfreeze_memory=False,
    )

    # Assert an Error is returned with the correct message
    assert isinstance(result, Error)
    assert "Missing request after 'vibe'" in result.error


@pytest.mark.asyncio
async def test_run_describe_command_normal() -> None:
    """Test normal describe command execution."""
    with (
        patch(
            "vibectl.subcommands.describe_cmd.configure_output_flags"
        ) as mock_configure_output,
        patch(
            "vibectl.subcommands.describe_cmd.configure_memory_flags"
        ) as _mock_configure_memory,
        patch(
            "vibectl.subcommands.describe_cmd.handle_standard_command"
        ) as mock_handle_standard,
    ):
        mock_output_flags = Mock()
        mock_configure_output.return_value = mock_output_flags
        mock_result = Success(data="test result")
        mock_handle_standard.return_value = mock_result

        result = await run_describe_command(
            resource="pod",
            args=("test-pod",),
            show_raw_output=None,
            show_vibe=None,
            freeze_memory=False,
            unfreeze_memory=False,
        )

        assert result == mock_result
        mock_handle_standard.assert_called_once_with(
            command="describe",
            resource="pod",
            args=("test-pod",),
            output_flags=mock_output_flags,
            summary_prompt_func=describe_resource_prompt,
        )


@pytest.mark.asyncio
async def test_run_describe_command_vibe() -> None:
    """Test describe command with vibe request."""
    with (
        patch(
            "vibectl.subcommands.describe_cmd.configure_output_flags"
        ) as mock_configure_output,
        patch(
            "vibectl.subcommands.describe_cmd.configure_memory_flags"
        ) as _mock_configure_memory,
        patch(
            "vibectl.subcommands.describe_cmd.handle_vibe_request"
        ) as mock_handle_vibe,
    ):
        mock_output_flags = Mock()
        mock_configure_output.return_value = mock_output_flags
        mock_result = Success(data="vibe result")
        mock_handle_vibe.return_value = mock_result

        result = await run_describe_command(
            resource="vibe",
            args=("show", "pods"),
            show_raw_output=None,
            show_vibe=None,
            freeze_memory=False,
            unfreeze_memory=False,
        )

        assert result == mock_result
        mock_handle_vibe.assert_called_once_with(
            request="show pods",
            command="describe",
            plan_prompt_func=ANY,
            output_flags=mock_output_flags,
            summary_prompt_func=describe_resource_prompt,
            semiauto=False,
            config=None,
        )


@pytest.mark.asyncio
async def test_run_describe_command_vibe_no_args() -> None:
    """Test describe command with vibe but no args."""
    with (
        patch(
            "vibectl.subcommands.describe_cmd.configure_output_flags"
        ) as mock_configure_output,
        patch(
            "vibectl.subcommands.describe_cmd.configure_memory_flags"
        ) as _mock_configure_memory,
    ):
        mock_output_flags = Mock()
        mock_configure_output.return_value = mock_output_flags

        result = await run_describe_command(
            resource="vibe",
            args=(),
            show_raw_output=None,
            show_vibe=None,
            freeze_memory=False,
            unfreeze_memory=False,
        )

        assert isinstance(result, Error)
        assert "Missing request after 'vibe' command" in result.error


@pytest.mark.asyncio
async def test_run_describe_command_vibe_handle_vibe_request_exception() -> None:
    """Test error handling when handle_vibe_request raises an exception."""
    with (
        patch(
            "vibectl.subcommands.describe_cmd.configure_output_flags"
        ) as mock_configure_output,
        patch(
            "vibectl.subcommands.describe_cmd.configure_memory_flags"
        ) as _mock_configure_memory,
        patch(
            "vibectl.subcommands.describe_cmd.handle_vibe_request"
        ) as mock_handle_vibe,
    ):
        mock_output_flags = Mock()
        mock_configure_output.return_value = mock_output_flags
        mock_handle_vibe.side_effect = Exception("Test vibe error")

        # The exception should propagate since we removed the try/catch
        with pytest.raises(Exception, match="Test vibe error"):
            await run_describe_command(
                resource="vibe",
                args=("test", "request"),
                show_raw_output=None,
                show_vibe=None,
                freeze_memory=False,
                unfreeze_memory=False,
            )


@pytest.mark.asyncio
async def test_run_describe_command_standard_command_exception() -> None:
    """Test error handling when handle_standard_command raises an exception."""
    with (
        patch(
            "vibectl.subcommands.describe_cmd.configure_output_flags"
        ) as mock_configure_output,
        patch(
            "vibectl.subcommands.describe_cmd.configure_memory_flags"
        ) as _mock_configure_memory,
        patch(
            "vibectl.subcommands.describe_cmd.handle_standard_command"
        ) as mock_handle_standard,
    ):
        mock_output_flags = Mock()
        mock_configure_output.return_value = mock_output_flags
        mock_handle_standard.side_effect = Exception("Test standard error")

        # The exception should propagate since we removed the try/catch
        with pytest.raises(Exception, match="Test standard error"):
            await run_describe_command(
                resource="pod",
                args=("test-pod",),
                show_raw_output=None,
                show_vibe=None,
                freeze_memory=False,
                unfreeze_memory=False,
            )


@pytest.mark.asyncio
async def test_run_describe_command_configure_output_flags_exception() -> None:
    """Test error handling when configure_output_flags raises an exception."""
    with patch(
        "vibectl.subcommands.describe_cmd.configure_output_flags"
    ) as mock_configure_output:
        mock_configure_output.side_effect = ValueError("Test config error")

        # The exception should propagate since we removed the try/catch
        with pytest.raises(ValueError, match="Test config error"):
            await run_describe_command(
                resource="pod",
                args=("test",),
                show_raw_output=None,
                show_vibe=None,
                freeze_memory=False,
                unfreeze_memory=False,
            )


@pytest.mark.asyncio
async def test_run_describe_command_configure_memory_flags_exception() -> None:
    """Test error handling when configure_memory_flags raises an exception."""
    with (
        patch(
            "vibectl.subcommands.describe_cmd.configure_output_flags"
        ) as mock_configure_output,
        patch(
            "vibectl.subcommands.describe_cmd.configure_memory_flags"
        ) as _mock_configure_memory,
    ):
        mock_output_flags = Mock()
        mock_configure_output.return_value = mock_output_flags
        _mock_configure_memory.side_effect = ValueError("Test memory config error")

        # The exception should propagate since we removed the try/catch
        with pytest.raises(ValueError, match="Test memory config error"):
            await run_describe_command(
                resource="pod",
                args=("test",),
                show_raw_output=None,
                show_vibe=None,
                freeze_memory=False,
                unfreeze_memory=False,
            )
