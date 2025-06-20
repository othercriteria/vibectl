"""Tests for top-level CLI flags that rely on ContextVar overrides.

These tests ensure that flags parsed by the root ``vibectl`` CLI group -
for example ``--show-raw-output`` and ``--no-show-kubectl`` - are correctly
propagated via the Config/ContextVar mechanism and reflected in the
``OutputFlags`` instance produced by ``configure_output_flags`` inside the
``logs`` sub-command implementation.
"""

from typing import Any
from unittest.mock import Mock, patch

import pytest


@patch("vibectl.subcommands.logs_cmd.configure_output_flags")
@patch("vibectl.subcommands.logs_cmd.run_kubectl")
@patch("vibectl.subcommands.logs_cmd.handle_command_output")
@pytest.mark.asyncio
async def test_global_flag_contextvar_transduction(
    mock_handle_output: Mock,
    mock_run_kubectl: Mock,
    mock_configure_flags: Mock,
) -> None:
    """Verify that root-level flags affect OutputFlags inside a sub-command.

    The root CLI group consumes ``--show-raw-output`` and ``--no-show-kubectl``
    and stores their values in ContextVars.  The ``logs`` sub-command should
    therefore *not* receive these flags directly, yet ``configure_output_flags``
    (called inside ``run_logs_command``) must see their effects when it
    consults ``Config``.
    """

    # We spy on the real implementation of configure_output_flags to capture
    # the computed OutputFlags, while still allowing normal processing.
    import vibectl.command_handler as ch

    captured_flags = {}

    def _side_effect(*args: Any, **kwargs: Any) -> ch.OutputFlags:  # type: ignore[override]
        flags = ch.configure_output_flags(*args, **kwargs)
        captured_flags["flags"] = flags
        return flags

    mock_configure_flags.side_effect = _side_effect

    # Stub out downstream calls so no real kubectl invocations happen.
    from vibectl.types import Success

    mock_run_kubectl.return_value = Success(data="stub output")

    # Invoke the full CLI (root group) so that top-level option parsing occurs.
    from vibectl.cli import cli

    with pytest.raises(SystemExit) as exc_info:
        await cli.main(
            [
                "--show-raw-output",  # should set display.show_raw_output = True
                "--no-show-kubectl",  # should set display.show_kubectl = False
                "logs",
                "pod",
                "my-pod",
            ]
        )

    # Command should exit cleanly.
    assert exc_info.value.code == 0

    # Ensure run_kubectl received the expected clean argument list (flags have
    # been stripped before the sub-command builds its kubectl invocation).
    mock_run_kubectl.assert_called_once_with(["logs", "pod", "my-pod"])

    # We captured exactly one OutputFlags instance via the side-effect.
    assert "flags" in captured_flags, "configure_output_flags was not called"
    flags = captured_flags["flags"]

    # The ContextVar overrides set by the root-level flags should be reflected
    # in the resulting OutputFlags.
    assert flags.show_raw_output is True
    assert flags.show_kubectl is False
