"""
Model adapter interface for vibectl.

This module provides an abstraction layer for interacting with LLM models,
making it easier to switch between model providers and handle model-specific
configuration. It uses an adapter pattern to isolate the rest of the application
from the details of model interaction.
"""

import json
import os
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import ExitStack
from typing import (
    Any,
    Generic,
    TypeVar,
    cast,
)

import llm
from llm.models import Response as LLMResponseObject  # type: ignore[import-untyped]
from pydantic import BaseModel

from .config import Config

# Import the new validation function
from .llm_interface import is_valid_llm_model_name
from .logutil import logger

# Import the consolidated keywords and custom exception
from .types import (
    RECOVERABLE_API_ERROR_KEYWORDS,
    LLMMetrics,
    LLMUsage,
    ModelResponse,
    RecoverableApiError,
    SystemFragments,
    UserFragments,
)


# NEW TimedOperation Context Manager
class TimedOperation:
    """Context manager to time an operation and log its duration."""

    def __init__(self, logger_instance: Any, identifier: str, operation_name: str):
        self.logger = logger_instance
        self.identifier = identifier
        self.operation_name = operation_name
        self.start_time: float = 0.0
        self.duration_ms: float = 0.0

    def __enter__(self) -> "TimedOperation":
        self.start_time = time.monotonic()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        end_time = time.monotonic()
        self.duration_ms = (end_time - self.start_time) * 1000
        self.logger.info(
            "%s for %s took: %.2f ms",
            self.operation_name,
            self.identifier,
            self.duration_ms,
        )


# Custom Exception for Adaptation Failures
class LLMAdaptationError(ValueError):
    """Custom exception for when LLM adaptation strategies are exhausted."""

    def __init__(
        self,
        message: str,
        final_attempt_count: int,
        all_attempt_latencies_ms: list[float],
        *args: Any,
    ) -> None:
        super().__init__(message, *args)
        self.final_attempt_count = final_attempt_count
        self.all_attempt_latencies_ms = all_attempt_latencies_ms


# Define T here if it's not already defined or imported globally in this file
T = TypeVar("T")


# Custom Exception for JSON parsing issues in the adapter
class LLMResponseParseError(Exception):
    def __init__(self, message: str, original_text: str | None = None):
        super().__init__(message)
        self.original_text = original_text


class SyncLLMResponseAdapter(ModelResponse):
    """
    Adapts a synchronous llm.Response object to conform to the
    asynchronous ModelResponse protocol.
    """

    def __init__(self, sync_response: LLMResponseObject):
        self._sync_response: LLMResponseObject = sync_response

    async def text(self) -> str:
        return str(self._sync_response.text())

    async def json(self) -> dict[str, Any]:
        try:
            loaded_json = json.loads(self._sync_response.text())
            return cast(dict[str, Any], loaded_json)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response text as JSON: {e}")
            raise LLMResponseParseError(
                "Failed to parse response as JSON",
                original_text=self._sync_response.text(),
            ) from e

    async def usage(self) -> LLMUsage:
        logger.debug(
            "[SyncLLMResponseAdapter.usage] Entered. Type of self._sync_response: %s",
            type(self._sync_response),
        )
        potential_usage_attr = getattr(self._sync_response, "usage", None)
        logger.debug(
            "[SyncLLMResponseAdapter.usage] potential_usage_attr from "
            f"getattr(self._sync_response, 'usage', None): {potential_usage_attr} "
            f"(Is callable: {callable(potential_usage_attr)})"
        )
        actual_usage_data = None

        model_name_for_log = "unknown_model_in_usage_method"
        try:
            if self._sync_response and hasattr(self._sync_response, "model"):
                model_obj = getattr(self._sync_response, "model", None)
                if model_obj and hasattr(model_obj, "model_id"):
                    model_name_for_log = str(
                        getattr(model_obj, "model_id", "unknown_model_id_attr")
                    )
                elif model_obj and hasattr(
                    model_obj, "id"
                ):  # Fallback for some model objects
                    model_name_for_log = str(
                        getattr(model_obj, "id", "unknown_id_attr")
                    )
                elif hasattr(
                    self._sync_response, "model_id"
                ):  # If model_id is directly on response
                    model_name_for_log = str(
                        getattr(
                            self._sync_response,
                            "model_id",
                            "unknown_direct_model_id_attr",
                        )
                    )
        except Exception as e:
            logger.debug(
                f"Error retrieving model name for logging in usage method: {e}"
            )

        if callable(potential_usage_attr):
            try:
                actual_usage_data = potential_usage_attr()
            except Exception as e:
                logger.warning(
                    f"Error calling .usage() method on LLM response for model "
                    f"'{model_name_for_log}': {e}"
                )
                return cast(
                    LLMUsage,
                    {
                        "input": 0,
                        "output": 0,
                        "details": {"error_calling_usage_method": str(e)},
                    },
                )
        else:
            actual_usage_data = potential_usage_attr

        if isinstance(actual_usage_data, dict):
            # Read from the llm library's expected keys
            llm_prompt_tokens = int(actual_usage_data.get("prompt_tokens", 0))
            llm_completion_tokens = int(actual_usage_data.get("completion_tokens", 0))
            # Return our LLMUsage TypedDict format
            return cast(
                LLMUsage,
                {
                    "input": llm_prompt_tokens,  # Map to "input"
                    "output": llm_completion_tokens,  # Map to "output"
                    "details": actual_usage_data,  # Store original dict
                },
            )
        elif hasattr(actual_usage_data, "input") and hasattr(
            actual_usage_data, "output"
        ):
            try:
                prompt_tokens = int(getattr(actual_usage_data, "input", 0))
                completion_tokens = int(getattr(actual_usage_data, "output", 0))
                # Store the original object in details if it's not a dict
                details_to_store = (
                    actual_usage_data  # actual_usage_data is an object here
                )
                return cast(
                    LLMUsage,
                    {
                        "input": prompt_tokens,
                        "output": completion_tokens,
                        "details": details_to_store,
                    },
                )
            except (TypeError, ValueError) as e:
                logger.warning(
                    f"Model '{model_name_for_log}' provided usage attributes "
                    "'input'/'output' that could not be cast to int. "
                    f"Type: {type(actual_usage_data)}, Error: {e}"
                )
        elif (
            actual_usage_data is not None
        ):  # It exists, was resolved, but not a dict and no input/output attrs
            logger.warning(
                f"Model '{model_name_for_log}' provided 'usage' data in an "
                f"unrecognized format. Type: {type(actual_usage_data)}, "
                f"Value: {str(actual_usage_data)[:100]}"
            )
        logger.debug(
            "[SyncLLMResponseAdapter.usage] Exiting. Defaulting to 0 tokens if not "
            "properly parsed."
        )
        # Ensure LLMUsage is returned, even if tokens are 0
        return cast(
            LLMUsage,
            {
                "input": 0,
                "output": 0,
                "details": actual_usage_data if actual_usage_data is not None else {},
            },
        )

    @property
    def id(self) -> str | None:
        return getattr(self._sync_response, "id", None)

    @property
    def model(self) -> str | None:
        return getattr(self._sync_response.model, "id", None)

    @property
    def created(self) -> int | None:
        return getattr(self._sync_response, "created", None)

    @property
    def response_ms(self) -> int | None:
        return getattr(self._sync_response, "response_ms", None)

    def __aiter__(self) -> AsyncIterator[str]:
        async def empty_iterator() -> AsyncIterator[str]:
            if False:  # pragma: no cover
                yield ""  # pragma: no cover

        return empty_iterator()

    async def on_done(
        self, callback: Callable[["ModelResponse"], Awaitable[None]]
    ) -> None:
        logger.debug(
            "on_done called on SyncLLMResponseAdapter; typically for streaming."
        )
        # For a non-streaming response, this is a no-op or could call
        # callback immediately.
        # However, to prevent complex logic for a non-streaming path, we keep it simple.
        # If immediate callback execution is desired:
        # await callback(self)
        pass


