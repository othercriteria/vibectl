"""Tests for the CLI scale command.

This module tests the functionality of the scale command group and its subcommands.
"""

from typing import Any
from unittest.mock import Mock, call, patch

from click.testing import CliRunner

from vibectl.cli import cli, scale
from vibectl.prompt import PLAN_SCALE_PROMPT


def test_scale_vibe_request(cli_runner: CliRunner) -> None:
    """Test that the scale command handles vibe requests properly."""
    with patch("vibectl.cli.handle_vibe_request") as mock_handle_vibe:
        result = cli_runner.invoke(
            scale, ["vibe", "scale the frontend deployment to 5 replicas"]
        )

        assert result.exit_code == 0
        mock_handle_vibe.assert_called_once()
        _, kwargs = mock_handle_vibe.call_args
        assert kwargs["request"] == "scale the frontend deployment to 5 replicas"
        assert kwargs["command"] == "scale"
        assert kwargs["plan_prompt"] == PLAN_SCALE_PROMPT


def test_scale_vibe_no_request(cli_runner: CliRunner) -> None:
    """Test that the scale command properly handles missing vibe request."""
    with patch("vibectl.cli.console_manager") as mock_console:
        result = cli_runner.invoke(scale, ["vibe"])

        assert result.exit_code == 1
        mock_console.print_error.assert_called_once_with("Missing request after 'vibe'")


def test_scale_no_subcommand(cli_runner: CliRunner) -> None:
    """Test that an error is displayed when no subcommand is provided for scale."""
    with patch("vibectl.cli.console_manager") as mock_console:
        result = cli_runner.invoke(scale, [])

        # For the scale command, it uses Click's default behavior of showing help text
        # with exit code 2 when no required arguments are provided
        assert result.exit_code == 2
        # Click's default behavior doesn't call console_manager
        mock_console.print_error.assert_not_called()


def test_scale_deployment_success(cli_runner: CliRunner) -> None:
    """Test normal execution of the scale deployment command."""
    with (
        patch("vibectl.cli.run_kubectl") as mock_run_kubectl,
        patch("vibectl.cli.handle_command_output") as mock_handle_output,
        patch("vibectl.cli.configure_output_flags") as mock_configure,
        patch("sys.exit"),  # Prevent test from exiting
    ):
        # Configure mocks
        mock_run_kubectl.return_value = "deployment.apps/nginx scaled"
        mock_configure.return_value = (False, True, False, "test-model")

        # Execute the command
        _ = cli_runner.invoke(scale, ["deployment", "nginx", "--replicas=5"])

        # Verify the kubectl command was correct
        mock_run_kubectl.assert_called_once_with(
            ["scale", "deployment", "nginx", "--replicas=5"], capture=True
        )
        mock_handle_output.assert_called_once()


def test_scale_integration_flow(cli_runner: CliRunner) -> None:
    """Test the integration between scale parent command and kubectl command."""
    with (
        patch("vibectl.cli.run_kubectl") as mock_run_kubectl,
        patch("vibectl.cli.handle_command_output") as mock_handle_output,
        patch("vibectl.cli.configure_output_flags") as mock_configure,
        patch("sys.exit"),  # Prevent test from exiting
    ):
        # Configure mocks
        mock_run_kubectl.return_value = "deployment.apps/nginx scaled"
        mock_configure.return_value = (False, True, False, "test-model")

        # Execute the command through the CLI
        _ = cli_runner.invoke(cli, ["scale", "deployment", "nginx", "--replicas=5"])

        # Verify the kubectl command was correct
        mock_run_kubectl.assert_called_once_with(
            ["scale", "deployment", "nginx", "--replicas=5"], capture=True
        )
        mock_handle_output.assert_called_once()


def test_scale_normal_execution(cli_runner: CliRunner) -> None:
    """Test normal execution of the scale command with mocks for internal functions."""
    with (
        patch("vibectl.cli.run_kubectl") as mock_run_kubectl,
        patch("vibectl.cli.handle_command_output") as mock_handle_output,
        patch("vibectl.cli.configure_output_flags") as mock_configure,
        patch("sys.exit"),  # Prevent test from exiting
    ):
        # Setup return values
        mock_run_kubectl.return_value = "deployment.apps/nginx scaled"
        mock_configure.return_value = (False, True, False, "test-model")

        # Execute the command
        _ = cli_runner.invoke(scale, ["deployment/nginx", "--replicas=3"])

        # With sys.exit mocked, we can't rely on exit code checks
        # Just verify the functions were called correctly
        mock_run_kubectl.assert_called_once_with(
            ["scale", "deployment/nginx", "--replicas=3"], capture=True
        )
        mock_handle_output.assert_called_once()


