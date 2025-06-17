"""Tests for model adapter."""

import asyncio
import json
import logging
import re
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import llm
import pytest
from pydantic import BaseModel

from vibectl.model_adapter import (
    LLMAdaptationError,
    LLMModelAdapter,
    LLMResponseParseError,
    LLMUsage,
    ModelAdapter,
    ModelResponse,
    SyncLLMResponseAdapter,
    get_model_adapter,
    reset_model_adapter,
    set_model_adapter,
)
from vibectl.types import (
    Fragment,
    RecoverableApiError,
    SystemFragments,
    UserFragments,
)


class TestModelAdapter:
    """Tests for model adapter functions."""

    def setup_method(self) -> None:
        """Reset adapter between tests."""
        reset_model_adapter()

    @patch("vibectl.model_adapter.Config")
    def test_get_model_adapter(self, mock_config_class: Mock) -> None:
        """Test get_model_adapter creates a single instance."""
        # Mock Config to return a config with no proxy enabled
        mock_config = Mock()
        mock_config.is_proxy_enabled.return_value = False
        mock_config_class.return_value = mock_config

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

    @patch("vibectl.model_adapter.Config")
    def test_reset_model_adapter(self, mock_config_class: Mock) -> None:
        """Test resetting the adapter."""
        # Mock Config to return a config with no proxy enabled
        mock_config = Mock()
        mock_config.is_proxy_enabled.return_value = False
        mock_config_class.return_value = mock_config

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

    @pytest.fixture
    def adapter_instance(self) -> LLMModelAdapter:
        """Provides an instance of LLMModelAdapter for tests."""
        return LLMModelAdapter()

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
    async def test_execute(self, mock_llm: MagicMock) -> None:
        """Test executing a prompt on a model."""
        # Setup
        mock_model = Mock()  # This is the llm.models.Model instance

        # This mock_raw_llm_response is what mock_model.prompt() returns
        mock_raw_llm_response = MagicMock()
        mock_raw_llm_response.text = MagicMock(return_value="Test response")
        mock_raw_llm_response.usage = {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "details": "some_details_for_test_execute",
        }
        # If .json() is called, it should also be sync
        mock_raw_llm_response.json = MagicMock(return_value={"key": "value"})

        mock_model.prompt.return_value = mock_raw_llm_response
        mock_model.model_id = "test-model-basic"  # Add model_id
        prompt_text = "Test prompt"

        # Execute
        adapter = LLMModelAdapter()
        response_text, metrics = await adapter.execute(  # Added await
            mock_model,
            system_fragments=SystemFragments([]),
            user_fragments=UserFragments([Fragment(prompt_text)]),
        )

        # Verify
        assert response_text == "Test response"
        mock_model.prompt.assert_called_once()
        _call_args, call_kwargs = mock_model.prompt.call_args
        assert call_kwargs.get("fragments") == [Fragment(prompt_text)]
        assert call_kwargs.get("system", None) is None
        assert metrics is not None
        assert metrics.latency_ms > 0
        assert metrics.token_input == 10
        assert metrics.token_output == 20

    @patch("vibectl.model_adapter.llm")
    async def test_execute_string_response(self, mock_llm: MagicMock) -> None:
        """Test handling string responses."""
        # Setup
        mock_model = Mock()
        mock_raw_llm_response = MagicMock()
        mock_raw_llm_response.text = MagicMock(return_value="Simple string response")
        mock_raw_llm_response.usage = {
            "prompt_tokens": 5,
            "completion_tokens": 5,
            "details": "some_details_for_test_execute_string_response",
        }
        mock_raw_llm_response.json = MagicMock(return_value={"key": "value"})

        mock_model.prompt.return_value = mock_raw_llm_response
        mock_model.model_id = "test-model-basic"
        prompt_text = "Test prompt"

        # Execute
        adapter = LLMModelAdapter()
        response_text, metrics = await adapter.execute(  # Added await
            mock_model,
            system_fragments=SystemFragments([]),
            user_fragments=UserFragments([Fragment(prompt_text)]),
        )

        # Verify
        assert response_text == "Simple string response"
        mock_model.prompt.assert_called_once()
        _call_args, call_kwargs = mock_model.prompt.call_args
        assert call_kwargs.get("fragments") == [Fragment(prompt_text)]
        assert call_kwargs.get("system", None) is None
        assert metrics is not None
        assert metrics.latency_ms > 0
        assert metrics.token_input == 5
        assert metrics.token_output == 5

    @patch("vibectl.model_adapter.llm")
    async def test_execute_error(self, mock_llm: MagicMock) -> None:
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
            await adapter.execute(
                mock_model,
                system_fragments=SystemFragments([]),
                user_fragments=UserFragments([Fragment(prompt_text)]),
            )

    @patch("vibectl.model_adapter.llm")
    async def test_execute_with_type_casting(self, mock_llm: MagicMock) -> None:
        """Test executing with Pydantic model for type casting."""

        class MyResponse(BaseModel):
            message: str
            value: int

        # Setup
        mock_model = Mock()
        mock_raw_llm_response = MagicMock()
        # .text should be the raw JSON string for Pydantic parsing
        mock_raw_llm_response.text = MagicMock(
            return_value='{"message": "Success", "value": 123}'
        )
        mock_raw_llm_response.usage = {
            "prompt_tokens": 20,
            "completion_tokens": 30,
            "details": "some_details_for_test_execute_with_type_casting",
        }
        mock_raw_llm_response.json = MagicMock(
            return_value={"message": "Success", "value": 123}
        )

        mock_model.prompt.return_value = mock_raw_llm_response
        mock_model.model_id = "test-model-typing"
        prompt_text = "Generate typed output"

        # Execute
        adapter = LLMModelAdapter()
        response_text, metrics = await adapter.execute(
            mock_model,
            system_fragments=SystemFragments([]),
            user_fragments=UserFragments([Fragment(prompt_text)]),
            response_model=MyResponse,
        )

        # Verify
        assert (
            json.loads(response_text)
            == MyResponse(message="Success", value=123).model_dump()
        )
        mock_model.prompt.assert_called_once()
        _call_args, call_kwargs = mock_model.prompt.call_args
        assert call_kwargs.get("fragments") == [Fragment(prompt_text)]
        assert call_kwargs.get("system", None) is None
        # Ensure response_model was passed to prompt if applicable by llm library
        # This depends on how llm library handles schema/response_model with .prompt()
        # For now, we assume it might be in kwargs, or handled internally by adapter.
        # assert call_kwargs.get("response_model") == MyResponse # Or similar check

        assert metrics is not None
        assert metrics.latency_ms > 0
        assert metrics.token_input == 20
        assert metrics.token_output == 30

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

    async def test_get_token_usage_success(
        self, adapter_instance: LLMModelAdapter, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test _get_token_usage successfully extracts tokens."""
        mock_response = MagicMock()  # This is the ModelResponse object
        mock_response.usage = AsyncMock(
            return_value=cast(LLMUsage, {"input": 100, "output": 200, "details": None})
        )

        tokens_in, tokens_out = await adapter_instance._get_token_usage(
            mock_response, "test-model"
        )

        assert tokens_in == 100
        assert tokens_out == 200
        mock_response.usage.assert_called_once()

    async def test_get_token_usage_missing_usage_method(
        self, adapter_instance: LLMModelAdapter, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test _get_token_usage when response lacks usage() method."""
        mock_response = MagicMock()
        mock_response.usage = AsyncMock()
        mock_response.usage.side_effect = AttributeError(
            "usage method explicitly mocked to fail"
        )

        tokens_in, tokens_out = await adapter_instance._get_token_usage(
            mock_response, "test-model-no-usage"
        )

        assert tokens_in == 0
        assert tokens_out == 0
        assert "lacks usage() method" in caplog.text

    async def test_get_token_usage_usage_returns_none(
        self, adapter_instance: LLMModelAdapter, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test _get_token_usage when usage() returns None."""
        mock_response = MagicMock()
        mock_response.usage = AsyncMock()
        mock_response.usage.return_value = None

        tokens_in, tokens_out = await adapter_instance._get_token_usage(
            mock_response, "test-model-usage-none"
        )

        assert tokens_in == 0
        assert tokens_out == 0
        mock_response.usage.assert_called_once()

    async def test_get_token_usage_missing_token_attributes(
        self, adapter_instance: LLMModelAdapter, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test _get_token_usage when usage object lacks input/output attributes."""
        mock_response = MagicMock()
        mock_response.usage = AsyncMock()

        # Create a spec for an object that definitely does not have 'input' or 'output'
        # This ensures getattr(mock_usage_obj, "input", None) returns None in the SUT.
        class UsageSpecWithoutTokens:
            pass  # No input/output attributes defined

        mock_usage_obj = MagicMock(spec_set=UsageSpecWithoutTokens)

        mock_response.usage.return_value = mock_usage_obj

        tokens_in, tokens_out = await adapter_instance._get_token_usage(
            mock_response, "test-model-missing-attrs"
        )

        assert tokens_in == 0
        assert tokens_out == 0
        mock_response.usage.assert_called_once()

    async def test_get_token_usage_none_token_values(
        self, adapter_instance: LLMModelAdapter, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test _get_token_usage when usage object has None for token values."""
        mock_response = MagicMock()
        mock_response.usage = AsyncMock()
        mock_response.usage = AsyncMock(
            return_value=cast(
                LLMUsage, {"input": None, "output": None, "details": "some details"}
            )
        )

        tokens_in, tokens_out = await adapter_instance._get_token_usage(
            mock_response, "test-model-none-values"
        )

        assert tokens_in == 0
        assert tokens_out == 0
        mock_response.usage.assert_called_once()

    async def test_get_token_usage_exception_in_usage(
        self, adapter_instance: LLMModelAdapter, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test _get_token_usage when usage() raises an unexpected error."""
        mock_response = MagicMock()
        mock_response.usage = AsyncMock()
        mock_response.usage.side_effect = ValueError("Unexpected usage error")

        tokens_in, tokens_out = await adapter_instance._get_token_usage(
            mock_response, "test-model-usage-exception"
        )

        assert tokens_in == 0
        assert tokens_out == 0
        assert "Failed to get token usage" in caplog.text
        assert "Unexpected usage error" in caplog.text
        mock_response.usage.assert_called_once()

    @patch("vibectl.model_adapter.LLMModelAdapter._execute_single_prompt_attempt")
    async def test_execute_single_prompt_attempt_success(
        self, mock_execute_single_prompt: MagicMock, adapter_instance: LLMModelAdapter
    ) -> None:
        """Test _execute_single_prompt_attempt successfully returns a response."""
        mock_model_instance = MagicMock()
        mock_model_instance.model_id = "test_model_id"

        mock_adapted_response = MagicMock()
        mock_adapted_response.text = AsyncMock(
            return_value="successful response from handle"
        )
        mock_adapted_response.json = AsyncMock(return_value={"data": "json_data"})
        mock_adapted_response.usage = AsyncMock(
            return_value=cast(LLMUsage, {"input": 10, "output": 5, "details": None})
        )

        with patch.object(
            adapter_instance, "_get_token_usage", new_callable=AsyncMock
        ) as mock_get_tokens:
            mock_get_tokens.return_value = (10, 5)  # input_tokens, output_tokens

            with patch.object(
                adapter_instance, "_handle_prompt_execution_with_adaptation"
            ) as mock_handle_execution:

                def handle_execution_side_effect(
                    model: Any,
                    initial_prompt_kwargs: dict[str, Any],
                    max_attempts: int,
                    all_attempt_latencies_ms_ref: list[float],
                ) -> tuple[MagicMock, int]:
                    all_attempt_latencies_ms_ref.append(
                        123.0
                    )  # Simulate a latency value
                    return mock_adapted_response, 1  # response, attempts

                mock_handle_execution.side_effect = handle_execution_side_effect

                response_str, metrics = await adapter_instance.execute_and_log_metrics(
                    mock_model_instance,
                    SystemFragments([]),
                    UserFragments([Fragment("test")]),
                    response_model=None,
                )

        assert response_str == "successful response from handle"
        assert metrics is not None
        assert metrics.token_input == 10
        assert metrics.token_output == 5
        mock_handle_execution.assert_called_once()
        mock_get_tokens.assert_called_once_with(
            mock_adapted_response, mock_model_instance.model_id
        )

    @patch("vibectl.model_adapter.LLMModelAdapter._execute_single_prompt_attempt")
    async def test_execute_single_prompt_attempt_type_error(
        self, mock_execute_single_prompt: MagicMock, adapter_instance: LLMModelAdapter
    ) -> None:
        """Test _execute_single_prompt_attempt raises TypeError on non-ModelResponse."""
        mock_model_instance = MagicMock()
        mock_model_instance.model_id = "test_model_id"
        mock_execute_single_prompt.return_value = (
            "not a ModelResponse object"  # Invalid return
        )

        with (
            pytest.raises(
                ValueError,
                match="LLM Execution Error for model test_model_id: "
                "_execute_single_prompt_attempt must return a ModelResponse",
            ),
            patch.object(
                adapter_instance, "_get_token_usage", new_callable=AsyncMock
            ) as mock_get_tokens,
            patch.object(
                adapter_instance, "_handle_prompt_execution_with_adaptation"
            ) as mock_handle_execution,
        ):
            mock_get_tokens.return_value = (0, 0)

            # Make _handle_prompt_execution_with_adaptation re-raise the original error
            def side_effect_for_handle_execution(
                *args: Any, **kwargs: Any
            ) -> tuple[MagicMock, int]:
                raise TypeError(  # This internal mock should still raise TypeError
                    "_execute_single_prompt_attempt must return a ModelResponse"
                )

            mock_handle_execution.side_effect = side_effect_for_handle_execution
            await adapter_instance.execute_and_log_metrics(
                mock_model_instance,
                SystemFragments([]),
                UserFragments([Fragment("test")]),
                response_model=None,
                # Explicitly None as mock_prompt_kwargs does not contain
                # response_model class
            )

    @patch.object(LLMModelAdapter, "_execute_single_prompt_attempt")
    @patch.object(LLMModelAdapter, "_get_token_usage", new_callable=AsyncMock)
    async def test_handle_prompt_execution_success_first_attempt(
        self,
        mock_get_tokens: AsyncMock,
        mock_execute_single: MagicMock,
        adapter_instance: LLMModelAdapter,
    ) -> None:
        """Test _handle_prompt_execution_with_adaptation succeeds on first attempt."""
        # Setup
        mock_model_obj = Mock(spec=llm.models.Model)
        mock_model_obj.model_id = "test_model_id"

        # Mock for SyncLLMResponseAdapter that _execute_single_prompt_attempt returns
        mock_sync_adapter_response = MagicMock(spec=SyncLLMResponseAdapter)
        mock_sync_adapter_response.text = AsyncMock(return_value="Successful response")
        # Mock .usage() to return what _get_token_usage expects
        mock_sync_adapter_response.usage = AsyncMock(
            return_value=cast(LLMUsage, {"input": 10, "output": 20})
        )

        mock_execute_single.return_value = mock_sync_adapter_response

        mock_get_tokens.return_value = (10, 20)  # input_tokens, output_tokens

        initial_prompt_kwargs = {
            "system": "System prompt",
            "fragments": [Fragment("User prompt")],
        }
        max_attempts = 3
        all_attempt_latencies_ms: list[float] = []

        # Execute
        response_obj, attempt_count = (
            adapter_instance._handle_prompt_execution_with_adaptation(
                model=mock_model_obj,
                initial_prompt_kwargs=initial_prompt_kwargs,
                max_attempts=max_attempts,
                all_attempt_latencies_ms_ref=all_attempt_latencies_ms,
            )
        )

        # Verify
        assert await response_obj.text() == "Successful response"
        assert attempt_count == 1
        mock_execute_single.assert_called_once_with(
            mock_model_obj, initial_prompt_kwargs
        )

    @patch("vibectl.model_adapter.logger.warning")
    @patch("vibectl.model_adapter.logger.info")
    @patch.object(LLMModelAdapter, "_execute_single_prompt_attempt")
    @patch.object(LLMModelAdapter, "_get_token_usage", new_callable=AsyncMock)
    async def test_handle_prompt_execution_adapts_by_removing_schema(
        self,
        mock_get_tokens: AsyncMock,
        mock_execute_single: MagicMock,
        mock_logger_info: MagicMock,
        mock_logger_warning: MagicMock,
        adapter_instance: LLMModelAdapter,
    ) -> None:
        """Test adaptation by removing schema after RecoverableApiError."""
        mock_model_obj = Mock(spec=llm.models.Model)
        mock_model_obj.model_id = "test_model_id"

        mock_success_response_adapter = MagicMock(
            spec=SyncLLMResponseAdapter
        )  # What _execute_single returns
        mock_success_response_adapter.text = AsyncMock(
            return_value="Success after removing schema"
        )
        mock_success_response_adapter.json = AsyncMock(
            return_value={"data": "some_data"}
        )
        mock_success_response_adapter.usage = AsyncMock(
            return_value=cast(LLMUsage, {"input": 5, "output": 15})
        )

        # First call should raise AttributeError related to schema
        # Second call should succeed
        mock_execute_single.side_effect = [
            AttributeError(
                "Something went wrong with the schema provided"
            ),  # Changed to AttributeError
            mock_success_response_adapter,  # Successful response after adaptation
        ]

        mock_get_tokens.return_value = (5, 15)  # For the successful attempt

        initial_prompt_kwargs = {
            "system": "System prompt",
            "fragments": ["User prompt"],  # String list
            "schema": {"type": "object", "properties": {"key": {"type": "string"}}},
        }
        all_attempt_latencies_ms: list[float] = []

        response_obj, attempt_count = (
            adapter_instance._handle_prompt_execution_with_adaptation(
                model=mock_model_obj,
                initial_prompt_kwargs=initial_prompt_kwargs,
                max_attempts=3,
                all_attempt_latencies_ms_ref=all_attempt_latencies_ms,
            )
        )

        assert await response_obj.text() == "Success after removing schema"
        assert attempt_count == 2
        assert mock_execute_single.call_count == 2

        # Verify second call to _execute_single_prompt_attempt had the schema removed
        second_call_args = mock_execute_single.call_args_list[1]
        # The model is the first positional argument after self
        assert second_call_args[0][0] is mock_model_obj
        # Prompt kwargs is the second positional argument
        prompt_kwargs_in_second_call = second_call_args[0][1]
        assert "schema" not in prompt_kwargs_in_second_call
        assert prompt_kwargs_in_second_call["system"] == "System prompt"
        assert prompt_kwargs_in_second_call["fragments"] == ["User prompt"]

        mock_logger_warning.assert_called_once()
        # Ensure the warning log contains the expected message format and model_id
        args, _ = mock_logger_warning.call_args
        assert (
            "Model %s raised AttributeError on attempt %d: %s. Adapting..." in args[0]
        )
        assert args[1] == mock_model_obj.model_id
        assert args[2] == 1  # Attempt number

        mock_logger_info.assert_any_call(
            "Attempting to adapt by removing 'schema' for model "
            f"{mock_model_obj.model_id}."
        )
        assert len(all_attempt_latencies_ms) == 2

    @patch("vibectl.model_adapter.logger.warning")
    @patch("vibectl.model_adapter.logger.info")
    @patch.object(LLMModelAdapter, "_execute_single_prompt_attempt")
    @patch.object(LLMModelAdapter, "_get_token_usage", new_callable=AsyncMock)
    async def test_handle_prompt_execution_adapts_by_combining_fragments(
        self,
        mock_get_tokens: AsyncMock,
        mock_execute_single: MagicMock,
        mock_logger_info: MagicMock,
        mock_logger_warning: MagicMock,
        adapter_instance: LLMModelAdapter,
    ) -> None:
        """Test adaptation by combining fragments after RecoverableApiError."""
        mock_model_obj = Mock(spec=llm.models.Model)
        mock_model_obj.model_id = "test_model_id"

        # Mock for the SyncLLMResponseAdapter
        mock_success_response = MagicMock(spec=SyncLLMResponseAdapter)
        mock_success_response.text = AsyncMock(
            return_value="Success after combining fragments"
        )
        mock_success_response.usage = AsyncMock(
            return_value=cast(LLMUsage, {"input": 10, "output": 30})
        )

        # _execute_single_prompt_attempt behavior:
        # 1st call: fails (original fragments)
        # 2nd call: succeeds (fragments combined)
        mock_execute_single.side_effect = [
            AttributeError(
                "Model does not support separate system/fragments prompts"
            ),  # Changed error type
            mock_success_response,  # Successful response after adaptation
        ]
        expected_attempt_count = 2
        expected_call_count = 2

        # This test focuses on fragment combination, so no schema initially.
        initial_prompt_kwargs = {
            "system": "System prompt",
            "fragments": [  # String list
                "User prompt part 1",
                "User prompt part 2",
            ],
        }

        mock_get_tokens.return_value = (10, 30)  # For the successful attempt

        all_attempt_latencies_ms: list[float] = []

        response_obj, attempt_count = (
            adapter_instance._handle_prompt_execution_with_adaptation(
                model=mock_model_obj,
                initial_prompt_kwargs=initial_prompt_kwargs,  # Use the corrected kwargs
                max_attempts=3,
                all_attempt_latencies_ms_ref=all_attempt_latencies_ms,
            )
        )

        assert await response_obj.text() == "Success after combining fragments"
        assert attempt_count == expected_attempt_count
        assert mock_execute_single.call_count == expected_call_count

        # Verify second call to _execute_single_prompt_attempt had fragments combined
        second_call_args = mock_execute_single.call_args_list[1]
        # The model is the first positional argument after self
        assert second_call_args[0][0] is mock_model_obj
        # Prompt kwargs is the second positional argument
        prompt_kwargs_in_second_call = second_call_args[0][1]
        assert "fragments" not in prompt_kwargs_in_second_call
        assert "system" not in prompt_kwargs_in_second_call
        assert (
            prompt_kwargs_in_second_call["prompt"]
            == "System prompt\n\nUser prompt part 1\n\nUser prompt part 2"
        )

        mock_logger_warning.assert_called_once()
        args, _ = mock_logger_warning.call_args
        assert (
            "Model %s raised AttributeError on attempt %d: %s. Adapting..." in args[0]
        )
        assert args[1] == mock_model_obj.model_id
        assert args[2] == 1  # Attempt number

        mock_logger_info.assert_any_call(
            "Attempting to adapt by combining 'system' and 'fragments' into 'prompt' "
            f"for model {mock_model_obj.model_id}."
        )
        assert len(all_attempt_latencies_ms) == expected_attempt_count

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
            f"Attempting to adapt by removing 'schema' for model {mock_model.model_id}."
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
    async def test_execute_success_path(
        self,
        mock_logger_info: MagicMock,
        mock_handle_execution: MagicMock,
        mock_get_tokens: MagicMock,
        adapter_instance: LLMModelAdapter,
    ) -> None:
        """Test the successful execution path of the main execute method."""
        mock_model = MagicMock()
        mock_model.model_id = "test-execute-success"

        mock_response_obj = MagicMock()
        # Mock async methods on the MagicMock spec instance
        mock_response_obj.text = AsyncMock(return_value="Successful response text")
        mock_response_obj.json = AsyncMock(
            return_value={"key": "value"}
        )  # Example json response
        mock_response_obj.usage = AsyncMock(
            return_value=cast(LLMUsage, {"input": 10, "output": 20, "details": None})
        )

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
        mock_get_tokens.return_value = (10, 20)

        system_frags = SystemFragments([Fragment("System prompt")])
        user_frags = UserFragments([Fragment("User prompt")])

        # Call execute
        response_text, metrics = await adapter_instance.execute(
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
            f"LLM call to model {mock_model.model_id} completed. "
            "Primary Latency (text_extraction): "
            f"{metrics.latency_ms:.2f} ms, llm_lib_latency: "
            f"{llm_lib_latency_for_log:.2f} ms, Total Duration: "
            f"{metrics.total_processing_duration_ms:.2f} ms, "
            f"Tokens In: {metrics.token_input}, Tokens Out: {metrics.token_output}",
        )


def test_model_response_protocol_runtime_check() -> None:
    class DummyResponse:
        def text(self) -> str:
            return "foo"


class TestModelValidation:
    """Tests for model validation functionality."""

    def setup_method(self) -> None:
        """Setup for each test."""
        self.adapter = LLMModelAdapter()

    def test_validate_model_name_valid(self) -> None:
        """Test validation of valid model names."""
        # Mock the helper function to return valid
        with patch(
            "vibectl.model_adapter.is_valid_llm_model_name", return_value=(True, None)
        ):
            result = self.adapter.validate_model_name("gpt-4")
            assert result is None

    def test_validate_model_name_invalid(self) -> None:
        """Test validation of invalid model names."""
        # Mock the helper function to return invalid
        with patch(
            "vibectl.model_adapter.is_valid_llm_model_name",
            return_value=(False, "Invalid model"),
        ):
            result = self.adapter.validate_model_name("invalid-model")
            assert result == "Invalid model"

    def test_validate_model_key_unknown_provider(self) -> None:
        """Test model key validation for unknown provider."""
        with patch.object(
            self.adapter, "_determine_provider_from_model", return_value=None
        ):
            result = self.adapter.validate_model_key("unknown-model")
            assert result is not None
            assert "Unknown model provider" in result

    def test_validate_model_key_ollama_provider(self) -> None:
        """Test model key validation for ollama provider."""
        with patch.object(
            self.adapter, "_determine_provider_from_model", return_value="ollama"
        ):
            result = self.adapter.validate_model_key("llama2")
            assert result is None  # Ollama doesn't need key validation

    def test_validate_model_key_missing_key(self) -> None:
        """Test model key validation when no key is configured."""
        mock_config = Mock()
        mock_config.get_model_key.return_value = None
        self.adapter.config = mock_config

        with patch.object(
            self.adapter, "_determine_provider_from_model", return_value="openai"
        ):
            result = self.adapter.validate_model_key("gpt-4")
            assert result is not None
            assert "No API key found" in result
            assert "export VIBECTL_OPENAI_API_KEY" in result

    def test_validate_model_key_invalid_anthropic_format(self) -> None:
        """Test anthropic key format validation."""
        mock_config = Mock()
        mock_config.get_model_key.return_value = (
            "invalid-anthropic-key-that-is-long-enough"
        )
        self.adapter.config = mock_config

        with patch.object(
            self.adapter, "_determine_provider_from_model", return_value="anthropic"
        ):
            result = self.adapter.validate_model_key("claude-3")
            assert result is not None
            assert "Anthropic API key format looks invalid" in result

    def test_validate_model_key_invalid_openai_format(self) -> None:
        """Test openai key format validation."""
        mock_config = Mock()
        mock_config.get_model_key.return_value = (
            "invalid-openai-key-that-is-long-enough"
        )
        self.adapter.config = mock_config

        with patch.object(
            self.adapter, "_determine_provider_from_model", return_value="openai"
        ):
            result = self.adapter.validate_model_key("gpt-4")
            assert result is not None
            assert "Openai API key format looks invalid" in result

    def test_validate_model_key_valid_key_format(self) -> None:
        """Test valid key format passes validation."""
        mock_config = Mock()
        mock_config.get_model_key.return_value = "sk-valid-key-format"
        self.adapter.config = mock_config

        with patch.object(
            self.adapter, "_determine_provider_from_model", return_value="openai"
        ):
            result = self.adapter.validate_model_key("gpt-4")
            assert result is None

    def test_validate_model_key_short_key_passes(self) -> None:
        """Test short keys pass validation regardless of format."""
        mock_config = Mock()
        mock_config.get_model_key.return_value = "short"  # Less than 20 chars
        self.adapter.config = mock_config

        with patch.object(
            self.adapter, "_determine_provider_from_model", return_value="openai"
        ):
            result = self.adapter.validate_model_key("gpt-4")
            assert result is None

    def test_format_api_key_message_error(self) -> None:
        """Test formatting API key error message."""
        result = self.adapter._format_api_key_message("openai", "gpt-4", is_error=True)
        assert "Failed to get model 'gpt-4'" in result
        assert "export VIBECTL_OPENAI_API_KEY" in result
        assert "VIBECTL_OPENAI_API_KEY_FILE" in result

    def test_format_api_key_message_warning(self) -> None:
        """Test formatting API key warning message."""
        result = self.adapter._format_api_key_message(
            "anthropic", "claude-3", is_error=False
        )
        assert "Warning: No API key found" in result
        assert "export VIBECTL_ANTHROPIC_API_KEY" in result

    def test_format_key_validation_message(self) -> None:
        """Test formatting key validation message."""
        result = self.adapter._format_key_validation_message("openai")
        assert "Openai API key format looks invalid" in result
        assert "typically start with 'sk-'" in result


class TestSyncLLMResponseAdapterErrors:
    """Tests for error handling in SyncLLMResponseAdapter."""

    def test_json_parse_error(self) -> None:
        """Test JSON parsing error handling."""
        mock_response = Mock()
        mock_response.text.return_value = "invalid json content"

        adapter = SyncLLMResponseAdapter(mock_response)

        with pytest.raises(LLMResponseParseError) as exc_info:
            asyncio.run(adapter.json())

        assert "Failed to parse response as JSON" in str(exc_info.value)
        assert exc_info.value.original_text == "invalid json content"

    def test_usage_callable_error(self) -> None:
        """Test error handling when usage() method call fails."""
        mock_response = Mock()
        mock_response.usage = Mock(side_effect=Exception("Usage call failed"))
        mock_response.model.model_id = "test-model"

        adapter = SyncLLMResponseAdapter(mock_response)

        result = asyncio.run(adapter.usage())
        result_dict = cast(dict, result)
        assert result_dict["input"] == 0
        assert result_dict["output"] == 0
        assert "error_calling_usage_method" in result_dict["details"]

    def test_usage_unrecognized_format(self) -> None:
        """Test usage with unrecognized format."""
        mock_response = Mock()
        mock_response.usage = "unrecognized_format"
        mock_response.model.model_id = "test-model"

        adapter = SyncLLMResponseAdapter(mock_response)

        result = asyncio.run(adapter.usage())
        result_dict = cast(dict, result)
        assert result_dict["input"] == 0
        assert result_dict["output"] == 0
        assert result_dict["details"] == "unrecognized_format"

    def test_usage_object_with_invalid_attrs(self) -> None:
        """Test usage object with input/output attrs that can't be cast to int."""
        mock_usage = Mock()
        mock_usage.input = "not_a_number"
        mock_usage.output = "also_not_a_number"

        mock_response = Mock()
        mock_response.usage = mock_usage
        mock_response.model.model_id = "test-model"

        adapter = SyncLLMResponseAdapter(mock_response)

        result = asyncio.run(adapter.usage())
        result_dict = cast(dict, result)
        assert result_dict["input"] == 0
        assert result_dict["output"] == 0

    def test_usage_model_name_extraction_error(self) -> None:
        """Test error handling in model name extraction for logging."""
        mock_response = Mock()
        mock_response.usage = {"prompt_tokens": 10, "completion_tokens": 20}
        # Mock model with problematic attribute access
        mock_response.model = Mock()
        mock_response.model.model_id = Mock(side_effect=Exception("Model access error"))

        adapter = SyncLLMResponseAdapter(mock_response)

        result = asyncio.run(adapter.usage())
        result_dict = cast(dict, result)
        assert result_dict["input"] == 10
        assert result_dict["output"] == 20

    def test_properties_with_none_response(self) -> None:
        """Test property accessors with None response."""
        mock_response = Mock()
        del mock_response.id  # Remove attribute
        del mock_response.created
        del mock_response.response_ms
        mock_response.model = Mock()
        del mock_response.model.id

        adapter = SyncLLMResponseAdapter(mock_response)

        assert adapter.id is None
        assert adapter.model is None
        assert adapter.created is None
        assert adapter.response_ms is None


class TestModelAdapterEdgeCases:
    """Tests for edge cases and error paths in ModelAdapter."""

    def setup_method(self) -> None:
        """Setup for each test."""
        self.adapter = LLMModelAdapter()

    @patch("vibectl.model_adapter.ModelEnvironment")
    async def test_stream_execute_type_error_with_recovery_keywords(
        self, mock_env: MagicMock
    ) -> None:
        """Test stream execute with TypeError containing recoverable keywords."""
        mock_model = Mock()
        mock_model.model_id = "test-model"
        mock_model.prompt.side_effect = Exception("rate limit exceeded")

        system_fragments = SystemFragments([])
        user_fragments = UserFragments([Fragment("test")])

        with pytest.raises(RecoverableApiError):
            async for _ in self.adapter.stream_execute(
                mock_model, system_fragments, user_fragments
            ):
                pass

    @patch("vibectl.model_adapter.ModelEnvironment")
    async def test_stream_execute_general_exception(self, mock_env: MagicMock) -> None:
        """Test stream execute with general exception."""
        mock_model = Mock()
        mock_model.model_id = "test-model"
        mock_model.prompt.side_effect = Exception("general error")

        system_fragments = SystemFragments([])
        user_fragments = UserFragments([Fragment("test")])

        with pytest.raises(ValueError, match="LLM Streaming Execution Error"):
            async for _ in self.adapter.stream_execute(
                mock_model, system_fragments, user_fragments
            ):
                pass

    async def test_execute_and_log_metrics_exception_handling(self) -> None:
        """Test exception handling in execute_and_log_metrics wrapper."""
        mock_model = Mock()
        system_fragments = SystemFragments([])
        user_fragments = UserFragments([Fragment("test")])

        # Mock execute to raise an exception
        with (
            patch.object(self.adapter, "execute", side_effect=Exception("test error")),
            pytest.raises(Exception, match="test error"),
        ):
            await self.adapter.execute_and_log_metrics(
                mock_model, system_fragments, user_fragments
            )