class ModelAdapter(ABC, Generic[T]):
    """Abstract base class for model adapters.

    This defines the interface that all model adapters must implement.
    """

    @abstractmethod
    def get_model(self, model_name: str) -> Any:
        """Get a model instance by name.

        Args:
            model_name: The name of the model to get

        Returns:
            Any: The model instance
        """
        pass

    @abstractmethod
    async def execute(
        self,
        model: Any,
        system_fragments: SystemFragments,
        user_fragments: UserFragments,
        response_model: type[BaseModel] | None = None,
    ) -> tuple[str, LLMMetrics | None]:
        """Execute a prompt on the model and get a response.

        Args:
            model: The model instance to execute the prompt on
            system_fragments: List of system prompt fragments.
            user_fragments: List of user prompt fragments.
            response_model: Optional Pydantic model for structured JSON response.

        Returns:
            tuple[str, LLMMetrics | None]: A tuple containing the response text
                                           and the metrics for the call.
        """
        pass

    @abstractmethod
    async def execute_and_log_metrics(
        self,
        model: Any,
        system_fragments: SystemFragments,
        user_fragments: UserFragments,
        response_model: type[BaseModel] | None = None,
    ) -> tuple[str, LLMMetrics | None]:
        """Wraps execute, logs metrics, returns response text and metrics."""
        pass

    @abstractmethod
    def validate_model_key(self, model_name: str) -> str | None:
        """Validate the API key for a model.

        Args:
            model_name: The name of the model to validate

        Returns:
            Optional warning message if there are potential issues, None otherwise
        """
        pass

    @abstractmethod
    def validate_model_name(self, model_name: str) -> str | None:
        """Validate the model name against the underlying provider/library.

        Args:
            model_name: The name of the model to validate.

        Returns:
            Optional error message string if validation fails, None otherwise.
        """
        pass

    @abstractmethod
    async def stream_execute(
        self,
        model: Any,
        system_fragments: SystemFragments,
        user_fragments: UserFragments,
        response_model: type[BaseModel] | None = None,
    ) -> AsyncIterator[str]:
        """Execute a prompt on the model and stream the response.

        Args:
            model: The model instance to execute the prompt on
            system_fragments: List of system prompt fragments.
            user_fragments: List of user prompt fragments.
            response_model: Optional Pydantic model for structured JSON response
                            (ignored for streaming).

        Yields:
            str: Chunks of the response text.

        Raises:
            RecoverableApiError: If a potentially recoverable API error occurs.
            ValueError: If another error occurs during execution.
        """
        # This is an abstract method, so it needs a body that "yields" something
        # to satisfy type checker in concrete implementations that use `async for`
        # over this, even if it's just a placeholder here. An empty generator is
        # fine for an abstract method.
        if False:
            yield ""

    @abstractmethod
    async def stream_execute_and_log_metrics(
        self,
        model: Any,
        system_fragments: SystemFragments,
        user_fragments: UserFragments,
        response_model: type[BaseModel] | None = None,
    ) -> tuple[AsyncIterator[str], "StreamingMetricsCollector"]:
        """Execute a prompt on the model and stream the response with metrics.

        Args:
            model: The model instance to execute the prompt on
            system_fragments: List of system prompt fragments.
            user_fragments: List of user prompt fragments.
            response_model: Optional Pydantic model (ignored for streaming).

        Returns:
            tuple[AsyncIterator[str], StreamingMetricsCollector]:
                A tuple containing the async iterator
                for response chunks and metrics collector.
        """
        pass