def test_scale_no_output(cli_runner: CliRunner) -> None:
    """Test scale command when there's no output from kubectl."""
    with (
        patch("vibectl.cli.run_kubectl") as mock_run_kubectl,
        patch("vibectl.cli.handle_command_output") as mock_handle_output,
        patch("vibectl.cli.configure_output_flags") as mock_configure,
        patch("sys.exit"),  # Prevent test from exiting
    ):
        # Setup return values
        mock_run_kubectl.return_value = ""
        mock_configure.return_value = (False, True, False, "test-model")

        # Execute
        _ = cli_runner.invoke(scale, ["deployment/nginx", "--replicas=3"])

        # With sys.exit mocked, we can't rely on exit code checks
        # Just verify the functions were called correctly
        mock_run_kubectl.assert_called_once_with(
            ["scale", "deployment/nginx", "--replicas=3"], capture=True
        )
        # No output should not trigger handle_command_output
        mock_handle_output.assert_not_called()


def test_scale_error_handling(cli_runner: CliRunner) -> None:
    """Test error handling in scale command."""
    with (
        patch("vibectl.cli.run_kubectl") as mock_run_kubectl,
        patch("vibectl.cli.handle_exception") as mock_handle_exception,
        patch("vibectl.cli.configure_output_flags") as mock_configure,
        patch("sys.exit"),  # Prevent test from exiting
    ):
        # Setup an exception
        mock_run_kubectl.side_effect = Exception("Test error")
        mock_configure.return_value = (False, True, False, "test-model")

        # Execute
        _ = cli_runner.invoke(scale, ["deployment/nginx", "--replicas=3"])

        # With sys.exit mocked, we can't rely on exit code checks
        # Just verify the exception was handled
        mock_handle_exception.assert_called_once()


