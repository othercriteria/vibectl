"""Defines Pydantic models for structured LLM responses."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_core.core_schema import ValidationInfo

from .types import ActionType


# Base Action Model
class LLMAction(BaseModel):
    """Base model for all LLM actions."""

    # This field will be used for discriminating unions
    # action_type: ActionType # This will be defined in subclasses with Literal


# Specific Action Models
class ThoughtAction(LLMAction):
    """Schema for a thought action from the LLM."""

    action_type: Literal[ActionType.THOUGHT] = Field(ActionType.THOUGHT)
    text: str = Field(..., description="The textual content of the LLM's thought.")


class CommandAction(LLMAction):
    """Schema for a command execution action from the LLM."""

    action_type: Literal[ActionType.COMMAND] = Field(ActionType.COMMAND)
    commands: list[str] | None = Field(
        None,
        description=(
            "List of command parts (arguments) for kubectl, *excluding* the initial"
            " command verb (e.g., get, create). Required if no yaml_manifest is"
            " provided."
        ),
    )
    yaml_manifest: str | None = Field(
        None,
        description=(
            "YAML manifest content as a string. Used when action_type is COMMAND and"
            " requires a manifest (e.g., for kubectl create -f -). Can be combined"
            " with 'commands' for flags like '-n'."
        ),
    )
    allowed_exit_codes: list[int] | None = Field(
        None,
        description=(
            "List of allowed exit codes for the planned command. If not provided, "
            "the system may use a default (e.g., [0]) or infer based on the "
            "command verb in specific contexts."
        ),
    )
    explanation: str | None = Field(
        None,
        description=(
            "AI's reasoning for choosing this action. If not provided, the system "
            "may use a default (e.g., 'no additional explanation provided')."
        ),
    )

    @field_validator("commands", mode="before")
    @classmethod
    def check_commands_or_yaml_required(
        cls, v: list[str] | None, info: ValidationInfo
    ) -> list[str] | None:
        """Validate that either commands or yaml_manifest is present."""
        # This validator assumes action_type is already confirmed as COMMAND
        # by the discriminated union.
        yaml_manifest = info.data.get("yaml_manifest")
        if not v and not yaml_manifest:
            raise ValueError(
                "Either 'commands' or 'yaml_manifest' is required for a COMMAND action"
            )
        return v


class WaitAction(LLMAction):
    """Schema for a wait action from the LLM."""

    action_type: Literal[ActionType.WAIT] = Field(ActionType.WAIT)
    duration_seconds: int = Field(..., description="Duration in seconds to wait.")


class ErrorAction(LLMAction):
    """Schema for an error action from the LLM."""

    action_type: Literal[ActionType.ERROR] = Field(ActionType.ERROR)
    message: str = Field(
        ...,
        description="Error message if the LLM encountered an issue or refused request.",
    )


class FeedbackAction(LLMAction):
    """Schema for a feedback action from the LLM."""

    action_type: Literal[ActionType.FEEDBACK] = Field(ActionType.FEEDBACK)
    message: str = Field(..., description="Textual feedback from the LLM.")
    explanation: str | None = Field(
        None, description="AI's reasoning for choosing this action."
    )
    suggestion: str | None = Field(
        None, description="Optional suggested text for the user to update memory with."
    )


class DoneAction(LLMAction):
    """Schema for a done action from the LLM (used by vibectl check)."""

    action_type: Literal[ActionType.DONE] = Field(ActionType.DONE)
    exit_code: int | None = Field(
        None,
        description=(
            "The intended exit code for vibectl. If None, a default may be used "
            "(e.g., 3 for 'cannot determine' in vibectl check)."
        ),
    )
    explanation: str | None = Field(
        None, description="The LLM's final reasoning or message for this DONE action."
    )


# Union of all specific actions for Pydantic's discriminated union
AnyLLMAction = (
    ThoughtAction
    | CommandAction
    | WaitAction
    | ErrorAction
    | FeedbackAction
    | DoneAction
)


class LLMPlannerResponse(BaseModel):
    """Schema for structured responses from the LLM planner."""

    action: AnyLLMAction = Field(
        ..., description="The single action for vibectl to perform."
    )

    model_config = {
        "use_enum_values": True,
        "extra": "forbid",  # Forbid extra fields to ensure strict adherence
    }


class ApplyFileScopeResponse(BaseModel):
    """Schema for LLM response when scoping files for kubectl apply."""

    file_selectors: list[str] = Field(
        ...,
        description=(
            "List of file paths, directory paths, or glob patterns identified for "
            "kubectl apply."
        ),
    )
    remaining_request_context: str = Field(
        ...,
        description=(
            "The remaining part of the user's request that is not related to file "
            "selection."
        ),
    )
    model_config = {
        "extra": "forbid",
    }


class LLMFinalApplyPlanResponse(BaseModel):
    """Schema for LLM response containing the final list of planned apply commands."""

    planned_commands: list[CommandAction] = Field(  # Changed from LLMCommandResponse
        ...,
        description=(
            "A list of CommandAction objects, each representing a kubectl "
            "command to be executed."
        ),
    )

    model_config = {
        "extra": "forbid",
    }


# TODO: Add PromptFragment model for typed prompt construction
