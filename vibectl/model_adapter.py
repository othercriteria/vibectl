"""
Model adapter interface for vibectl.

This module provides an abstraction layer for interacting with LLM models,
making it easier to switch between model providers and handle model-specific
configuration. It uses an adapter pattern to isolate the rest of the application
from the details of model interaction.
"""

import os
from abc import ABC, abstractmethod
from typing import Any, Protocol, cast, runtime_checkable

import llm
from pydantic import BaseModel

from .config import Config

# Import the new validation function
from .llm_interface import is_valid_llm_model_name
from .logutil import logger

# Import the consolidated keywords and custom exception
from .types import RECOVERABLE_API_ERROR_KEYWORDS, RecoverableApiError


@runtime_checkable
class ModelResponse(Protocol):
    """Protocol defining the expected interface for model responses."""

    def text(self) -> str:
        """Get the text content of the response.

        Returns:
            str: The text content of the response
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
        prompt_text: str,
        response_model: type[BaseModel] | None = None,
    ) -> str:
        """Execute a prompt on the model and get a response.

        Args:
            model: The model instance to execute the prompt on
            prompt_text: The prompt text to execute
            response_model: Optional Pydantic model for structured JSON response.

        Returns:
            str: The response text
        """
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
        elif name_lower.startswith("ollama:"):
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
        elif name_lower.startswith("ollama:"):
            return "ollama"
        # Default to None if we can't determine the provider
        return None

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
        prompt_text: str,
        response_model: type[BaseModel] | None = None,
    ) -> str:
        """Execute a prompt on the model and get a response.

        Args:
            model: The model instance to execute the prompt on
            prompt_text: The prompt text to execute
            response_model: Optional Pydantic model for structured JSON response.
                            If provided, attempts to use the model's schema support.
                            If the model doesn't support schemas, it falls back
                            to a regular prompt call.

        Returns:
            str: The response text (either raw text or JSON string if schema used).

        Raises:
            ValueError: If there is an error executing the prompt. The message will
                        indicate if the error seems recoverable based on keywords.
            RecoverableApiError: If the error seems recoverable (e.g., rate limit).
        """
        logger.debug(
            "Executing prompt on model '%s' with response model: %s",
            model.model_id,
            response_model.__name__ if response_model else "None",
        )
        logger.debug("Prompt text:\n%s", prompt_text)

        # Use context manager for environment variables
        with ModelEnvironment(model.model_id, self.config):
            response: Any = None
            try:
                if response_model:
                    # Attempt schema-based call first
                    try:
                        logger.debug("Attempting schema-based prompt call.")
                        # Assume llm might raise specific error if schema not supported
                        # e.g., llm.SchemaUnsupportedError - adjust if different
                        response = model.prompt(prompt_text, schema=response_model)
                        logger.debug("Schema-based call successful.")
                    except AttributeError as ae:
                        # Catch potential AttributeError if model lacks schema support
                        # or if llm library changes how unsupported schemas are signaled
                        # Also catch placeholder SchemaUnsupportedError
                        # TODO: Identify and catch the specific exception raised by llm
                        #       when a model doesn't support schemas.
                        #       Replace this broad catch if possible.
                        if "schema" in str(ae).lower():  # Basic check
                            logger.warning(
                                "Model '%s' may not support schemas or schema feature "
                                "failed (%s). Falling back to non-schema prompt.",
                                model.model_id,
                                ae,
                            )
                            # Fallback: Call without schema
                            response = model.prompt(prompt_text)
                        else:
                            # Re-raise if the AttributeError is unrelated to schemas
                            raise ae
                else:
                    # Regular call if no schema is provided
                    response = model.prompt(prompt_text)

                # --- Process the response ---

                # Check if the response conforms to the expected protocol
                if not isinstance(response, ModelResponse):
                    logger.warning(
                        "Model response does not conform to ModelResponse protocol: %s",
                        type(response),
                    )
                    # Attempt to get text anyway, assuming it might be a basic string
                    # or have a similar interface. This is a best-effort approach.
                    try:
                        return str(response)  # Fallback to string conversion
                    except Exception as conversion_err:
                        logger.error(
                            "Failed to convert bad model response to string: %s",
                            conversion_err,
                            exc_info=True,
                        )
                        raise ValueError(
                            f"Model response type {type(response)} cannot be processed."
                        ) from conversion_err

                # Get text from the response object
                # Cast needed because 'response' could be Any after fallback
                response_text = cast("ModelResponse", response).text()

                # If a schema was *attempted* and fallback occurred, the result might
                # be unstructured text. If schema succeeded, it should be JSON.
                # The caller (e.g., handle_vibe_request) needs to handle parsing.
                return response_text

            except Exception as e:
                # BUG FIX: Remove the immediate re-raise that prevented error checking.
                # raise e # <<< REMOVE THIS LINE

                # If this is an AttributeError likely re-raised from schema fallback,
                # let it propagate directly without wrapping.
                if isinstance(e, AttributeError) and response_model is not None:
                    logger.debug("Re-raising AttributeError from schema handling.")
                    raise e

                error_message = str(e)
                error_message_lower = error_message.lower()
                logger.error(
                    "Error executing prompt on model '%s': %s",
                    model.model_id,
                    error_message,
                    exc_info=True,  # Log traceback directly at ERROR level
                )

                # Check if the error message indicates a recoverable API error
                is_recoverable = any(
                    keyword in error_message_lower
                    for keyword in RECOVERABLE_API_ERROR_KEYWORDS
                )

                if is_recoverable:
                    raise RecoverableApiError(f"{error_message}") from e
                else:
                    # Raise a general ValueError for other errors
                    raise ValueError(f"Error executing prompt: {error_message}") from e

    def validate_model_name(self, model_name: str) -> str | None:
        """Validate if the model name is recognized by the llm library.

        This check does not validate API keys.

        Args:
            model_name: The name of the model to validate.

        Returns:
            Optional error message string if validation fails, None otherwise.
        """
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