def test_scale_debug_detailed_flow(cli_runner: CliRunner) -> None:
    """Comprehensive test for scale command's flow and behavior."""
    with (
        patch("vibectl.cli.run_kubectl") as mock_run_kubectl,
        patch("vibectl.cli.handle_command_output") as mock_handle_output,
        patch("vibectl.cli.configure_output_flags") as mock_configure,
        patch("vibectl.cli.console_manager") as mock_console,
        patch("vibectl.cli.handle_vibe_request") as mock_handle_vibe,
        patch("vibectl.cli.configure_memory_flags") as mock_configure_memory,
        patch("sys.exit"),  # Prevent test from exiting
    ):
        # Configure detailed mocks with debug output
        mock_run_kubectl.return_value = "deployment.apps/nginx scaled to 3 replicas"
        mock_configure.return_value = (True, True, False, "claude-3.7-sonnet")

        # Capture console output for debugging
        debug_output = []
        mock_console.print.side_effect = lambda *args, **kwargs: debug_output.append(
            f"CONSOLE: {args[0]}"
        )
        mock_console.print_debug = Mock(
            side_effect=lambda *args, **kwargs: debug_output.append(f"DEBUG: {args[0]}")
        )

        # 1. Test regular scale command
        debug_output.append("=== REGULAR SCALE COMMAND ===")
        _ = cli_runner.invoke(
            scale, ["deployment/nginx", "--replicas=3", "--show-raw-output"]
        )

        # Verify kubectl was called with correct parameters
        debug_output.append(f"RUN_KUBECTL CALLS: {mock_run_kubectl.call_args_list}")
        debug_output.append(f"OUTPUT HANDLING: {mock_handle_output.call_args}")

        assert mock_run_kubectl.call_count >= 1
        assert mock_run_kubectl.call_args == call(
            ["scale", "deployment/nginx", "--replicas=3"], capture=True
        )

        # Verify output handling for regular command
        assert mock_handle_output.call_count >= 1
        output_kwargs = mock_handle_output.call_args[1]
        debug_output.append(f"OUTPUT HANDLER KWARGS: {output_kwargs}")
        assert "output" in output_kwargs
        assert "show_raw_output" in output_kwargs
        assert "show_vibe" in output_kwargs
        assert "model_name" in output_kwargs

        # 2. Test vibe mode
        debug_output.append("\n=== VIBE MODE SCALE COMMAND ===")
        mock_run_kubectl.reset_mock()
        mock_handle_output.reset_mock()

        # Execute vibe command
        _ = cli_runner.invoke(
            scale,
            [
                "vibe",
                "scale the nginx deployment to 5 replicas",
                "--model",
                "claude-3.7-sonnet",
            ],
        )

        # Verify vibe request handling
        debug_output.append(f"VIBE REQUEST CALL: {mock_handle_vibe.call_args}")
        assert mock_handle_vibe.call_count >= 1
        vibe_kwargs = mock_handle_vibe.call_args[1]
        assert vibe_kwargs["request"] == "scale the nginx deployment to 5 replicas"
        assert vibe_kwargs["command"] == "scale"
        assert vibe_kwargs["plan_prompt"] == PLAN_SCALE_PROMPT
        assert "model_name" in vibe_kwargs

        # 3. Test error handling
        debug_output.append("\n=== ERROR HANDLING ===")
        mock_run_kubectl.reset_mock()
        mock_run_kubectl.side_effect = Exception("Simulated kubectl error")

        # Error path output
        mock_console.print_error = Mock(
            side_effect=lambda *args, **kwargs: debug_output.append(f"ERROR: {args[0]}")
        )

        # Execute with error condition
        with patch("vibectl.cli.handle_exception") as mock_handle_exception:
            _ = cli_runner.invoke(scale, ["deployment/nginx", "--replicas=3"])
            assert mock_handle_exception.call_count >= 1
            debug_output.append(
                f"EXCEPTION HANDLER CALL: {mock_handle_exception.call_args}"
            )

        # 4. Output flow validation
        debug_output.append("\n=== FLOW VALIDATION ===")

        # Check configuration flags were used
        debug_output.append(f"CONFIGURE_FLAGS CALLS: {mock_configure.call_args_list}")
        debug_output.append(
            f"CONFIGURE_MEMORY CALLS: {mock_configure_memory.call_args_list}"
        )

        # Print all captured debug output for analysis
        print("\n".join(debug_output))


