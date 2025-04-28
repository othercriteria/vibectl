"""Defines Pydantic models for structured LLM responses."""
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field, validator

from .types import ActionType


class LLMCommandResponse(BaseModel):
    """Schema for structured responses from the LLM for command execution."""

    action_type: ActionType = Field(
        ..., description="The type of action the LLM wants to perform."
    )
    commands: Optional[List[str]] = Field(
        None,
        description=(
            "List of command parts (arguments) for kubectl. Required if action_type is"
            " COMMAND."
        ),
    )
    explanation: Optional[str] = Field(
        None, description="Textual explanation or feedback from the LLM."
    )
    error: Optional[str] = Field(
        None,
        description=(
            "Error message if the LLM encountered an issue or refused the request."
            " Required if action_type is ERROR."
        ),
    )
    wait_duration_seconds: Optional[int] = Field(
        None,
        description="Duration in seconds to wait. Required if action_type is WAIT.",
    )

    @validator("commands", always=True)
    def check_commands(cls, v: Optional[List[str]], values: Dict[str, Any]) -> Optional[List[str]]:
        """Validate commands field based on action_type."""
        action_type = values.get("action_type")
        if action_type == ActionType.COMMAND and not v:
            raise ValueError("commands is required when action_type is COMMAND")
        return v

    @validator("error", always=True)
    def check_error(cls, v: Optional[str], values: Dict[str, Any]) -> Optional[str]:
        """Validate error field based on action_type."""
        action_type = values.get("action_type")
        if action_type == ActionType.ERROR and not v:
            raise ValueError("error is required when action_type is ERROR")
        return v

    @validator("wait_duration_seconds", always=True)
    def check_wait_duration(
        cls, v: Optional[int], values: Dict[str, Any]
    ) -> Optional[int]:
        """Validate wait_duration_seconds field based on action_type."""
        action_type = values.get("action_type")
        if action_type == ActionType.WAIT and v is None:
            raise ValueError(
                "wait_duration_seconds is required when action_type is WAIT"
            )
        return v

    class Config:
        # Use enum values in the schema
        use_enum_values = True 