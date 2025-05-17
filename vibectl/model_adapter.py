"""
Model adapter interface for vibectl.

This module provides an abstraction layer for interacting with LLM models,
making it easier to switch between model providers and handle model-specific
configuration. It uses an adapter pattern to isolate the rest of the application
from the details of model interaction.
"""

import os
import time
from abc import ABC, abstractmethod
from contextlib import ExitStack
from typing import Any, Protocol, runtime_checkable

import llm
from pydantic import BaseModel

from .config import Config

# Import the new validation function
from .llm_interface import is_valid_llm_model_name
from .logutil import logger

# Import the consolidated keywords and custom exception
from .types import (
    RECOVERABLE_API_ERROR_KEYWORDS,
    LLMMetrics,
    RecoverableApiError,
    SystemFragments,
    UserFragments,
)


# Protocol for the object returned by response.usage()
@runtime_checkable
class LLMUsage(Protocol):
    """Protocol defining the expected interface for model usage details."""

    input: int
    output: int
    details: dict[str, Any] | None


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


@runtime_checkable
class ModelResponse(Protocol):
    """Protocol defining the expected interface for model responses."""

    def text(self) -> str:
        """Get the text content of the response.

        Returns:
            str: The text content of the response
        """
        ...

    def json(self) -> dict[str, Any]:
        """Get the JSON content of the response.

        Returns:
            dict[str, Any]: The JSON content of the response as a dictionary.
        """
        ...

    def usage(self) -> LLMUsage:
        """Get the token usage information for the response.

        Returns:
            LLMUsage: An object containing token usage details.
        """
        ...