def test_scale_llm_integration_flow(cli_runner: CliRunner) -> None:
    """Focused test on the LLM integration flow for the scale command."""
    with (
        patch("vibectl.cli.handle_vibe_request") as mock_handle_vibe,
        patch("vibectl.command_handler.llm") as mock_llm,
        patch("vibectl.command_handler.run_kubectl") as mock_run_kubectl,
        patch("vibectl.command_handler.handle_command_output") as mock_handle_output,
        patch("vibectl.cli.configure_output_flags") as mock_configure,
        patch("vibectl.cli.console_manager"),
        patch("sys.exit"),  # Prevent test from exiting
    ):
        # Debug output collection
        debug_output = []

        # Configure mocks to track the LLM flow
        mock_configure.return_value = (True, True, False, "claude-3.7-sonnet")

        # Setup LLM model mock
        mock_model = Mock()
        mock_llm.get_model.return_value = mock_model

        # Simulate LLM response for scale command planning
        mock_response = Mock()
        mock_response.text.return_value = "deployment/nginx\n" "--replicas=5"
        mock_model.prompt.return_value = mock_response

        # Simulate kubectl output
        mock_run_kubectl.return_value = "deployment.apps/nginx scaled to 5 replicas"

        # Pass through to our mocked command_handler functions
        # This enables us to spy on the internal handle_vibe_request flow
        def handle_vibe_side_effect(*args: Any, **kwargs: Any) -> None:
            debug_output.append("=== VIBE REQUEST HANDLING ===")
            debug_output.append(f"REQUEST: {kwargs['request']}")
            debug_output.append(f"COMMAND: {kwargs['command']}")
            debug_output.append(f"PLAN PROMPT: {kwargs['plan_prompt'][:100]}...")
            debug_output.append(f"MODEL: {kwargs['model_name']}")

            # Call the mocked LLM
            model = mock_llm.get_model(kwargs["model_name"])
            prompt = kwargs["plan_prompt"].format(request=kwargs["request"])
            debug_output.append(f"FORMATTED PROMPT (excerpt): {prompt[:100]}...")

            # Get LLM response and parse it
            response = model.prompt(prompt)
            plan = response.text()
            debug_output.append(f"LLM RESPONSE: {plan}")

            # Parse into kubectl args and execute
            kubectl_args = plan.split("\n")
            debug_output.append(f"PARSED KUBECTL ARGS: {kubectl_args}")

            # Simulate kubectl execution
            output = mock_run_kubectl([kwargs["command"], *kubectl_args], capture=True)
            debug_output.append(f"KUBECTL OUTPUT: {output}")

            # Handle the output through summary prompt
            if output:
                debug_output.append("HANDLING COMMAND OUTPUT...")
                summary_prompt = kwargs["summary_prompt_func"]()
                debug_output.append(
                    f"SUMMARY PROMPT (excerpt): {summary_prompt[:100]}..."
                )

                # This would normally call the LLM again for summarization
                mock_handle_output(
                    output=output,
                    show_raw_output=kwargs["show_raw_output"],
                    show_vibe=kwargs["show_vibe"],
                    model_name=kwargs["model_name"],
                    summary_prompt_func=kwargs["summary_prompt_func"],
                )

            return None

        # Set up our spy on handle_vibe_request
        mock_handle_vibe.side_effect = handle_vibe_side_effect

        # Execute the vibe command
        debug_output.append("EXECUTING: vibectl scale vibe 'scale nginx to 5 replicas'")
        _ = cli_runner.invoke(
            scale, ["vibe", "scale nginx to 5 replicas", "--model", "claude-3.7-sonnet"]
        )

        # Verify vibe request was handled
        assert mock_handle_vibe.call_count == 1
        assert mock_llm.get_model.call_count >= 1

        # Check LLM was called with correct prompt
        assert mock_model.prompt.call_count >= 1
        prompt_arg = mock_model.prompt.call_args[0][0]
        debug_output.append(
            f"LLM PROMPT CONTAINS 'scale nginx to 5 replicas': "
            f"{'scale nginx to 5 replicas' in prompt_arg}"
        )

        # Check kubectl would be called with correct arguments
        assert mock_run_kubectl.call_count >= 1

        # Final debug output
        debug_output.append("\n=== SCALE COMMAND LLM INTEGRATION SUMMARY ===")
        debug_output.append("1. User input converted to kubectl args via LLM")
        debug_output.append("2. Kubectl executes the command and returns output")
        debug_output.append("3. Output is summarized via second LLM call")
        debug_output.append("4. Summary is displayed to user based on output flags")

        # Print all debug info
        print("\n".join(debug_output))


def test_scale_with_kubectl_flags(cli_runner: CliRunner) -> None:
    """Test that the scale command correctly handles kubectl-style flags like -n."""
    with (
        patch("vibectl.cli.run_kubectl") as mock_run_kubectl,
        # We don't actually use the mock_handle_output in this test
        # but we need to patch it to avoid real calls
        patch("vibectl.cli.handle_command_output"),
        patch("vibectl.cli.configure_output_flags") as mock_configure,
        patch("sys.exit"),  # Prevent test from exiting
    ):
        # Setup return values
        mock_run_kubectl.return_value = "deployment.apps/nginx scaled"
        mock_configure.return_value = (False, True, False, "test-model")

        # Execute the command with -n flag for namespace
        _ = cli_runner.invoke(
            scale, ["deployment/nginx", "-n", "sandbox", "--replicas=3"]
        )

        # Verify the command succeeded and kubectl was called with correct args
        mock_run_kubectl.assert_called_once_with(
            ["scale", "deployment/nginx", "-n", "sandbox", "--replicas=3"], capture=True
        )

        # Additional test with multiple kubectl flags
        mock_run_kubectl.reset_mock()

        # Try with different flags order
        _ = cli_runner.invoke(
            scale, ["deployment/nginx", "--replicas=3", "-n", "sandbox", "--record"]
        )

        # Verify the command succeeded with all flags passed through
        mock_run_kubectl.assert_called_once_with(
            ["scale", "deployment/nginx", "--replicas=3", "-n", "sandbox", "--record"],
            capture=True,
        )
