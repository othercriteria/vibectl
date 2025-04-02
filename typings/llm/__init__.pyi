"""Type stubs for llm module."""

from typing import Protocol

class LLMResponse(Protocol):
    """Protocol for LLM response objects."""

    def text(self) -> str:
        """Get the text content of the response."""
        ...

class LLMModel(Protocol):
    """Protocol for LLM model objects."""

    def prompt(self, prompt: str) -> LLMResponse:
        """Send a prompt to the model and get a response."""
        ...

def get_model(model_name: str) -> LLMModel:
    """Get a model instance by name."""
    ...
