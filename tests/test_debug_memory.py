"""Debug tests for memory update functionality.

This module contains debugging tests for the memory update function to
diagnose issues with string handling and mock behavior.
"""

from unittest.mock import Mock, patch

from vibectl.memory import update_memory


def test_debug_memory_update_execution() -> None:
    """Debug test to inspect exactly what happens in update_memory."""
    # Setup detailed tracing of all calls
    all_calls = []

    # Mock config
    mock_config = Mock()
    mock_config.get.return_value = True  # for is_memory_enabled check

    # Create recording function to trace all string values
    def record_call(name: str, *args: str, **kwargs: str) -> object:
        """Record all details of a function call."""
        call_info = {
            "name": name,
            "args": args,
            "kwargs": kwargs,
        }
        all_calls.append(call_info)

        # Return appropriate values based on function name
        if name == "Config":
            return mock_config
        elif name == "get_model_adapter":
            return mock_adapter
        elif name == "adapter.get_model":
            return mock_model
        elif name == "adapter.execute":
            # This is the key return value we need to debug
            result = "Updated memory content with special characters: \u2022 \u2713"
            print(f"\nAdapter execute returning: '{result}' (len={len(result)})")
            return result
        elif name == "memory_update_prompt":
            return "Test prompt template"
        return None

    # Create our mocks
    mock_adapter = Mock()
    mock_model = Mock()

    # Setup mocks with our recording function
    mock_config_patcher = patch(
        "vibectl.memory.Config",
        side_effect=lambda *args, **kwargs: record_call("Config", *args, **kwargs),
    )
    mock_adapter_patcher = patch(
        "vibectl.memory.get_model_adapter",
        side_effect=lambda *args, **kwargs: record_call(
            "get_model_adapter", *args, **kwargs
        ),
    )
    mock_prompt_patcher = patch(
        "vibectl.memory.memory_update_prompt",
        side_effect=lambda *args, **kwargs: record_call(
            "memory_update_prompt", *args, **kwargs
        ),
    )

    # Override adapter methods with our recording function
    mock_adapter.get_model = lambda *args, **kwargs: record_call(
        "adapter.get_model", *args, **kwargs
    )
    mock_adapter.execute = lambda *args, **kwargs: record_call(
        "adapter.execute", *args, **kwargs
    )

    # Execute with all mocks applied
    with mock_config_patcher, mock_adapter_patcher, mock_prompt_patcher:
        # Call update_memory
        update_memory(
            command="kubectl get pods",
            command_output="pod1 Running\npod2 Error",
            vibe_output="Pods are in mixed state",
            model_name="test-model",
        )

    # Print the full detailed trace of what happened
    print("\nDetailed update_memory execution trace:")
    for i, call_info in enumerate(all_calls):
        name = call_info["name"]
        args = call_info["args"]
        kwargs = call_info["kwargs"]
        print(f"{i+1}. {name}({args}, {kwargs})")

    # Print the actual set calls made on mock_config
    print("\nActual calls to mock_config.set:")
    for i, c in enumerate(mock_config.set.call_args_list):
        print(f"{i+1}. set{c}")
        # Print hex encoding of the string to check for encoding issues
        if len(c[0]) >= 2 and isinstance(c[0][1], str):
            value = c[0][1]
            hex_val = value.encode("utf-8").hex()
            print(f"   Value as hex: {hex_val}")
            print(f"   Value length: {len(value)}")
            print(f"   First char: {value[0]}, Last char: {value[-1]}")


def test_debug_mock_adapter_execution() -> None:
    """Debug test for mock adapter execution string handling."""
    # Create mock adapter
    mock_adapter = Mock()
    mock_model = Mock()

    # Setup the mocks
    test_string = "Updated memory content"
    mock_adapter.get_model.return_value = mock_model
    mock_adapter.execute.return_value = test_string

    # Create mock config
    mock_config = Mock()
    mock_config.get.return_value = True

    # Apply all mocks
    with (
        patch("vibectl.memory.get_model_adapter", return_value=mock_adapter),
        patch("vibectl.memory.Config", return_value=mock_config),
        patch("vibectl.memory.memory_update_prompt", return_value="Test prompt"),
    ):
        # Call update_memory
        update_memory(
            command="test",
            command_output="output",
            vibe_output="vibe",
        )

    # Print details about the mock calls
    print("\nMock execution details:")
    print(f"Mock adapter.execute.return_value: '{mock_adapter.execute.return_value}'")
    print(f"Type: {type(mock_adapter.execute.return_value)}")
    print(f"Length: {len(mock_adapter.execute.return_value)}")

    # Print all calls to config.set
    print("\nAll calls to config.set:")
    for i, c in enumerate(mock_config.set.call_args_list):
        print(f"{i+1}. set{c}")
        # If the set was called with a string value for memory, inspect it
        if len(c[0]) >= 2 and c[0][0] == "memory" and isinstance(c[0][1], str):
            value = c[0][1]
            print(f"   Value: '{value}'")
            print(f"   Type: {type(value)}")
            print(f"   Length: {len(value)}")
            print(
                f"   Is adapter return value: {value is mock_adapter.execute.return_value}"
            )
            if len(value) >= 1:
                print(f"   First char: '{value[0]}'")


def test_debug_direct_mock_behavior() -> None:
    """Debug test for directly testing mock behavior."""
    # Create a simple mock
    mock_obj = Mock()

    # Set the return value of the mock's method
    test_string = "Test return value"
    mock_obj.get_value.return_value = test_string

    # Call the mock method
    result = mock_obj.get_value()

    # Verify the result and mock behavior
    print("\nDirect mock test:")
    print(f"Original string: '{test_string}'")
    print(f"Result string: '{result}'")
    print(f"Is same object: {result is test_string}")
    print(f"Values equal: {result == test_string}")
    print(f"Original type: {type(test_string)}")
    print(f"Result type: {type(result)}")

    # Test with a mock method
    def mock_func(arg: str) -> str:
        """Return the input string."""
        return arg

    # Use the return value in another call
    mock_obj.set_value = Mock()
    mock_obj.set_value(result)

    # Check what was passed to set_value
    print("\nMock set_value call:")
    call_args = mock_obj.set_value.call_args
    print(f"Call args: {call_args}")
    value_passed = call_args[0][0]
    print(f"Value passed: '{value_passed}'")
    print(f"Value type: {type(value_passed)}")
    print(f"Is original: {value_passed is test_string}")
    print(f"Is result: {value_passed is result}")

    # Check with direct string literal
    mock_obj.set_literal = Mock()
    mock_obj.set_literal("Test return value")

    # Check what was passed
    print("\nMock set_literal call:")
    literal_args = mock_obj.set_literal.call_args
    print(f"Call args: {literal_args}")
    literal_value = literal_args[0][0]
    print(f"Literal value: '{literal_value}'")

    # Try assert_called_with
    try:
        mock_obj.set_value.assert_called_with(test_string)
        print("assert_called_with(test_string) passed")
    except AssertionError as e:
        print(f"assert_called_with(test_string) failed: {e}")

    try:
        mock_obj.set_literal.assert_called_with("Test return value")
        print("assert_called_with('Test return value') passed")
    except AssertionError as e:
        print(f"assert_called_with('Test return value') failed: {e}")
