"""
Model adapter interface for vibectl.

This module provides an abstraction layer for interacting with LLM models,
making it easier to switch between model providers and handle model-specific
configuration. It uses an adapter pattern to isolate the rest of the application
from the details of model interaction.
"""

import os
from abc import ABC, abstractmethod
from typing import Any, Protocol, cast

import llm

from .config import Config


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
    def execute(self, model: Any, prompt_text: str) -> str:
        """Execute a prompt on the model and get a response.

        Args:
            model: The model instance to execute the prompt on
            prompt_text: The prompt text to execute

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


class ModelEnvironment:
    """Context manager for handling model-specific environment variables.

    This class provides a safer way to temporarily set environment variables
    for model execution, ensuring they are properly restored even in case of exceptions.
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
        if model_name.startswith("gpt-"):
            return "openai"
        elif model_name.startswith("claude-"):
            return "anthropic"
        elif model_name.startswith("ollama:"):
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
        if api_key:
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

    def _determine_provider_from_model(self, model_name: str) -> str | None:
        """Determine the provider from the model name.

        Args:
            model_name: The model name

        Returns:
            The provider name (openai, anthropic, ollama) or None if unknown
        """
        if model_name.startswith("gpt-"):
            return "openai"
        elif model_name.startswith("claude-"):
            return "anthropic"
        elif model_name.startswith("ollama:"):
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
            return self._model_cache[model_name]

        # Use context manager for environment variable handling
        with ModelEnvironment(model_name, self.config):
            try:
                # Get model from LLM package
                model = llm.get_model(model_name)
                self._model_cache[model_name] = model
                return model
            except Exception as e:
                provider = self._determine_provider_from_model(model_name)

                # Check if error might be due to missing API key
                if provider and not self.config.get_model_key(provider):
                    env_var = f"VIBECTL_{provider.upper()}_API_KEY"
                    file_var = f"VIBECTL_{provider.upper()}_API_KEY_FILE"
                    raise ValueError(
                        f"Failed to get model '{model_name}': API key for {provider} not found. "
                        f"Please set it using one of these methods:\n"
                        f"- Environment variable: export {env_var}=your-api-key\n"
                        f"- Config key file: vibectl config set model_key_files.{provider} /path/to/key/file\n"
                        f"- Direct config: vibectl config set model_keys.{provider} your-api-key\n"
                        f"- Environment variable key file: export {file_var}=/path/to/key/file"
                    ) from e

                # Generic error message if not API key related
                raise ValueError(f"Failed to get model '{model_name}': {e}") from e

    def execute(self, model: Any, prompt_text: str) -> str:
        """Execute a prompt on the model and get a response.

        Args:
            model: The model instance to execute the prompt on
            prompt_text: The prompt text to execute

        Returns:
            str: The response text

        Raises:
            ValueError: If there's an error during execution
        """
        # Get model name from the model object if available
        model_name = getattr(model, "name", "unknown")

        # Use context manager for environment variable handling
        with ModelEnvironment(model_name, self.config):
            try:
                response = model.prompt(prompt_text)
                if hasattr(response, "text"):
                    return cast("ModelResponse", response).text()
                return str(response)
            except Exception as e:
                provider = self._determine_provider_from_model(model_name)

                # Check if error might be due to invalid API key
                if provider and "authentication" in str(e).lower():
                    env_var = f"VIBECTL_{provider.upper()}_API_KEY"
                    raise ValueError(
                        f"Authentication error during model execution: {e}\n"
                        f"Please check your {provider} API key is valid and set correctly."
                    ) from e

                # Generic error message
                raise ValueError(f"Error during model execution: {e}") from e

    def validate_model_key(self, model_name: str) -> str | None:
        """Validate the API key for a model.

        Args:
            model_name: The name of the model to validate

        Returns:
            Optional warning message if there are potential issues, None otherwise
        """
        provider = self._determine_provider_from_model(model_name)
        if not provider:
            return f"Unknown model provider for '{model_name}'. Key validation skipped."

        # Ollama models often don't need a key for local usage
        if provider == "ollama":
            return None

        # Check if we have a key configured
        key = self.config.get_model_key(provider)
        if not key:
            env_var = f"VIBECTL_{provider.upper()}_API_KEY"
            file_var = f"VIBECTL_{provider.upper()}_API_KEY_FILE"
            return (
                f"Warning: No API key found for {provider} models like '{model_name}'. "
                f"Set a key using one of these methods:\n"
                f"- Environment variable: export {env_var}=your-api-key\n"
                f"- Config key file: vibectl config set model_key_files.{provider} /path/to/key/file\n"
                f"- Direct config: vibectl config set model_keys.{provider} your-api-key\n"
                f"- Environment variable key file: export {file_var}=/path/to/key/file"
            )

        # Basic validation - check key format based on provider
        # Valid keys either start with sk- OR are short (<20 chars)
        # Warning is shown when key doesn't start with sk- AND is not short (>=20 chars)
        if provider == "anthropic" and not key.startswith("sk-") and len(key) >= 20:
            return (
                "Warning: The Anthropic API key format looks invalid. "
                "Anthropic keys typically start with 'sk-' and are longer than 20 characters."
            )

        if provider == "openai" and not key.startswith("sk-") and len(key) >= 20:
            return (
                "Warning: The OpenAI API key format looks invalid. "
                "OpenAI keys typically start with 'sk-' and are longer than 20 characters."
            )

        return None


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
