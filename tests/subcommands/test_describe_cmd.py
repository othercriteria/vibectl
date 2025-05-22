from unittest.mock import ANY, AsyncMock, Mock, patch

import pytest

from vibectl.command_handler import OutputFlags
from vibectl.prompt import describe_resource_prompt
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
        show_kubectl=None,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=True,
        show_streaming=True,
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
        show_kubectl=None,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=True,
        show_streaming=True,
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
        show_kubectl=True,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=True,
        show_streaming=True,
    )

    assert isinstance(result, Success)
    mock_handle_standard.assert_called_once()
    mock_configure_output.assert_called_once_with(
        show_raw_output=True,
        show_vibe=True,
        model=None,
        show_kubectl=True,
        show_metrics=True,
        show_streaming=True,
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
        show_kubectl=None,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=True,
        show_streaming=True,
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
        show_kubectl=None,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=True,
        show_streaming=True,
    )

    # Assert Success is returned
    assert isinstance(result, Success)

    mock_handle_vibe.assert_called_once_with(
        request="show me the nginx pod",
        command="describe",
        plan_prompt_func=ANY,
        summary_prompt_func=describe_resource_prompt,
        output_flags=ANY,  # Check specific flags if needed
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
        show_kubectl=None,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=True,
        show_streaming=True,
    )

    # Assert an Error is returned with the correct message
    assert isinstance(result, Error)
    assert "Missing request after 'vibe'" in result.error


# --- Unit tests for run_describe_command for 100% coverage ---


@pytest.mark.asyncio
async def test_run_describe_command_normal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Covers the normal path (resource != 'vibe')."""
    # Mock dependencies
    mock_output_flags = Mock()
    mock_result = Mock()

    def fake_configure_output_flags(*a: object, **kw: object) -> Mock:
        return mock_output_flags

    def fake_configure_memory_flags(*a: object, **kw: object) -> None:
        pass

    async def fake_handle_standard_command(
        resource: str, args: tuple, output_flags: OutputFlags, **kwargs: object
    ) -> Mock:
        return mock_result

    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.configure_output_flags",
        fake_configure_output_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.configure_memory_flags",
        fake_configure_memory_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd._handle_standard_describe",
        fake_handle_standard_command,
    )

    # Call the function
    result = await run_describe_command(
        resource="pod",
        args=("test-pod",),
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=True,
        show_streaming=True,
    )
    assert result == mock_result


@pytest.mark.asyncio
async def test_run_describe_command_vibe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Covers the vibe path (resource == 'vibe')."""
    mock_output_flags = Mock()
    mock_result = Mock()

    def fake_configure_output_flags(*a: object, **kw: object) -> Mock:
        return mock_output_flags

    def fake_configure_memory_flags(*a: object, **kw: object) -> None:
        pass

    async def fake_handle_vibe_request(
        args: tuple, output_flags: OutputFlags, **kwargs: object
    ) -> Mock:
        return mock_result

    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.configure_output_flags",
        fake_configure_output_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.configure_memory_flags",
        fake_configure_memory_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd._handle_vibe_describe",
        fake_handle_vibe_request,
    )

    result = await run_describe_command(
        resource="vibe",
        args=("describe", "pod", "test-pod"),
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=True,
        show_streaming=True,
    )
    assert result == mock_result


@pytest.mark.asyncio
async def test_run_describe_command_vibe_no_args(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Covers the vibe path with no arguments after 'vibe'."""
    mock_output_flags = Mock()

    def fake_configure_output_flags(*a: object, **kw: object) -> Mock:
        return mock_output_flags

    def fake_configure_memory_flags(*a: object, **kw: object) -> None:
        pass

    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.configure_output_flags",
        fake_configure_output_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.configure_memory_flags",
        fake_configure_memory_flags,
    )

    result = await run_describe_command(
        resource="vibe",
        args=(),
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=True,
        show_streaming=True,
    )
    assert isinstance(result, Error)
    assert "Missing request after 'vibe' command" in result.error


@pytest.mark.asyncio
async def test_run_describe_command_vibe_handle_vibe_request_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tests error handling when handle_vibe_request raises an exception."""
    mock_output_flags = Mock()

    def fake_configure_output_flags(*a: object, **kw: object) -> Mock:
        return mock_output_flags

    def fake_configure_memory_flags(*a: object, **kw: object) -> None:
        pass

    async def fake_handle_vibe_request(
        args: tuple, output_flags: OutputFlags, **kwargs: object
    ) -> None:
        raise Exception("Test vibe error")

    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.configure_output_flags",
        fake_configure_output_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.configure_memory_flags",
        fake_configure_memory_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd._handle_vibe_describe",
        fake_handle_vibe_request,
    )

    result = await run_describe_command(
        resource="vibe",
        args=("test",),
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=True,
        show_streaming=True,
    )
    assert isinstance(result, Error)
    assert "Unhandled error in describe execution: Test vibe error" in result.error


@pytest.mark.asyncio
async def test_run_describe_command_standard_command_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tests error handling when handle_standard_command raises an exception."""
    mock_output_flags = Mock()

    def fake_configure_output_flags(*a: object, **kw: object) -> Mock:
        return mock_output_flags

    def fake_configure_memory_flags(*a: object, **kw: object) -> None:
        pass

    async def fake_handle_standard_command(
        resource: str, args: tuple, output_flags: OutputFlags, **kwargs: object
    ) -> None:
        raise Exception("Test standard error")

    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.configure_output_flags",
        fake_configure_output_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.configure_memory_flags",
        fake_configure_memory_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd._handle_standard_describe",
        fake_handle_standard_command,
    )

    result = await run_describe_command(
        resource="pod",
        args=("test",),
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=True,
        show_streaming=True,
    )
    assert isinstance(result, Error)
    assert "Unhandled error in describe execution: Test standard error" in result.error


@pytest.mark.asyncio
async def test_run_describe_command_configure_output_flags_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test error handling when configure_output_flags raises an exception."""

    def fake_configure_output_flags(*a: object, **kw: object) -> None:
        raise ValueError("Test config error")

    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.configure_output_flags",
        fake_configure_output_flags,
    )

    result = await run_describe_command(
        resource="pod",
        args=("test",),
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=True,
        show_streaming=True,
    )
    assert isinstance(result, Error)
    assert "Error configuring options: Test config error" in result.error


@pytest.mark.asyncio
async def test_run_describe_command_configure_memory_flags_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test error handling when configure_memory_flags raises an exception."""
    mock_output_flags = Mock()

    def fake_configure_output_flags(*a: object, **kw: object) -> Mock:
        return mock_output_flags

    def fake_configure_memory_flags(*a: object, **kw: object) -> None:
        raise ValueError("Test memory config error")

    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.configure_output_flags",
        fake_configure_output_flags,
    )
    monkeypatch.setattr(
        "vibectl.subcommands.describe_cmd.configure_memory_flags",
        fake_configure_memory_flags,
    )

    result = await run_describe_command(
        resource="pod",
        args=("test",),
        show_raw_output=None,
        show_vibe=None,
        show_kubectl=None,
        model=None,
        freeze_memory=False,
        unfreeze_memory=False,
        show_metrics=True,
        show_streaming=True,
    )
    assert isinstance(result, Error)
    assert "Error configuring options: Test memory config error" in result.error
