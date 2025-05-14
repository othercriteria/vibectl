"""Tests for model adapter."""

import logging
import os
import re
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
from pydantic import BaseModel

from vibectl.model_adapter import (
    LLMAdaptationError,
    LLMMetrics,
    LLMModelAdapter,
    LLMUsage,
    ModelAdapter,
    ModelEnvironment,
    ModelResponse,
    get_model_adapter,
    reset_model_adapter,
    set_model_adapter,
)
from vibectl.types import Fragment, SystemFragments, UserFragments


class TestModelAdapter:
    """Tests for model adapter functions."""

    def setup_method(self) -> None:
        """Reset adapter between tests."""
        reset_model_adapter()

    def test_get_model_adapter(self) -> None:
        """Test get_model_adapter creates a single instance."""
        adapter1 = get_model_adapter()
        adapter2 = get_model_adapter()
        assert adapter1 is adapter2
        assert isinstance(adapter1, LLMModelAdapter)

    def test_set_model_adapter(self) -> None:
        """Test setting a custom adapter."""
        mock_adapter = Mock(spec=ModelAdapter)
        set_model_adapter(mock_adapter)
        adapter = get_model_adapter()
        assert adapter is mock_adapter

    def test_reset_model_adapter(self) -> None:
        """Test resetting the adapter."""
        adapter1 = get_model_adapter()
        reset_model_adapter()
        adapter2 = get_model_adapter()
        assert adapter1 is not adapter2


