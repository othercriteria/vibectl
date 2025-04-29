"""Defines Pydantic models for structured LLM responses."""

from pydantic import BaseModel, Field, field_validator
from pydantic_core.core_schema import ValidationInfo

from .types import ActionType


class LLMCommandResponse(BaseModel):
    """Schema for structured responses from the LLM for command execution."""

    action_type: ActionType = Field(
        ..., description="The type of action the LLM wants to perform."
    )
    commands: list[str] | None = Field(
        None,
        description=(
            "List of command parts (arguments) for kubectl. Required if action_type is"
            " COMMAND."
        ),
    )
    explanation: str | None = Field(
        None, description="Textual explanation or feedback from the LLM."
    )
    error: str | None = Field(
        None,
        description=(
            "Error message if the LLM encountered an issue or refused the request."
            " Required if action_type is ERROR."
        ),
    )
    wait_duration_seconds: int | None = Field(
        None,
        description="Duration in seconds to wait. Required if action_type is WAIT.",
    )

    @field_validator("commands", mode="before")
    @classmethod
    def check_commands(
        cls, v: list[str] | None, info: ValidationInfo
    ) -> list[str] | None:
        """Validate commands field based on action_type."""
        if "action_type" in info.data:
            action_type_str = info.data["action_type"]
            try:
                action_type = ActionType(action_type_str)
                if action_type == ActionType.COMMAND and not v:
                    raise ValueError("commands is required when action_type is COMMAND")
            except ValueError as e:
                raise ValueError(
                    f"Invalid action_type provided: {action_type_str}"
                ) from e
        return v

    @field_validator("error", mode="before")
    @classmethod
    def check_error(cls, v: str | None, info: ValidationInfo) -> str | None:
        """Validate error field based on action_type."""
        if "action_type" in info.data:
            action_type_str = info.data["action_type"]
            try:
                action_type = ActionType(action_type_str)
                if action_type == ActionType.ERROR and not v:
                    raise ValueError("error is required when action_type is ERROR")
            except ValueError as e:
                raise ValueError(
                    f"Invalid action_type provided: {action_type_str}"
                ) from e
        return v

    @field_validator("wait_duration_seconds", mode="before")
    @classmethod
    def check_wait_duration(cls, v: int | None, info: ValidationInfo) -> int | None:
        """Validate wait_duration_seconds field based on action_type."""
        if "action_type" in info.data:
            action_type_str = info.data["action_type"]
            try:
                action_type = ActionType(action_type_str)
                if action_type == ActionType.WAIT and v is None:
                    raise ValueError(
                        "wait_duration_seconds is required when action_type is WAIT"
                    )
            except ValueError as e:
                raise ValueError(
                    f"Invalid action_type provided: {action_type_str}"
                ) from e
        return v

    model_config = {
        "use_enum_values": True,
        "extra": "ignore",
    }