class ModelAdapter(ABC):
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
    def execute(
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
    def execute_and_log_metrics(
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

    def _get_token_usage(
        self, response: ModelResponse, model_id: str
    ) -> tuple[int, int]:
        """Safely extracts token usage from a model response.

        Args:
            response: The model response object.
            model_id: The ID of the model, for logging purposes.

        Returns:
            A tuple containing (token_input, token_output).
        """
        token_input = 0
        token_output = 0
        try:
            usage_obj = response.usage()  # type: ignore[attr-defined]
            if usage_obj:
                # Log the raw usage object at DEBUG level
                logger.debug(
                    "Raw LLM usage object for model %s: %s", model_id, usage_obj
                )

                raw_input = getattr(usage_obj, "input", None)
                raw_output = getattr(usage_obj, "output", None)

                try:
                    token_input = int(raw_input) if raw_input is not None else 0
                except (TypeError, ValueError):
                    token_input = 0  # Default to 0 if conversion fails or type is wrong

                try:
                    token_output = int(raw_output) if raw_output is not None else 0
                except (TypeError, ValueError):
                    token_output = (
                        0  # Default to 0 if conversion fails or type is wrong
                    )

            logger.debug(
                "Token usage for model %s - Input: %d, Output: %d",
                model_id,
                token_input,
                token_output,
            )
        except AttributeError:
            logger.warning(
                "Model %s response lacks usage() method for token counting.", model_id
            )
        except Exception as usage_err:
            logger.warning(
                "Failed to get token usage for model %s: %s", model_id, usage_err
            )
        return token_input, token_output

    def _execute_single_prompt_attempt(
        self, model: Any, prompt_kwargs: dict[str, Any]
    ) -> ModelResponse:
        """Executes a single prompt attempt and returns the validated response object.

        Args:
            model: The model instance.
            prompt_kwargs: Keyword arguments for the model's prompt method.

        Returns:
            The validated ModelResponse object.

        Raises:
            AttributeError: If model.prompt has an issue with arguments.
            TypeError: If the response object is not of the expected type.
            Other exceptions from model.prompt().
        """
        response = model.prompt(**prompt_kwargs)
        if not isinstance(response, ModelResponse):
            raise TypeError(f"Expected ModelResponse, got {type(response).__name__}")
        return response

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
                        "Attempting to adapt by removing 'schema' for model %s.",
                        model.model_id,
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
                        "into 'prompt' for model %s.",
                        model.model_id,
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
                        "Adaptation applied for model %s. Proceeding to attempt %d.",
                        model.model_id,
                        attempt_num + 1,
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
                    "LLM call to model %s failed on attempt %d with "
                    "non-AttributeError: %s",
                    model.model_id,
                    attempt_num,
                    e,
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

    def execute(
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
        overall_start_time = time.monotonic()
        current_total_processing_duration_ms: float | None = None
        metrics: LLMMetrics | None = None
        all_attempt_latencies_ms_list: list[float] = []
        num_attempts_final = 0
        max_adaptation_attempts = 3
        text_extraction_duration_ms = 0.0  # Initialize

        try:
            current_model_id_for_log = getattr(model, "model_id", "Unknown")
            logger.debug(
                "Executing call to model '%s' with response_model: %s",
                current_model_id_for_log,
                response_model is not None,
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
                            "Generated schema for model %s: %s",
                            current_model_id_for_log,
                            schema_dict,
                        )
                    except Exception as schema_exc:
                        logger.error(
                            "Failed to generate schema for model %s: %s. "
                            "Duration: %.2f ms",
                            current_model_id_for_log,
                            schema_exc,
                            schema_timer.duration_ms,
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
                response_text = response_obj.text()
            text_extraction_duration_ms = text_timer.duration_ms  # Store for metrics

            # Log the raw response object at DEBUG level
            logger.debug(
                "Raw LLM response JSON for model %s: %s",
                current_model_id_for_log,
                response_obj.json(),
            )

            with TimedOperation(
                logger, current_model_id_for_log, "_get_token_usage() call"
            ):
                token_input, token_output = self._get_token_usage(
                    response_obj, current_model_id_for_log
                )

            overall_end_time = time.monotonic()
            current_total_processing_duration_ms = (
                overall_end_time - overall_start_time
            ) * 1000

            metrics = LLMMetrics(
                latency_ms=text_extraction_duration_ms,  # Use stored duration
                total_processing_duration_ms=current_total_processing_duration_ms,
                token_input=token_input,
                token_output=token_output,
                call_count=num_attempts_final,
            )
            logger.info(
                "LLM call to model %s completed. Primary Latency (text_extraction): "
                "%.2f ms, llm_lib_latency: %.2f ms, Total Duration: %.2f ms, "
                "Tokens In: %d, Tokens Out: %d",
                current_model_id_for_log,
                text_extraction_duration_ms,
                llm_lib_latency_ms,
                current_total_processing_duration_ms,
                token_input,
                token_output,
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
                "LLM call to model %s failed after %d adaptation attempts. "
                "Last llm_lib_latency: %.2f ms, Total Duration: %.2f ms. "
                "Error: %s",
                current_model_id_for_log,
                num_attempts_final,
                llm_lib_latency_ms,
                current_total_processing_duration_ms,
                lae.args[0],
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

            error_str = str(e).lower()
            current_model_id_for_log = getattr(model, "model_id", "Unknown")

            logger.warning(
                "LLM call to model '%s' failed. Attempts (if adaptation stage): %d. "
                "Last/Relevant llm_lib_latency: %.2f ms, Total Duration: %.2f ms. "
                "Error: %s",
                current_model_id_for_log,
                int(num_attempts_final),
                llm_lib_latency_ms_for_error
                if llm_lib_latency_ms_for_error is not None
                else -1.0,
                current_total_processing_duration_ms,
                e,
                exc_info=True,
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

    def execute_and_log_metrics(
        self,
        model: Any,
        system_fragments: SystemFragments,
        user_fragments: UserFragments,
        response_model: type[BaseModel] | None = None,
    ) -> tuple[str, LLMMetrics | None]:
        """Wraps execute, logs metrics, returns response text and metrics."""
        # TODO: When response_model is provided, this method should ideally attempt
        # to parse the response into the Pydantic model. If successful, it could
        # return tuple[BaseModel, LLMMetrics | None] or a more specific type.
        # If parsing fails, it should either raise the parsing exception (e.g.,
        # ValidationError, JSONDecodeError) or return a clear error indicator
        # alongside the raw string, rather than just the raw string.
        # Currently, it always returns tuple[str, LLMMetrics | None], and parsing
        # is handled by the caller.
        response_text = ""
        metrics = None
        try:
            # Pass fragments to execute
            response_text, metrics = self.execute(
                model, system_fragments, user_fragments, response_model
            )
            return response_text, metrics
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

        # The actual model loading check is removed from here.
        # We now assume the model name is valid and focus only on the key.

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
            f"- Config key file: vibectl config set model_key_files.{provider} \n"
            f"  /path/to/key/file\n"
            f"- Direct config: vibectl config set model_keys.{provider} your-api-key\n"
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