class TestLLMModelAdapter:
    """Tests for LLMModelAdapter."""

    def setup_method(self) -> None:
        """Reset adapter and aggressively ensure logger level for tests."""
        reset_model_adapter()
        logger_instance = logging.getLogger("vibectl.logutil")
        # Remove any handlers that might have been added by other tests/basicConfig
        for handler in list(logger_instance.handlers):  # Iterate over a copy
            logger_instance.removeHandler(handler)
        logger_instance.setLevel(logging.INFO)  # Explicitly set level
        logger_instance.propagate = False  # Prevent messages going to root logger

    @patch("vibectl.model_adapter.llm")
    def test_get_model(self, mock_llm: MagicMock) -> None:
        """Test getting a model."""
        # Setup
        mock_model = Mock()
        mock_response = Mock(spec=ModelResponse)
        mock_response.text.return_value = "Test response"
        mock_model.prompt.return_value = mock_response
        # Add model_id to the mock model
        mock_model.model_id = "test-model-basic"
        # Set the return value for the patched llm.get_model
        mock_llm.get_model.return_value = mock_model

        # Execute
        adapter = LLMModelAdapter()
        model = adapter.get_model("test-model")

        # Verify
        assert (
            model is mock_llm.get_model.return_value
        )  # Check against the patched return value
        mock_llm.get_model.assert_called_once_with("test-model")

    @patch("vibectl.model_adapter.llm")
    def test_get_model_caching(self, mock_llm: MagicMock) -> None:
        """Test model caching."""
        # Setup
        mock_model = Mock()
        mock_response = Mock(spec=ModelResponse)
        mock_response.text.return_value = "Test response"
        mock_model.prompt.return_value = mock_response
        # Add model_id to the mock model
        mock_model.model_id = "test-model-basic"

        # Execute
        adapter = LLMModelAdapter()
        model1 = adapter.get_model("test-model")
        model2 = adapter.get_model("test-model")

        # Verify
        assert model1 is model2
        mock_llm.get_model.assert_called_once_with("test-model")

    @patch("vibectl.model_adapter.llm")
    def test_get_model_error(self, mock_llm: MagicMock) -> None:
        """Test error handling when getting a model."""
        # Setup
        # mock_model = Mock() # No need to mock the model instance itself
        # mock_response = Mock(spec=ModelResponse)
        # mock_response.text.return_value = "Test response"
        # Set side_effect on the llm.get_model call
        mock_llm.get_model.side_effect = Exception("Test error getting model")

        # Execute and verify
        adapter = LLMModelAdapter()
        with pytest.raises(ValueError, match="Test error getting model") as exc_info:
            adapter.get_model("test-model")

        assert "Failed to get model 'test-model'" in str(exc_info.value)
        mock_llm.get_model.assert_called_once_with("test-model")

    @patch("vibectl.model_adapter.llm")
    def test_execute(self, mock_llm: MagicMock) -> None:
        """Test executing a prompt on a model."""
        # Setup
        mock_model = Mock()
        mock_response = Mock(spec=ModelResponse)
        mock_response.text.return_value = "Test response"
        mock_model.prompt.return_value = mock_response
        mock_model.model_id = "test-model-basic"  # Add model_id
        prompt_text = "Test prompt"

        # Execute
        adapter = LLMModelAdapter()
        response_text, metrics = adapter.execute(
            mock_model,
            system_fragments=SystemFragments([]),
            user_fragments=UserFragments([Fragment(prompt_text)]),
        )

        # Verify
        assert response_text == "Test response"
        mock_model.prompt.assert_called_once()
        call_args, call_kwargs = mock_model.prompt.call_args
        assert call_kwargs.get("fragments") == [prompt_text]
        # Check system kwarg is None or absent
        assert call_kwargs.get("system", None) is None
        assert metrics is not None
        assert metrics.latency_ms > 0

    @patch("vibectl.model_adapter.llm")
    def test_execute_string_response(self, mock_llm: MagicMock) -> None:
        """Test handling string responses."""
        # Setup
        mock_model = Mock()
        mock_response = Mock(spec=ModelResponse)
        mock_response.text.return_value = "Test response"
        mock_model.prompt.return_value = mock_response
        mock_model.model_id = "test-model-basic"  # Add model_id
        prompt_text = "Test prompt"

        # Execute
        adapter = LLMModelAdapter()
        response_text, metrics = adapter.execute(
            mock_model,
            system_fragments=SystemFragments([]),
            user_fragments=UserFragments([Fragment(prompt_text)]),
        )

        # Verify
        assert response_text == "Test response"
        # ... (rest of verification as before) ...

    @patch("vibectl.model_adapter.llm")
    def test_execute_error(self, mock_llm: MagicMock) -> None:
        """Test error handling during execution."""
        # Setup
        mock_model = Mock()
        mock_model.prompt.side_effect = Exception("Test error")
        mock_model.model_id = "test-model-error"  # Add model_id
        prompt_text = "Test prompt"

        expected_msg = (
            f"LLM Execution Error for model {mock_model.model_id}: Test error"
        )

        # Execute and verify
        adapter = LLMModelAdapter()
        with pytest.raises(ValueError, match=re.escape(expected_msg)):
            adapter.execute(
                mock_model,
                system_fragments=SystemFragments([]),
                user_fragments=UserFragments([Fragment(prompt_text)]),
            )

    @patch("vibectl.model_adapter.llm")
    def test_execute_with_type_casting(self, mock_llm: MagicMock) -> None:
        """Test type casting behavior in the execute method."""
        # Setup
        mock_model = Mock()
        mock_model.model_id = "test-model-type-casting"  # Add model_id
        # Re-add mock response definitions
        mock_response_int = Mock(spec=ModelResponse)
        mock_response_int.text.return_value = "42"
        mock_response_float = Mock(spec=ModelResponse)
        mock_response_float.text.return_value = "3.14"
        mock_response_bool = Mock(spec=ModelResponse)
        mock_response_bool.text.return_value = "True"
        mock_response_none = Mock(spec=ModelResponse)
        mock_response_none.text.return_value = "None"

        # Test each response type
        adapter = LLMModelAdapter()

        # Test integer response
        mock_model.prompt.return_value = mock_response_int
        response_text, metrics = adapter.execute(
            mock_model,
            system_fragments=SystemFragments([]),
            user_fragments=UserFragments([Fragment("Integer prompt")]),
        )
        assert response_text == "42"

        # Test float response
        mock_model.prompt.return_value = mock_response_float
        response_text, metrics = adapter.execute(
            mock_model,
            system_fragments=SystemFragments([]),
            user_fragments=UserFragments([Fragment("Float prompt")]),
        )
        assert response_text == "3.14"

        # Test boolean response
        mock_model.prompt.return_value = mock_response_bool
        response_text, metrics = adapter.execute(
            mock_model,
            system_fragments=SystemFragments([]),
            user_fragments=UserFragments([Fragment("Boolean prompt")]),
        )
        assert response_text == "True"

        # Test None response
        mock_model.prompt.return_value = mock_response_none
        response_text, metrics = adapter.execute(
            mock_model,
            system_fragments=SystemFragments([]),
            user_fragments=UserFragments([Fragment("None prompt")]),
        )
        assert response_text == "None"

    @pytest.mark.parametrize(
        "model_name, expected_provider",
        [
            ("gpt-4", "openai"),
            ("gpt-3.5-turbo", "openai"),
            ("anthropic/claude-3-opus-20240229", "anthropic"),
            ("claude-2", "anthropic"),
            ("claude-3-sonnet", "anthropic"),
            ("ollama:llama2", "ollama"),
            ("ollama:mistral", "ollama"),
            ("unknown-model", None),
            (
                "custom/claude-variant",
                "anthropic",
            ),  # Test with prefix that isn't 'anthropic/'
            ("anthropic-claude-custom", "anthropic"),  # Test with suffix
            ("MyOllamaModel:latest", "ollama"),  # Case-insensitivity for ollama prefix
        ],
    )
    def test_determine_provider_from_model(
        self,
        model_name: str,
        expected_provider: str | None,
        adapter_instance: LLMModelAdapter,  # Use a fixture for the adapter instance
    ) -> None:
        """Test _determine_provider_from_model with various model names."""
        assert (
            adapter_instance._determine_provider_from_model(model_name)
            == expected_provider
        )

    def test_get_token_usage_success(
        self, adapter_instance: LLMModelAdapter, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test _get_token_usage successfully extracts tokens."""
        mock_response = MagicMock(spec=ModelResponse)
        mock_response.usage = MagicMock()
        mock_usage_obj = MagicMock()
        mock_usage_obj.input = 100
        mock_usage_obj.output = 200
        mock_response.usage.return_value = mock_usage_obj

        tokens_in, tokens_out = adapter_instance._get_token_usage(
            mock_response, "test-model"
        )

        assert tokens_in == 100
        assert tokens_out == 200
        mock_response.usage.assert_called_once()

    def test_get_token_usage_missing_usage_method(
        self, adapter_instance: LLMModelAdapter, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test _get_token_usage when response lacks usage() method."""
        mock_response = MagicMock(spec=ModelResponse)
        # Make sure calling .usage() on this specific mock raises AttributeError
        # to correctly test the except block in _get_token_usage.
        mock_response.usage.side_effect = AttributeError(
            "usage method explicitly mocked to fail"
        )

        tokens_in, tokens_out = adapter_instance._get_token_usage(
            mock_response, "test-model-no-usage"
        )

        assert tokens_in == 0
        assert tokens_out == 0
        assert "lacks usage() method" in caplog.text

    def test_get_token_usage_usage_returns_none(
        self, adapter_instance: LLMModelAdapter, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test _get_token_usage when usage() returns None."""
        mock_response = MagicMock(spec=ModelResponse)
        mock_response.usage = MagicMock()
        mock_response.usage.return_value = None

        tokens_in, tokens_out = adapter_instance._get_token_usage(
            mock_response, "test-model-usage-none"
        )

        assert tokens_in == 0
        assert tokens_out == 0
        mock_response.usage.assert_called_once()

    def test_get_token_usage_missing_token_attributes(
        self, adapter_instance: LLMModelAdapter, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test _get_token_usage when usage object lacks input/output attributes."""
        mock_response = MagicMock(spec=ModelResponse)
        mock_response.usage = MagicMock()

        # Create a spec for an object that definitely does not have 'input' or 'output'
        # This ensures getattr(mock_usage_obj, "input", None) returns None in the SUT.
        class UsageSpecWithoutTokens:
            pass  # No input/output attributes defined

        mock_usage_obj = MagicMock(spec_set=UsageSpecWithoutTokens)

        mock_response.usage.return_value = mock_usage_obj

        tokens_in, tokens_out = adapter_instance._get_token_usage(
            mock_response, "test-model-missing-attrs"
        )

        assert tokens_in == 0
        assert tokens_out == 0
        mock_response.usage.assert_called_once()

    def test_get_token_usage_none_token_values(
        self, adapter_instance: LLMModelAdapter, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test _get_token_usage when usage object has None for token values."""
        mock_response = MagicMock(spec=ModelResponse)
        mock_response.usage = MagicMock()
        mock_usage_obj = MagicMock()
        mock_usage_obj.input = None
        mock_usage_obj.output = None
        mock_response.usage.return_value = mock_usage_obj

        tokens_in, tokens_out = adapter_instance._get_token_usage(
            mock_response, "test-model-none-values"
        )

        assert tokens_in == 0
        assert tokens_out == 0
        mock_response.usage.assert_called_once()

    def test_get_token_usage_exception_in_usage(
        self, adapter_instance: LLMModelAdapter, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test _get_token_usage when usage() raises an unexpected error."""
        mock_response = MagicMock(spec=ModelResponse)
        mock_response.usage = MagicMock()
        mock_response.usage.side_effect = ValueError("Unexpected usage error")

        tokens_in, tokens_out = adapter_instance._get_token_usage(
            mock_response, "test-model-usage-exception"
        )

        assert tokens_in == 0
        assert tokens_out == 0
        assert "Failed to get token usage" in caplog.text
        assert "Unexpected usage error" in caplog.text
        mock_response.usage.assert_called_once()

    def test_execute_single_prompt_attempt_success(
        self, adapter_instance: LLMModelAdapter
    ) -> None:
        """Test _execute_single_prompt_attempt successfully returns ModelResponse."""
        mock_model = MagicMock()
        mock_model_response_obj = MagicMock(spec=ModelResponse)
        mock_model.prompt.return_value = mock_model_response_obj
        prompt_kwargs = {"prompt": "test prompt"}

        response = adapter_instance._execute_single_prompt_attempt(
            mock_model, prompt_kwargs
        )

        assert response is mock_model_response_obj
        mock_model.prompt.assert_called_once_with(**prompt_kwargs)

    def test_execute_single_prompt_attempt_type_error(
        self, adapter_instance: LLMModelAdapter
    ) -> None:
        """Test _execute_single_prompt_attempt TypeError's for wrong response type."""
        mock_model = MagicMock()
        mock_model.prompt.return_value = "not a ModelResponse object"  # Invalid type
        prompt_kwargs = {"prompt": "test prompt"}

        with pytest.raises(TypeError, match="Expected ModelResponse, got str"):
            adapter_instance._execute_single_prompt_attempt(mock_model, prompt_kwargs)
        mock_model.prompt.assert_called_once_with(**prompt_kwargs)

    def test_handle_prompt_execution_success_first_attempt(
        self, adapter_instance: LLMModelAdapter
    ) -> None:
        """Test _handle_prompt_execution_with_adaptation works on the first attempt."""
        mock_model = MagicMock()
        mock_model.model_id = "test-model"
        mock_response_obj = MagicMock(spec=ModelResponse)
        mock_model.prompt.return_value = mock_response_obj

        initial_kwargs = {"prompt": "test"}
        latencies_ref: list[float] = []

        response, attempt_num = (
            adapter_instance._handle_prompt_execution_with_adaptation(
                mock_model,
                initial_kwargs,
                max_attempts=3,
                all_attempt_latencies_ms_ref=latencies_ref,
            )
        )

        assert response is mock_response_obj
        assert attempt_num == 1
        assert len(latencies_ref) == 1
        assert latencies_ref[0] >= 0
        mock_model.prompt.assert_called_once_with(**initial_kwargs)

    @patch("vibectl.model_adapter.logger.warning")
    @patch("vibectl.model_adapter.logger.info")
    def test_handle_prompt_execution_adapts_by_removing_schema(
        self,
        mock_logger_info: MagicMock,
        mock_logger_warning: MagicMock,
        adapter_instance: LLMModelAdapter,
    ) -> None:
        """Test adaptation by removing 'schema' on AttributeError."""
        mock_model = MagicMock()
        mock_model.model_id = "test-model-schema-adapt"
        mock_response_obj_success = MagicMock(spec=ModelResponse)

        # First call raises AttributeError related to schema, second call succeeds
        attr_error_instance = AttributeError(
            "Model does not support 'schema' parameter"
        )
        mock_model.prompt.side_effect = [attr_error_instance, mock_response_obj_success]

        initial_kwargs = {"prompt": "test", "schema": {"type": "object"}}
        latencies_ref: list[float] = []

        response, attempt_num = (
            adapter_instance._handle_prompt_execution_with_adaptation(
                mock_model,
                initial_kwargs.copy(),  # Pass a copy as it will be modified
                max_attempts=3,
                all_attempt_latencies_ms_ref=latencies_ref,
            )
        )

        assert response is mock_response_obj_success
        assert attempt_num == 2
        assert len(latencies_ref) == 2

        # Assert logger.warning was called for the adaptation attempt
        mock_logger_warning.assert_any_call(
            "Model %s raised AttributeError on attempt %d: %s. Adapting...",
            mock_model.model_id,
            1,  # First attempt failed
            attr_error_instance,
        )

        # Assert logger.info was called for the specific adaptation strategy
        mock_logger_info.assert_any_call(
            "Attempting to adapt by removing 'schema' for model %s.",
            mock_model.model_id,
        )

    @patch("vibectl.model_adapter.logger.warning")
    @patch("vibectl.model_adapter.logger.info")
    def test_handle_prompt_execution_adapts_by_combining_fragments(
        self,
        mock_logger_info: MagicMock,
        mock_logger_warning: MagicMock,
        adapter_instance: LLMModelAdapter,
    ) -> None:
        """Test adaptation by combining 'system' and 'fragments' into 'prompt'."""
        mock_model = MagicMock()
        mock_model.model_id = "test-model-fragments-adapt"
        mock_response_obj_success = MagicMock(spec=ModelResponse)

        # First call raises AttributeError related to fragments, second succeeds
        attr_error_instance = AttributeError(
            "Model does not support 'fragments' parameter"
        )
        mock_model.prompt.side_effect = [attr_error_instance, mock_response_obj_success]

        initial_kwargs = {
            "system": SystemFragments([Fragment("System prompt.")]),
            "fragments": UserFragments(
                [Fragment("User fragment 1."), Fragment("User fragment 2.")]
            ),
        }
        latencies_ref: list[float] = []

        response, attempt_num = (
            adapter_instance._handle_prompt_execution_with_adaptation(
                mock_model,
                initial_kwargs.copy(),  # Pass a copy
                max_attempts=3,
                all_attempt_latencies_ms_ref=latencies_ref,
            )
        )

        assert response is mock_response_obj_success
        assert attempt_num == 2
        assert len(latencies_ref) == 2

        mock_logger_warning.assert_any_call(
            "Model %s raised AttributeError on attempt %d: %s. Adapting...",
            mock_model.model_id,
            1,  # First attempt
            attr_error_instance,
        )
        mock_logger_info.assert_any_call(
            "Attempting to adapt by combining 'system' and 'fragments' "
            "into 'prompt' for model %s.",
            mock_model.model_id,
        )

    # Test for LLMAdaptationError when all retries/adaptations fail.
    @patch("vibectl.model_adapter.logger.error")
    @patch("vibectl.model_adapter.logger.warning")
    @patch("vibectl.model_adapter.logger.info")
    def test_handle_prompt_execution_fails_after_all_adaptations(
        self,
        mock_logger_info: MagicMock,
        mock_logger_warning: MagicMock,
        mock_logger_error: MagicMock,
        adapter_instance: LLMModelAdapter,
    ) -> None:
        """Test LLMAdaptationError is raised when all adaptations fail."""
        mock_model = MagicMock()
        mock_model.model_id = "test-model-all-fail"

        # First call raises an error that triggers schema adaptation,
        # subsequent calls raise a generic AttributeError.
        schema_attr_error = AttributeError("This model has some schema problem")
        persistent_attr_error = AttributeError(
            "Persistent model error after schema removal"
        )
        mock_model.prompt.side_effect = [schema_attr_error, persistent_attr_error]

        initial_kwargs = {"prompt": "test", "schema": {}}
        latencies_ref: list[float] = []
        max_attempts = 2  # Keep it small for this test

        with pytest.raises(LLMAdaptationError) as exc_info:
            adapter_instance._handle_prompt_execution_with_adaptation(
                mock_model,
                initial_kwargs.copy(),
                max_attempts=max_attempts,
                all_attempt_latencies_ms_ref=latencies_ref,
            )

        assert (
            f"Failed for model {mock_model.model_id} due to persistent AttributeError"
            in str(exc_info.value)
        )
        assert exc_info.value.final_attempt_count == max_attempts
        assert len(latencies_ref) == max_attempts
        assert mock_model.prompt.call_count == max_attempts

        # Check that schema adaptation INFO log was called
        mock_logger_info.assert_any_call(
            "Attempting to adapt by removing 'schema' for model %s.",
            mock_model.model_id,
        )

        # Check WARNING logs for each attempt
        mock_logger_warning.assert_any_call(
            "Model %s raised AttributeError on attempt %d: %s. Adapting...",
            mock_model.model_id,
            1,  # First attempt
            schema_attr_error,
        )
        mock_logger_warning.assert_any_call(
            "Model %s raised AttributeError on attempt %d: %s. Adapting...",
            mock_model.model_id,
            2,  # Second attempt
            persistent_attr_error,
        )

        # Check ERROR log for final failure
        expected_error_msg = (
            f"Failed for model {mock_model.model_id} due to persistent AttributeError "
            f"after {max_attempts} attempts and exhausting adaptation strategies. "
            f"Last error: {persistent_attr_error}"
        )
        mock_logger_error.assert_any_call(expected_error_msg)

    # Test for immediate re-raise of non-AttributeError exceptions.
    def test_handle_prompt_execution_reraises_other_exceptions(
        self, adapter_instance: LLMModelAdapter, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test non-AttributeError exceptions are re-raised immediately."""
        mock_model = MagicMock()
        mock_model.model_id = "test-model-other-error"

        # First call raises ValueError
        mock_model.prompt.side_effect = ValueError("Some other LLM error")

        initial_kwargs = {"prompt": "test"}
        latencies_ref: list[float] = []

        with pytest.raises(ValueError, match="Some other LLM error"):
            adapter_instance._handle_prompt_execution_with_adaptation(
                mock_model,
                initial_kwargs.copy(),
                max_attempts=3,
                all_attempt_latencies_ms_ref=latencies_ref,
            )

        assert len(latencies_ref) == 1  # Only one attempt should be made
        assert mock_model.prompt.call_count == 1
        assert "failed on attempt 1 with non-AttributeError" in caplog.text

    @patch.object(LLMModelAdapter, "_get_token_usage")
    @patch.object(LLMModelAdapter, "_handle_prompt_execution_with_adaptation")
    @patch("vibectl.model_adapter.logger.info")
    def test_execute_success_path(
        self,
        mock_logger_info: MagicMock,
        mock_handle_execution: MagicMock,
        mock_get_tokens: MagicMock,
        adapter_instance: LLMModelAdapter,
    ) -> None:
        """Test the successful execution path of the main execute method."""
        mock_model = MagicMock()
        mock_model.model_id = "test-execute-success"

        mock_response_obj = MagicMock(spec=ModelResponse)
        mock_response_obj.text.return_value = "Successful response text"

        # Side effect for _handle_prompt_execution_with_adaptation
        # It returns (response_obj, attempt_num) and modifies latencies list
        # For this success path, the actual llm_lib_latency will be in the list.
        # Let's simulate one attempt with a latency of 10.0 ms.
        # The mock_handle_execution is for the SUT's internal call.
        def side_effect_for_handle_execution(
            model_arg: Any,
            initial_kwargs_arg: dict[str, Any],
            max_attempts_arg: int,
            all_attempt_latencies_ms_ref_arg: list[float],
        ) -> tuple[MagicMock, int]:
            all_attempt_latencies_ms_ref_arg.append(
                10.0
            )  # This is llm_lib_latency for the successful call
            return mock_response_obj, 1

        mock_handle_execution.side_effect = side_effect_for_handle_execution
        mock_get_tokens.return_value = (10, 20)  # (tokens_in, tokens_out)

        system_frags = SystemFragments([Fragment("System prompt")])
        user_frags = UserFragments([Fragment("User prompt")])

        # Call execute
        response_text, metrics = adapter_instance.execute(
            mock_model, system_frags, user_frags
        )

        assert response_text == "Successful response text"
        assert metrics is not None
        assert metrics.token_input == 10
        assert metrics.token_output == 20
        assert metrics.call_count == 1
        assert metrics.latency_ms > 0  # text_extraction_duration_ms
        assert metrics.total_processing_duration_ms is not None
        assert metrics.total_processing_duration_ms > metrics.latency_ms

        mock_handle_execution.assert_called_once()
        mock_get_tokens.assert_called_once_with(mock_response_obj, mock_model.model_id)
        mock_response_obj.text.assert_called_once()

        # Assert specific logger.info calls
        # The llm_lib_latency used in the final log message comes from the last entry
        # in all_attempt_latencies_ms_list, which our side_effect sets to 10.0
        llm_lib_latency_for_log = 10.0

        # The first message to check
        mock_logger_info.assert_any_call(
            "LLM call to model %s completed. Primary Latency (text_extraction): "
            "%.2f ms, llm_lib_latency: %.2f ms, Total Duration: %.2f ms, "
            "Tokens In: %d, Tokens Out: %d",
            mock_model.model_id,
            metrics.latency_ms,  # This is text_extraction_duration_ms
            llm_lib_latency_for_log,
            metrics.total_processing_duration_ms,
            metrics.token_input,
            metrics.token_output,
        )


def test_model_response_protocol_runtime_check() -> None:
    class DummyResponse:
        def text(self) -> str:
            return "foo"

        def json(self) -> dict[str, Any]:
            return {"foo": "bar"}

        def usage(self) -> LLMUsage:  # Assuming LLMUsage is importable or defined here
            # A mock LLMUsage object or a simple class implementing it
            class DummyUsage(LLMUsage):
                input: int = 0
                output: int = 0
                details: dict[str, Any] | None = None

            return DummyUsage()

    resp = DummyResponse()
    assert isinstance(resp, ModelResponse)


def test_model_adapter_abc_methods() -> None:
    class DummyAdapter(ModelAdapter):
        def get_model(self, model_name: str) -> str:
            raise NotImplementedError()

        # Update signature to match ModelAdapter
        def execute(
            self,
            model: Any,
            system_fragments: SystemFragments,
            user_fragments: UserFragments,
            response_model: type[BaseModel] | None = None,
        ) -> tuple[str, LLMMetrics | None]:
            # Dummy impl. needs adjustment if it was calling self.execute
            # For ABC test, just raise or return dummy data
            raise NotImplementedError("Dummy execute should not be called in ABC test")
            # return "dummy_response", None

        def validate_model_key(self, model_name: str) -> str | None:
            raise NotImplementedError()

        def validate_model_name(self, model_name: str) -> str | None:
            return None

        # Update signature to match ModelAdapter
        def execute_and_log_metrics(
            self,
            model: Any,
            system_fragments: SystemFragments,
            user_fragments: UserFragments,
            response_model: type[BaseModel] | None = None,
        ) -> tuple[str, LLMMetrics | None]:
            # Dummy impl. needs adjustment
            raise NotImplementedError(
                "Dummy execute_and_log_metrics should not be called in ABC test"
            )
            # return "dummy_response", None

    adapter = DummyAdapter()
    with pytest.raises(NotImplementedError):
        adapter.get_model("foo")
    with pytest.raises(NotImplementedError):
        adapter.validate_model_key("foo")
    # Test execute and execute_and_log_metrics raise NotImplementedError
    with pytest.raises(NotImplementedError):
        adapter.execute(None, SystemFragments([]), UserFragments([]))
    with pytest.raises(NotImplementedError):
        adapter.execute_and_log_metrics(None, SystemFragments([]), UserFragments([]))


def test_validate_model_key_unknown_provider() -> None:
    adapter = LLMModelAdapter()
    msg = adapter.validate_model_key("unknown-model")
    assert isinstance(msg, str) and "Unknown model provider" in msg


def test_validate_model_key_ollama() -> None:
    adapter = LLMModelAdapter()
    # Should return None for ollama
    assert adapter.validate_model_key("ollama:foo") is None


def test_validate_model_key_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = LLMModelAdapter()
    monkeypatch.setattr(adapter.config, "get_model_key", lambda provider: None)
    msg = adapter.validate_model_key("gpt-3.5-turbo")
    assert isinstance(msg, str) and "No API key found" in msg


def test_validate_model_key_invalid_format(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = LLMModelAdapter()
    # Provide a long key that doesn't start with sk-
    monkeypatch.setattr(adapter.config, "get_model_key", lambda provider: "x" * 30)
    msg = adapter.validate_model_key("gpt-3.5-turbo")
    assert isinstance(msg, str) and "API key format looks invalid" in msg


def test_validate_model_key_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = LLMModelAdapter()
    monkeypatch.setattr(adapter.config, "get_model_key", lambda provider: "sk-abc123")
    assert adapter.validate_model_key("gpt-3.5-turbo") is None


def test_model_environment_all_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    # Unknown provider: should do nothing
    config = Mock()
    env = ModelEnvironment("foo-bar", config)
    assert env.provider is None
    env.__enter__()  # __enter__ returns None, no need to assert
    # Known provider, no key
    config.get_model_key.return_value = None
    env = ModelEnvironment("gpt-3.5-turbo", config)
    # No key, so nothing set
    env.__enter__()
    # Known provider, with key, no original env
    config.get_model_key.return_value = "test-key"
    env = ModelEnvironment("gpt-3.5-turbo", config)
    # Remove env var if present
    os.environ.pop("OPENAI_API_KEY", None)
    env.__enter__()
    assert os.environ["OPENAI_API_KEY"] == "test-key"
    env.__exit__(None, None, None)
    assert "OPENAI_API_KEY" not in os.environ
    # Known provider, with key, with original env
    os.environ["OPENAI_API_KEY"] = "orig-key"
    config.get_model_key.return_value = "test-key"
    env = ModelEnvironment("gpt-3.5-turbo", config)
    env.__enter__()
    assert os.environ["OPENAI_API_KEY"] == "test-key"
    env.__exit__(None, None, None)
    assert os.environ["OPENAI_API_KEY"] == "orig-key"


def test_get_model_ollama_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ollama models should not require an API key, even if none is set."""
    from vibectl.model_adapter import LLMModelAdapter

    adapter = LLMModelAdapter()
    # Patch llm.get_model to return a dummy model
    monkeypatch.setattr("vibectl.model_adapter.llm.get_model", lambda name: object())
    # Should not raise
    adapter.get_model("ollama:tinyllama")


def test_get_model_ollama_with_dummy_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ollama models should not error if a dummy API key is set."""
    from vibectl.model_adapter import LLMModelAdapter

    adapter = LLMModelAdapter()
    # Patch config.get_model_key to return a dummy key for ollama
    monkeypatch.setattr(
        adapter.config,
        "get_model_key",
        lambda provider: "dummy" if provider == "ollama" else None,
    )
    # Patch llm.get_model to return a dummy model
    monkeypatch.setattr("vibectl.model_adapter.llm.get_model", lambda name: object())
    # Should not raise
    adapter.get_model("ollama:tinyllama")


class TestLLMModelAdapterSchemaFallback:
    """Tests specifically for the schema fallback logic in LLMModelAdapter."""

    class MockResponse:
        def __init__(self, text_content: str):
            self._text = text_content

        def text(self) -> str:
            return self._text

        def json(self) -> dict[str, Any]:
            # Return a simple dict, can be customized if needed per test
            return {"text_content": self._text, "source": "mock"}

        def usage(self) -> LLMUsage:
            # Return a mock LLMUsage object
            class MockUsage(LLMUsage):
                input: int = 10  # Example value
                output: int = 20  # Example value
                # details: dict[str, Any] | None = {"mock_detail": True} # RUF012 issue

                def __init__(self) -> None:
                    self.details: dict[str, Any] | None = {"mock_detail": True}

            return MockUsage()

    class DummySchema(BaseModel):
        field: str

    @patch("vibectl.model_adapter.llm")
    def test_execute_schema_unsupported_fallback(self, mock_llm: MagicMock) -> None:
        """Test fallback when model.prompt raises schema-related AttributeError."""
        # Setup
        mock_model = Mock()
        mock_model.model_id = "test-fallback-model"  # Add model_id
        mock_fallback_response = self.MockResponse("Fallback response text")
        mock_model.prompt.side_effect = [
            AttributeError("'Model' object has no attribute 'schema'"),
            mock_fallback_response,
        ]
        prompt_text = "Test prompt"

        # Execute
        adapter = LLMModelAdapter()
        response_text, metrics = adapter.execute(
            mock_model,
            system_fragments=SystemFragments([]),
            user_fragments=UserFragments([Fragment(prompt_text)]),
            response_model=self.DummySchema,
        )

        # Verify
        assert response_text == "Fallback response text"
        assert mock_model.prompt.call_count == 2
        first_call_args, first_call_kwargs = mock_model.prompt.call_args_list[0]
        second_call_args, second_call_kwargs = mock_model.prompt.call_args_list[1]
        assert first_call_kwargs.get("schema") is not None
        assert "schema" not in second_call_kwargs
        # Check metrics exist and basic fields are present
        assert metrics is not None
        assert metrics.latency_ms > 0
        assert metrics.call_count == 2

    @patch("vibectl.model_adapter.llm")
    def test_execute_schema_supported(self, mock_llm: MagicMock) -> None:
        """Test execute works normally when schema is supported."""
        # Setup
        mock_model = Mock()
        mock_model.model_id = "test-schema-model"  # Add model_id
        mock_response = Mock(spec=ModelResponse)
        mock_response.text.return_value = '{"field": "value"}'
        mock_model.prompt.return_value = mock_response
        prompt_text = "Test prompt"

        # Execute
        adapter = LLMModelAdapter()
        response_text, metrics = adapter.execute(
            mock_model,
            system_fragments=SystemFragments([]),
            user_fragments=UserFragments([Fragment(prompt_text)]),
            response_model=self.DummySchema,
        )

        # Verify
        assert response_text == '{"field": "value"}'
        mock_model.prompt.assert_called_once()
        call_args, call_kwargs = mock_model.prompt.call_args
        assert call_kwargs.get("schema") is not None
        # Check metrics exist and basic fields are present
        assert metrics is not None
        assert metrics.call_count == 1

    @patch("vibectl.model_adapter.llm")
    def test_execute_unrelated_attribute_error(self, mock_llm: MagicMock) -> None:
        """Test unrelated AttributeError from prompt is wrapped."""
        # Setup
        adapter = LLMModelAdapter()
        mock_model = Mock()
        mock_model.model_id = "test-attr-err-model"
        original_attribute_error_msg = "Some other attribute is missing"
        mock_model.prompt.side_effect = AttributeError(original_attribute_error_msg)

        system_frags = SystemFragments([])
        user_frags = UserFragments([Fragment("Test prompt")])

        # Construct the expected message from LLMAdaptationError
        # This is lae.args[0] in the execute method
        expected_lae_msg_part = (
            f"Failed for model {mock_model.model_id} due to persistent AttributeError "
            "after 1 attempts and exhausting adaptation strategies. "
            f"Last error: {original_attribute_error_msg}"
        )

        # Construct the final expected ValueError message from execute
        expected_final_error_msg = (
            f"LLM execution failed for model {mock_model.model_id} after 1 "
            "adaptation attempts: "
            f"{expected_lae_msg_part}"
        )

        with pytest.raises(ValueError, match=re.escape(expected_final_error_msg)):
            adapter.execute(
                mock_model,
                system_fragments=system_frags,
                user_fragments=user_frags,
                response_model=self.DummySchema,  # Keep schema for this test variant
            )


class TestModelEnvironment:
    """Tests for ModelEnvironment."""

    def test_enter_unknown_provider(self) -> None:
        """Test __enter__ does nothing for unknown provider."""
        original_env = dict(os.environ)
        try:
            os.environ.clear()  # Start clean
            config = Mock()
            env = ModelEnvironment("unknown-model", config)
            with env:  # Enter the context
                # Check that no relevant env vars were set
                assert "OPENAI_API_KEY" not in os.environ
                assert "ANTHROPIC_API_KEY" not in os.environ
                assert "OLLAMA_API_KEY" not in os.environ
            # Exit should also leave env clean
            assert not os.environ
        finally:
            os.environ.clear()
            os.environ.update(original_env)

    def test_enter_ollama_provider(self) -> None:
        """Test __enter__ does nothing for ollama provider."""
        original_env = dict(os.environ)
        try:
            os.environ.clear()  # Start clean
            config = Mock()
            # Mock the get_model_key method to simulate having a key
            config.get_model_key.return_value = "dummy-ollama-key"
            env = ModelEnvironment("ollama:llama3", config)
            with env:  # Enter the context
                # Check that no relevant env vars were set
                assert "OPENAI_API_KEY" not in os.environ
                assert "ANTHROPIC_API_KEY" not in os.environ
                assert "OLLAMA_API_KEY" not in os.environ
            # Exit should also leave env clean
            assert not os.environ
        finally:
            os.environ.clear()
            os.environ.update(original_env)


# Fixture for LLMModelAdapter instance to be reused in tests
@pytest.fixture
def adapter_instance() -> LLMModelAdapter:
    return LLMModelAdapter()