class ModelEnvironment:
    """Context manager for handling model-specific environment variables.

    This class provides a safer way to temporarily set environment variables
    for model execution, ensuring they are properly restored even in case of
    exceptions.
    """

    def __init__(self, model_name: str, config: Config):
        """Initialize the context manager.

        Args:
            model_name: The name of the model
            config: Configuration object for accessing API keys
        """
        self.model_name = model_name
        self.config = config
        self.original_env: dict[str, str] = {}
        self.provider = self._determine_provider_from_model(model_name)

    def _determine_provider_from_model(self, model_name: str) -> str | None:
        """Determine the provider from the model name.

        Args:
            model_name: The model name

        Returns:
            The provider name (openai, anthropic, ollama) or None if unknown
        """
        name_lower = model_name.lower()
        if name_lower.startswith("gpt-"):
            return "openai"
        elif name_lower.startswith("anthropic/") or "claude-" in name_lower:
            return "anthropic"
        elif "ollama" in name_lower and ":" in name_lower:
            return "ollama"
        # Default to None if we can't determine the provider
        return None

    def __enter__(self) -> None:
        """Set up the environment for model execution."""
        if not self.provider:
            return

        # Get the standard environment variable name for this provider
        legacy_key_name = ""
        if self.provider == "openai":
            legacy_key_name = "OPENAI_API_KEY"
        elif self.provider == "anthropic":
            legacy_key_name = "ANTHROPIC_API_KEY"
        elif self.provider == "ollama":
            legacy_key_name = "OLLAMA_API_KEY"

        if not legacy_key_name:
            return

        # Save original value if it exists
        if legacy_key_name in os.environ:
            self.original_env[legacy_key_name] = os.environ[legacy_key_name]

        # Get the API key for this provider
        api_key = self.config.get_model_key(self.provider)

        # Only set the environment variable if an API key exists
        # AND the provider is NOT ollama (ollama often runs locally without keys)
        if api_key and self.provider != "ollama":
            # Set the environment variable for the LLM package to use
            os.environ[legacy_key_name] = api_key

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Restore the original environment after model execution."""
        for key, value in self.original_env.items():
            os.environ[key] = value

        # Also remove keys we added but weren't originally present
        # Check for the standard environment variable names
        legacy_keys = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OLLAMA_API_KEY"]
        for key in legacy_keys:
            if key not in self.original_env and key in os.environ:
                del os.environ[key]


class StreamingMetricsCollector:
    """Helper class to collect metrics from a streaming operation."""

    def __init__(self) -> None:
        self._completed: bool = False
        self._metrics: LLMMetrics | None = None

    def _mark_completed(self, metrics: LLMMetrics) -> None:
        """Internal method to mark streaming as completed with metrics."""
        self._completed = True
        self._metrics = metrics

    async def get_metrics(self) -> LLMMetrics | None:
        """Get the final metrics. This should be called after the stream is consumed."""
        if not self._completed:
            # If streaming hasn't completed yet, return None
            # This can happen if get_metrics is called before the stream
            # is fully consumed
            return None
        return self._metrics

    @property
    def is_completed(self) -> bool:
        """Check if the streaming operation has completed."""
        return self._completed


class LLMModelAdapter(ModelAdapter):
    """Adapter for the LLM package models.

    This adapter wraps the LLM package to provide a consistent interface
    for model interaction.
    """

    def __init__(self, config: Config | None = None) -> None:
        """Initialize the LLM model adapter.

        Args:
            config: Optional Config instance. If not provided, creates a new one.
        """
        self.config = config or Config()
        self._model_cache: dict[str, Any] = {}
        logger.debug("LLMModelAdapter initialized with config: %s", self.config)

    def _determine_provider_from_model(self, model_name: str) -> str | None:
        """Determine the provider from the model name.

        Args:
            model_name: The model name

        Returns:
            The provider name (openai, anthropic, ollama) or None if unknown
        """
        name_lower = model_name.lower()
        if name_lower.startswith("gpt-"):
            return "openai"
        elif name_lower.startswith("anthropic/") or "claude-" in name_lower:
            return "anthropic"
        elif "ollama" in name_lower and ":" in name_lower:
            return "ollama"
        # Default to None if we can't determine the provider
        return None

    async def _get_token_usage(
        self, response: ModelResponse, model_id: str
    ) -> tuple[int, int]:
        """Safely extracts token usage from a model response.

        Args:
            response: The model response object.
            model_id: The ID of the model, for logging purposes.

        Returns:
            A tuple containing (token_input, token_output).
        """
        logger.debug(
            "[_get_token_usage] Entered. Type of received 'response' "
            f"object: {type(response)}, model_id: {model_id}"
        )
        token_input = 0
        token_output = 0
        try:
            # Await the async usage() method
            logger.debug("[_get_token_usage] Attempting to call await response.usage()")
            usage_data_maybe_none = await response.usage()
            logger.debug(
                "[_get_token_usage] Result from await response.usage(): %s",
                usage_data_maybe_none,
            )
            if usage_data_maybe_none:
                # We've confirmed it's not None, so it's LLMUsage (a TypedDict)
                usage_obj = cast(LLMUsage, usage_data_maybe_none)
                logger.debug(
                    "Raw LLM usage object for model %s: %s", model_id, usage_obj
                )

                raw_input = cast(dict, usage_obj).get("input")
                raw_output = cast(dict, usage_obj).get("output")

                try:
                    token_input = int(raw_input) if raw_input is not None else 0
                except (TypeError, ValueError):
                    token_input = 0
                try:
                    token_output = int(raw_output) if raw_output is not None else 0
                except (TypeError, ValueError):
                    token_output = 0
            logger.debug(
                f"[_get_token_usage] Successfully processed usage. "
                f"Input: {token_input}, Output: {token_output}"
            )
        except (
            AttributeError
        ) as e:  # Add specific logging for the caught AttributeError
            logger.warning(
                f"[_get_token_usage] Caught AttributeError: {e}. This is likely "
                "why 'lacks usage() method' is reported.",
                exc_info=True,
            )
            logger.warning(
                f"Model {model_id} response lacks usage() method for token counting."
            )
        except Exception as usage_err:
            logger.warning(
                f"Failed to get token usage for model {model_id}: {usage_err}"
            )
        return token_input, token_output

    def _execute_single_prompt_attempt(
        self, model: Any, prompt_kwargs: dict[str, Any]
    ) -> ModelResponse:
        """Executes single prompt attempt and returns raw response wrapped for async."""
        prompt_kwargs_to_use = prompt_kwargs.copy()

        logger.debug(
            f"Executing single prompt attempt with kwargs: {prompt_kwargs_to_use}"
        )
        try:
            # Directly call the model's prompt method
            llm_response: LLMResponseObject = model.prompt(**prompt_kwargs_to_use)

            # Log the raw response type for debugging
            logger.debug(
                "Raw response type from model.prompt() in "
                f"_execute_single_prompt_attempt: {type(llm_response)}"
            )
            # Wrap the synchronous llm.Response in SyncLLMResponseAdapter
            # to conform to the ModelResponse protocol (async text(), json(), usage())
            return SyncLLMResponseAdapter(llm_response)

        except Exception as e:
            # Log the exception details before re-raising or wrapping
            logger.error(
                "Error during model.prompt() call in "
                f"_execute_single_prompt_attempt: {e}",
                exc_info=True,
            )
            # Determine if this is a RecoverableApiError based on keywords
            error_message = str(e).lower()
            if any(
                keyword in error_message for keyword in RECOVERABLE_API_ERROR_KEYWORDS
            ):
                raise RecoverableApiError(
                    f"Recoverable API error in _execute_single_prompt_attempt: {e}"
                ) from e
            # For other errors, re-raise them to be handled by the caller
            raise  # Re-raise the original exception to preserve its type and traceback

    def _handle_prompt_execution_with_adaptation(
        self,
        model: Any,
        initial_prompt_kwargs: dict[str, Any],
        max_attempts: int,
        all_attempt_latencies_ms_ref: list[float],
    ) -> tuple[ModelResponse, int]:
        """
        Handles LLM prompt execution with adaptive retries for AttributeError.

        Tries to adapt to common AttributeErrors like schema or fragment issues.
        Other exceptions from the LLM call are re-raised immediately.

        Args:
            model: The model instance.
            initial_prompt_kwargs: Initial keyword arguments for the prompt.
            max_attempts: Maximum number of attempts.
            all_attempt_latencies_ms_ref: List to append latencies of each attempt

        Returns:
            A tuple: (ModelResponse, successful_attempt_number).

        Raises:
            LLMAdaptationError: If all adaptation attempts for AttributeError fail.
            Any other Exception from model.prompt() if not an AttributeError.
        """
        current_kwargs = initial_prompt_kwargs.copy()
        schema_adaptation_done = False
        fragments_adaptation_done = False

        for attempt_num in range(1, max_attempts + 1):
            start_attempt_time = time.monotonic()
            try:
                response_obj = self._execute_single_prompt_attempt(
                    model, current_kwargs
                )
                end_attempt_time = time.monotonic()
                current_llm_lib_latency_ms = (
                    end_attempt_time - start_attempt_time
                ) * 1000
                all_attempt_latencies_ms_ref.append(current_llm_lib_latency_ms)

                logger.info(
                    "LLM library call for model %s succeeded on attempt %d "
                    "(llm_lib_latency: %.2f ms).",
                    model.model_id,
                    attempt_num,
                    current_llm_lib_latency_ms,
                )
                return response_obj, attempt_num
            except AttributeError as attr_err:
                end_attempt_time = time.monotonic()
                all_attempt_latencies_ms_ref.append(
                    (end_attempt_time - start_attempt_time) * 1000
                )
                err_str = str(attr_err).lower()
                logger.warning(
                    "Model %s raised AttributeError on attempt %d: %s. Adapting...",
                    model.model_id,
                    attempt_num,
                    attr_err,
                )

                adapted = False
                if (
                    "schema" in err_str
                    and "schema" in current_kwargs
                    and not schema_adaptation_done
                ):
                    logger.info(
                        "Attempting to adapt by removing 'schema' for model "
                        f"{model.model_id}."
                    )
                    current_kwargs.pop("schema")
                    schema_adaptation_done = True
                    adapted = True
                elif (
                    ("fragments" in err_str or "system" in err_str)
                    and ("fragments" in current_kwargs or "system" in current_kwargs)
                    and not fragments_adaptation_done
                ):
                    logger.info(
                        "Attempting to adapt by combining 'system' and 'fragments' "
                        f"into 'prompt' for model {model.model_id}."
                    )
                    system_prompt_parts = []
                    if "system" in current_kwargs:
                        system_val = current_kwargs.pop("system")
                        if isinstance(system_val, str):
                            system_prompt_parts.append(system_val)
                        elif isinstance(system_val, list):  # Should be SystemFragments
                            system_prompt_parts.extend(system_val)

                    user_fragments_parts = []
                    if "fragments" in current_kwargs:
                        fragments_val = current_kwargs.pop("fragments")
                        if isinstance(fragments_val, list):  # Should be UserFragments
                            user_fragments_parts.extend(fragments_val)

                    full_prompt_parts = system_prompt_parts + user_fragments_parts
                    current_kwargs["prompt"] = "\n\n".join(
                        str(p) for p in full_prompt_parts
                    )
                    fragments_adaptation_done = True
                    adapted = True

                if adapted and attempt_num < max_attempts:
                    logger.info(
                        f"Adaptation applied for model {model.model_id}. "
                        f"Proceeding to attempt {attempt_num + 1}."
                    )
                    continue  # To the next iteration of the loop
                else:
                    # Either no adaptation was made for this AttributeError,
                    # or it was the last attempt.
                    final_msg = (
                        f"Failed for model {model.model_id} due to persistent "
                        f"AttributeError after {attempt_num} attempts and "
                        f"exhausting adaptation strategies. Last error: {attr_err}"
                    )
                    logger.error(final_msg)
                    raise LLMAdaptationError(
                        final_msg, attempt_num, list(all_attempt_latencies_ms_ref)
                    ) from attr_err
            except Exception as e:  # Non-AttributeError from LLM call
                end_attempt_time = time.monotonic()
                all_attempt_latencies_ms_ref.append(
                    (end_attempt_time - start_attempt_time) * 1000
                )
                logger.warning(
                    f"LLM call to model {model.model_id} failed on attempt "
                    f"{attempt_num} with non-AttributeError: {e}"
                )
                raise  # Re-raise for the main execute handler

        # Logically, the loop should always exit via a return or raise.
        # This assertion is to satisfy linters and as a failsafe.
        raise AssertionError(
            "Reached end of _handle_prompt_execution_with_adaptation for "
            f"{model.model_id}, which should be unreachable."
        )

    def get_model(self, model_name: str) -> Any:
        """Get an LLM model instance by name, with caching.

        Args:
            model_name: The name of the model to get

        Returns:
            Any: The model instance

        Raises:
            ValueError: If the model cannot be loaded or API key is missing
        """
        # Check cache first
        if model_name in self._model_cache:
            logger.debug("Model '%s' found in cache", model_name)
            return self._model_cache[model_name]

        logger.info("Loading model '%s'", model_name)
        # Use context manager for environment variable handling
        with ModelEnvironment(model_name, self.config):
            try:
                # Get model from LLM package
                model = llm.get_model(model_name)
                self._model_cache[model_name] = model
                logger.info("Model '%s' loaded and cached", model_name)
                return model
            except Exception as e:
                provider = self._determine_provider_from_model(model_name)

                # Check if error might be due to missing API key
                if provider and not self.config.get_model_key(provider):
                    error_msg = self._format_api_key_message(
                        provider, model_name, is_error=True
                    )
                    logger.error(
                        "API key missing for provider '%s' (model '%s'): %s",
                        provider,
                        model_name,
                        error_msg,
                    )
                    raise ValueError(error_msg) from e

                # Generic error message if not API key related
                logger.error(
                    "Failed to get model '%s': %s",
                    model_name,
                    e,
                    exc_info=True,
                )
                raise ValueError(f"Failed to get model '{model_name}': {e}") from e

    async def execute(
        self,
        model: Any,
        system_fragments: SystemFragments,
        user_fragments: UserFragments,
        response_model: type[BaseModel] | None = None,
    ) -> tuple[str, LLMMetrics | None]:
        """Execute a prompt using fragments on the LLM package model.

        Args:
            model: The model instance to execute the prompt on
            system_fragments: List of system prompt fragments
            user_fragments: List of user prompt fragments (passed as 'fragments')
            response_model: Optional Pydantic model for structured JSON response.

        Returns:
            tuple[str, LLMMetrics | None]: A tuple containing the response text
                                           and the metrics for the call.

        Raises:
            RecoverableApiError: If a potentially recoverable API error occurs.
            ValueError: If another error occurs during execution.
        """
        # Directly use the async logic without an inner _execute_async and asyncio.run
        overall_start_time = time.monotonic()
        current_total_processing_duration_ms: float | None = None
        metrics: LLMMetrics | None = None
        all_attempt_latencies_ms_list: list[float] = []
        num_attempts_final = 0
        max_adaptation_attempts = 3
        text_extraction_duration_ms = 0.0  # Initialize

        current_model_id_for_log = "Unknown"  # Initialize before try block
        try:
            current_model_id_for_log = getattr(model, "model_id", "Unknown")
            logger.debug(
                f"Executing call to model '{current_model_id_for_log}' "
                f"with response_model: {response_model is not None}"
            )

            with ExitStack() as stack:
                stack.enter_context(
                    TimedOperation(
                        logger,
                        current_model_id_for_log,
                        "Pre-LLM call setup (ModelEnv, args, schema)",
                    )
                )
                stack.enter_context(
                    ModelEnvironment(current_model_id_for_log, self.config)
                )

                initial_kwargs_for_model_prompt: dict[str, Any] = {}
                if system_fragments:
                    initial_kwargs_for_model_prompt["system"] = "\n\n".join(
                        system_fragments
                    )

                fragments_list: UserFragments = (
                    user_fragments if user_fragments else UserFragments([])
                )
                initial_kwargs_for_model_prompt["fragments"] = fragments_list

                if response_model:
                    schema_timer = stack.enter_context(
                        TimedOperation(
                            logger, current_model_id_for_log, "Schema generation"
                        )
                    )
                    try:
                        schema_dict: dict[str, Any] = response_model.model_json_schema()
                        initial_kwargs_for_model_prompt["schema"] = schema_dict
                        logger.debug(
                            f"Generated schema for model {current_model_id_for_log}: "
                            f"{schema_dict}"
                        )
                    except Exception as schema_exc:
                        logger.error(
                            f"Failed to generate schema for model "
                            f"{current_model_id_for_log}: {schema_exc}. "
                            f"Duration: {schema_timer.duration_ms} ms"
                        )

            (
                response_obj,
                success_attempt_num,
            ) = self._handle_prompt_execution_with_adaptation(
                model,
                initial_kwargs_for_model_prompt,
                max_adaptation_attempts,
                all_attempt_latencies_ms_list,
            )

            num_attempts_final = success_attempt_num
            llm_lib_latency_ms = all_attempt_latencies_ms_list[-1]

            with TimedOperation(
                logger, current_model_id_for_log, "response_obj.text() call"
            ) as text_timer:
                response_text = await response_obj.text()  # Ensure await here
            text_extraction_duration_ms = text_timer.duration_ms

            # If we have a response_model, we expect JSON, so try to log it.
            # Otherwise, log the plain text we already retrieved.
            if response_model:
                try:
                    json_to_log = await response_obj.json()
                    logger.debug(
                        f"Raw LLM response (expected JSON) for model "
                        f"{current_model_id_for_log}: {json_to_log}"
                    )
                except LLMResponseParseError:  # Or broader json.JSONDecodeError
                    logger.debug(
                        f"Raw LLM response (expected JSON, but failed to parse) for "
                        f"model {current_model_id_for_log}: {response_text}"
                    )
            else:
                logger.debug(
                    f"Raw LLM response (plain text) for model "
                    f"{current_model_id_for_log}: {response_text}"
                )

            with TimedOperation(
                logger, current_model_id_for_log, "_get_token_usage() call"
            ):
                token_input, token_output = await self._get_token_usage(
                    response_obj, current_model_id_for_log
                )

            overall_end_time = time.monotonic()
            current_total_processing_duration_ms = (
                overall_end_time - overall_start_time
            ) * 1000

            metrics = LLMMetrics(
                latency_ms=text_extraction_duration_ms,
                total_processing_duration_ms=current_total_processing_duration_ms,
                token_input=token_input,
                token_output=token_output,
                call_count=num_attempts_final,
            )
            logger.info(
                f"LLM call to model {current_model_id_for_log} completed. "
                "Primary Latency (text_extraction): "
                f"{text_extraction_duration_ms:.2f} ms, "
                f"llm_lib_latency: {llm_lib_latency_ms:.2f} ms, "
                f"Total Duration: {current_total_processing_duration_ms:.2f} ms, "
                f"Tokens In: {token_input}, "
                f"Tokens Out: {token_output}"
            )
            return response_text, metrics

        except LLMAdaptationError as lae:
            num_attempts_final = lae.final_attempt_count
            llm_lib_latency_ms = lae.all_attempt_latencies_ms[
                -1
            ]  # Latency of the last failed attempt by llm lib

            overall_end_time = time.monotonic()
            current_total_processing_duration_ms = (
                overall_end_time - overall_start_time
            ) * 1000

            logger.error(
                f"LLM call to model {current_model_id_for_log} failed after "
                f"{num_attempts_final} adaptation attempts. "
                f"Last llm_lib_latency: {llm_lib_latency_ms} ms, "
                f"Total Duration: {current_total_processing_duration_ms} ms. "
                f"Error: {lae.args[0]}"
            )

            metrics = LLMMetrics(
                latency_ms=0.0,
                total_processing_duration_ms=current_total_processing_duration_ms,
                token_input=0,
                token_output=0,
                call_count=num_attempts_final,
            )
            raise ValueError(
                f"LLM execution failed for model {current_model_id_for_log} after "
                f"{num_attempts_final} adaptation attempts: {lae.args[0]}"
            ) from lae

        except Exception as e:
            overall_end_time = time.monotonic()
            current_total_processing_duration_ms = (
                overall_end_time - overall_start_time
            ) * 1000

            if all_attempt_latencies_ms_list:
                num_attempts_final = len(all_attempt_latencies_ms_list)
                llm_lib_latency_ms_for_error = all_attempt_latencies_ms_list[-1]
            else:
                num_attempts_final = 1
                llm_lib_latency_ms_for_error = (
                    current_total_processing_duration_ms  # Best guess
                )

            # current_model_id_for_log might not be set if error occurred very early
            # Re-fetch if it's still "Unknown" and model object exists
            if current_model_id_for_log == "Unknown" and model:
                current_model_id_for_log = getattr(model, "model_id", "Unknown")

            error_str = str(e).lower()

            logger.warning(
                f"LLM call to model '{current_model_id_for_log}' failed. "
                f"Attempts (if adaptation stage): {num_attempts_final}. "
                f"Last/Relevant llm_lib_latency: {llm_lib_latency_ms_for_error} ms, "
                f"Total Duration: {current_total_processing_duration_ms} ms. "
                f"Error: {e}"
            )
            metrics = LLMMetrics(
                latency_ms=0.0,
                total_processing_duration_ms=current_total_processing_duration_ms,
                call_count=num_attempts_final,
                token_input=0,
                token_output=0,
            )
            if any(keyword in error_str for keyword in RECOVERABLE_API_ERROR_KEYWORDS):
                logger.warning(
                    "Recoverable API error detected for model '%s': %s",
                    current_model_id_for_log,
                    e,
                )
                raise RecoverableApiError(
                    "Recoverable API Error during LLM call to "
                    f"{current_model_id_for_log}: {e}"
                ) from e
            else:
                raise ValueError(
                    f"LLM Execution Error for model {current_model_id_for_log}: {e}"
                ) from e
        finally:
            if current_total_processing_duration_ms is None:
                overall_end_time_finally = time.monotonic()
                current_total_processing_duration_ms = (
                    overall_end_time_finally - overall_start_time
                ) * 1000
                if metrics is not None and metrics.total_processing_duration_ms is None:
                    metrics.total_processing_duration_ms = (
                        current_total_processing_duration_ms
                    )

    async def execute_and_log_metrics(
        self,
        model: Any,
        system_fragments: SystemFragments,
        user_fragments: UserFragments,
        response_model: type[BaseModel] | None = None,
    ) -> tuple[str, LLMMetrics | None]:
        """Wraps execute, logs metrics, returns response text and metrics."""
        response_text = ""
        metrics_val: LLMMetrics | None = None
        try:
            response_text, metrics_val = await self.execute(  # Add await
                model, system_fragments, user_fragments, response_model
            )
            return response_text, metrics_val
        except (RecoverableApiError, ValueError) as e:
            logger.debug("execute_and_log_metrics caught error: %s", e)
            raise e
        except Exception as e:
            logger.exception("Unexpected error in execute_and_log_metrics wrapper")
            raise e

    def validate_model_name(self, model_name: str) -> str | None:
        """Validate the model name using llm library helper."""
        # Delegate to the config-independent function
        is_valid, error_msg = is_valid_llm_model_name(model_name)
        if not is_valid:
            return error_msg
        return None

    def validate_model_key(self, model_name: str) -> str | None:
        """Validate the API key for a model, assuming the model name is valid.

        Args:
            model_name: The name of the model to validate

        Returns:
            Optional warning message if there are potential issues, None otherwise
        """
        provider = self._determine_provider_from_model(model_name)
        if not provider:
            logger.warning(
                "Unknown model provider for '%s'. Key validation skipped.", model_name
            )
            return f"Unknown model provider for '{model_name}'. Key validation skipped."

        # Ollama models often don't need a key for local usage
        if provider == "ollama":
            logger.debug(
                "Ollama provider detected for model '%s'; skipping key validation.",
                model_name,
            )
            return None

        # Check if we have a key configured
        key = self.config.get_model_key(provider)
        if not key:
            msg = self._format_api_key_message(provider, model_name, is_error=False)
            logger.warning(
                "No API key found for provider '%s' (model '%s')", provider, model_name
            )
            return msg

        # Basic validation - check key format based on provider
        # Valid keys either start with sk- OR are short (<20 chars)
        # Warning is shown when key doesn't start with sk- AND is not
        # short (>=20 chars)
        if provider == "anthropic" and not key.startswith("sk-") and len(key) >= 20:
            logger.warning(
                "Anthropic API key format looks invalid for model '%s'", model_name
            )
            return self._format_key_validation_message(provider)

        if provider == "openai" and not key.startswith("sk-") and len(key) >= 20:
            logger.warning(
                "OpenAI API key format looks invalid for model '%s'", model_name
            )
            return self._format_key_validation_message(provider)

        logger.debug(
            "API key for provider '%s' (model '%s') passed basic validation.",
            provider,
            model_name,
        )
        return None

    def _format_api_key_message(
        self, provider: str, model_name: str, is_error: bool = False
    ) -> str:
        """Format a message about missing or invalid API keys.

        Args:
            provider: The provider name (openai, anthropic, etc.)
            model_name: The name of the model
            is_error: Whether this is an error (True) or warning (False)

        Returns:
            A formatted message string with key setup instructions
        """
        env_key = f"VIBECTL_{provider.upper()}_API_KEY"
        file_key = f"VIBECTL_{provider.upper()}_API_KEY_FILE"

        if is_error:
            prefix = (
                f"Failed to get model '{model_name}': "
                f"API key for {provider} not found. "
            )
        else:
            prefix = (
                f"Warning: No API key found for {provider} models like '{model_name}'. "
            )

        instructions = (
            f"Set a key using one of these methods:\n"
            f"- Environment variable: export {env_key}=your-api-key\n"
            f"- Config key file: vibectl config set providers.{provider}.key_file \n"
            f"  /path/to/key/file\n"
            f"- Direct config: vibectl config set "
            f"providers.{provider}.key your-api-key\n"
            f"- Environment variable key file: export {file_key}=/path/to/key/file"
        )

        return f"{prefix}{instructions}"

    def _format_key_validation_message(self, provider: str) -> str:
        """Format a message about potentially invalid API key format.

        Args:
            provider: The provider name (openai, anthropic, etc.)

        Returns:
            A formatted warning message about the key format
        """
        provider_name = provider.capitalize()
        return (
            f"Warning: The {provider_name} API key format looks invalid. "
            f"{provider_name} keys typically start with 'sk-' and are "
            f"longer than 20 characters."
        )

    async def stream_execute(
        self,
        model: Any,
        system_fragments: SystemFragments,
        user_fragments: UserFragments,
        response_model: type[BaseModel] | None = None,  # Ignored for streaming
    ) -> AsyncIterator[str]:
        """Execute a prompt on the model and stream the response.

        Args:
            model: The model instance to execute the prompt on
            system_fragments: List of system prompt fragments.
            user_fragments: List of user prompt fragments.
            response_model: Optional Pydantic model (ignored for streaming).

        Yields:
            str: Chunks of the response text.

        Raises:
            RecoverableApiError: If a potentially recoverable API error occurs.
            ValueError: If another error occurs during execution.
        """
        current_model_id_for_log = getattr(model, "model_id", "Unknown")
        logger.debug(
            "Streaming call to model '%s'",
            current_model_id_for_log,
        )

        prompt_kwargs: dict[str, Any] = {}
        if system_fragments:
            prompt_kwargs["system"] = "\n\n".join(system_fragments)

        fragments_list: UserFragments = (
            user_fragments if user_fragments else UserFragments([])
        )
        prompt_kwargs["prompt"] = "\n\n".join(fragments_list)

        try:
            with ModelEnvironment(current_model_id_for_log, self.config):
                # model is from llm.get_model(). Its prompt() method returns
                # a Response object.
                # If the model supports streaming, this Response object is
                # synchronously iterable.
                response = model.prompt(**prompt_kwargs)

                # TODO: Metrics collection for streaming (e.g., using response.on_done()
                # if available, or by accumulating token counts if chunks provide that
                # info, which is unlikely). For now, metrics are not collected for
                # streaming responses.

                # Synchronously iterate and yield chunks with a slight await to make
                # it async-friendly.
                import asyncio  # Required for asyncio.sleep

                for chunk in response:  # This is a synchronous loop.
                    yield chunk
                    await asyncio.sleep(0)  # Allow other async tasks to run.

        except TypeError as te:
            # Catching TypeError specifically because the `for chunk in response:`
            # might fail if the `response` object is not iterable as expected (e.g.,
            # if it was an error response object).
            logger.error(
                "TypeError during synchronous streaming for model "
                f"{current_model_id_for_log}: {te}. "
                f"This may indicate the response object was not iterable as expected."
            )
            raise ValueError(
                f"LLM streaming iteration error for model {current_model_id_for_log}: "
                "Not iterable or unexpected response type."
            ) from te
        except Exception as e:
            error_str = str(e).lower()
            logger.warning(
                f"LLM streaming call to model '{current_model_id_for_log}' failed. "
                f"Error: {e}",
                exc_info=True,
            )
            if any(keyword in error_str for keyword in RECOVERABLE_API_ERROR_KEYWORDS):
                logger.warning(
                    "Recoverable API error detected during streaming for model "
                    f"'{current_model_id_for_log}': {e}"
                )
                raise RecoverableApiError(
                    "Recoverable API Error during LLM stream to "
                    f"{current_model_id_for_log}: {e}"
                ) from e
            else:
                raise ValueError(
                    "LLM Streaming Execution Error for model "
                    f"{current_model_id_for_log}: {e}"
                ) from e

    async def stream_execute_and_log_metrics(
        self,
        model: Any,
        system_fragments: SystemFragments,
        user_fragments: UserFragments,
        response_model: type[BaseModel] | None = None,  # Ignored for streaming
    ) -> tuple[AsyncIterator[str], "StreamingMetricsCollector"]:
        """Execute a prompt on the model and stream the response with metrics.

        Args:
            model: The model instance to execute the prompt on
            system_fragments: List of system prompt fragments.
            user_fragments: List of user prompt fragments.
            response_model: Optional Pydantic model (ignored for streaming).

        Returns:
            tuple[AsyncIterator[str], StreamingMetricsCollector]:
                A tuple containing the async iterator
                for response chunks and metrics collector.
        """
        import time

        current_model_id_for_log = getattr(model, "model_id", "Unknown")
        logger.debug(
            "Streaming call with metrics to model '%s'",
            current_model_id_for_log,
        )

        overall_start_time = time.monotonic()
        first_chunk_time: float | None = None
        total_chunks = 0
        accumulated_text = ""
        completed = False
        final_metrics: LLMMetrics | None = None

        metrics_collector = StreamingMetricsCollector()

        async def metered_stream() -> AsyncIterator[str]:
            nonlocal \
                first_chunk_time, \
                total_chunks, \
                accumulated_text, \
                completed, \
                final_metrics

            try:
                # Start the streaming
                stream_iterator = self.stream_execute(
                    model, system_fragments, user_fragments, response_model
                )

                async for chunk in stream_iterator:
                    if first_chunk_time is None:
                        first_chunk_time = time.monotonic()
                    total_chunks += 1
                    accumulated_text += chunk
                    yield chunk

            except Exception as e:
                logger.error(
                    f"Error during streaming for model {current_model_id_for_log}: {e}"
                )
                raise
            finally:
                # Calculate final metrics after streaming completes
                overall_end_time = time.monotonic()
                total_duration_ms = (overall_end_time - overall_start_time) * 1000

                # Calculate latency (time to first chunk)
                latency_ms = 0.0
                if first_chunk_time is not None:
                    latency_ms = (first_chunk_time - overall_start_time) * 1000

                # Estimate token counts (rough approximation)
                def estimate_tokens(text: str) -> int:
                    # Rough estimate: ~4 characters per token on average
                    return max(1, len(text) // 4)

                input_prompt = "\n\n".join(system_fragments) if system_fragments else ""
                input_prompt += (
                    "\n\n" + "\n\n".join(user_fragments) if user_fragments else ""
                )
                token_input = estimate_tokens(input_prompt)
                token_output = estimate_tokens(accumulated_text)

                final_metrics = LLMMetrics(
                    latency_ms=latency_ms,
                    total_processing_duration_ms=total_duration_ms,
                    token_input=token_input,
                    token_output=token_output,
                    call_count=1,
                )

                # Mark metrics as completed
                metrics_collector._mark_completed(final_metrics)
                completed = True

                logger.info(
                    "LLM streaming call to "
                    f"{current_model_id_for_log} completed. "
                    f"Latency (first chunk): {latency_ms:.2f} ms, "
                    f"Total Duration: {total_duration_ms:.2f} ms, "
                    f"Chunks: {total_chunks}, "
                    f"Estimated Tokens In: {token_input}, "
                    f"Estimated Tokens Out: {token_output}"
                )

        try:
            # Return the metered stream iterator and metrics collector
            return metered_stream(), metrics_collector

        except Exception as e:
            overall_end_time = time.monotonic()
            total_duration_ms = (overall_end_time - overall_start_time) * 1000

            error_str = str(e).lower()
            logger.warning(
                "LLM streaming call with metrics to "
                f"{current_model_id_for_log} failed. "
                f"Total Duration: {total_duration_ms:.2f} ms. "
                f"Error: {e}"
            )

            if any(keyword in error_str for keyword in RECOVERABLE_API_ERROR_KEYWORDS):
                logger.warning(
                    "Recoverable API error detected during streaming with metrics for "
                    f"model {current_model_id_for_log}: {e}"
                )
                raise RecoverableApiError(
                    "Recoverable API Error during LLM stream with metrics to "
                    f"{current_model_id_for_log}: {e}"
                ) from e
            else:
                raise ValueError(
                    "LLM Streaming Execution Error with metrics for model "
                    f"{current_model_id_for_log}: {e}"
                ) from e


# Default model adapter instance
_default_adapter: ModelAdapter | None = None


def get_model_adapter(config: Config | None = None) -> ModelAdapter:
    """Get the default model adapter instance.

    Creates a new instance if one doesn't exist.

    Args:
        config: Optional Config instance. If not provided, creates a new one.

    Returns:
        ModelAdapter: The default model adapter instance
    """
    global _default_adapter
    if _default_adapter is None:
        # Get or create config if not provided
        if config is None:
            config = Config()

        # Check if proxy mode is enabled
        proxy_enabled = config.get("proxy.enabled", False)

        if proxy_enabled:
            # Import here to avoid circular imports
            from .config import parse_proxy_url
            from .proxy_model_adapter import ProxyModelAdapter

            # Get proxy configuration
            server_url = config.get("proxy.server_url")

            # Provide helpful error message if server_url is missing
            if not server_url:
                raise ValueError(
                    "Proxy mode is enabled but no server URL is configured.\n"
                    "Fix this by either:\n"
                    "  1. Configure a proxy server: "
                    "vibectl setup-proxy configure <server-url>\n"
                    "  2. Disable proxy mode: vibectl setup-proxy disable --yes\n"
                    "\nExample server URLs:\n"
                    "  - vibectl-server://myserver.com:443\n"
                    "  - vibectl-server://jwt-token@myserver.com:443 (with JWT auth)\n"
                    "  - vibectl-server-insecure://localhost:50051"
                )

            # Parse the server URL with better error handling
            try:
                proxy_config = parse_proxy_url(server_url)
                if proxy_config is None:
                    raise ValueError(f"Invalid proxy URL format: {server_url}")
            except Exception as e:
                raise ValueError(
                    f"Invalid proxy server URL: {server_url}\n"
                    f"Error: {e}\n\n"
                    "Fix this by either:\n"
                    "  1. Configure a valid proxy server: "
                    "vibectl setup-proxy configure <server-url>\n"
                    "  2. Disable proxy mode: vibectl setup-proxy disable --yes\n"
                    "\nValid server URL formats:\n"
                    "  - vibectl-server://myserver.com:443 (secure)\n"
                    "  - vibectl-server://jwt-token@myserver.com:443 "
                    "(secure with JWT auth)\n"
                    "  - vibectl-server-insecure://localhost:50051 (insecure)\n"
                    "  - vibectl-server://secret@myserver.com:8080 (with auth)"
                ) from e

            _default_adapter = ProxyModelAdapter(
                config=config,
                host=proxy_config.host,
                port=proxy_config.port,
                jwt_token=proxy_config.jwt_token,
                use_tls=proxy_config.use_tls,
            )
        else:
            # Use direct LLM adapter
            _default_adapter = LLMModelAdapter(config)

    return _default_adapter


def set_model_adapter(adapter: ModelAdapter) -> None:
    """Set the default model adapter instance.

    This is primarily used for testing or to switch adapter implementations.

    Args:
        adapter: The adapter instance to set as default
    """
    global _default_adapter
    _default_adapter = adapter


def reset_model_adapter() -> None:
    """Reset the default model adapter instance.

    This is primarily used for testing to ensure a clean state.
    """
    global _default_adapter
    _default_adapter = None


def validate_model_key_on_startup(model_name: str) -> str | None:
    """Validate the model key on startup.

    Args:
        model_name: The name of the model to validate

    Returns:
        Optional warning message if there are potential issues, None otherwise
    """
    adapter = get_model_adapter()
    return adapter.validate_model_key(model_name)


async def _get_response_text_async(response: ModelResponse) -> str:
    """Helper to await response.text()."""
    return await response.text()


async def _get_response_json_async(response: ModelResponse) -> dict[str, Any]:
    """Helper to await response.json()."""
    return await response.json()


async def _get_response_usage_async(response: ModelResponse) -> LLMUsage:
    """Helper to await response.usage()."""
    return await response.usage()
