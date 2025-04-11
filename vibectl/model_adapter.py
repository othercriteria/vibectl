"""
Model adapter interface for vibectl.

This module provides an abstraction layer for interacting with LLM models,
making it easier to switch between model providers and handle model-specific
configuration. It uses an adapter pattern to isolate the rest of the application
from the details of model interaction.
"""

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

    def get_model(self, model_name: str) -> Any:
        """Get an LLM model instance by name, with caching.

        Args:
            model_name: The name of the model to get

        Returns:
            Any: The model instance
        """
        # Check cache first
        if model_name in self._model_cache:
            return self._model_cache[model_name]

        # Get model from LLM package
        try:
            model = llm.get_model(model_name)
            self._model_cache[model_name] = model
            return model
        except Exception as e:
            raise ValueError(f"Failed to get model '{model_name}': {e}") from e

    def execute(self, model: Any, prompt_text: str) -> str:
        """Execute a prompt on the model and get a response.

        Args:
            model: The model instance to execute the prompt on
            prompt_text: The prompt text to execute

        Returns:
            str: The response text
        """
        try:
            response = model.prompt(prompt_text)
            if hasattr(response, "text"):
                return cast("ModelResponse", response).text()
            return str(response)
        except Exception as e:
            raise ValueError(f"Error during model execution: {e}") from e


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
    """Reset the default model adapter to None.

    This forces a new adapter to be created on the next call to get_model_adapter.
    """
    global _default_adapter
    _default_adapter = None
