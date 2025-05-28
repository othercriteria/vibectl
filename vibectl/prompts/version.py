"""
Prompt definitions for kubectl version commands.

This module contains prompt templates and functions specific to the 'kubectl version'
command for retrieving Kubernetes version information.
"""

from vibectl.config import Config
from vibectl.schema import ActionType
from vibectl.types import Examples, PromptFragments

from .schemas import _SCHEMA_DEFINITION_JSON
from .shared import (
    create_planning_prompt,
    create_summary_prompt,
    with_planning_prompt_override,
    with_summary_prompt_override,
)

# Template for planning kubectl version commands
PLAN_VERSION_PROMPT: PromptFragments = create_planning_prompt(
    command="version",
    description="Kubernetes version information",
    examples=Examples(
        [
            (
                "version in json format",  # Target/flag description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["--output=json"],
                    "explanation": "User requested version in JSON format.",
                },
            ),
            (
                "client version only",  # Target/flag description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["--client=true", "--output=json"],
                    "explanation": "User requested client version only, JSON format.",
                },
            ),
            (
                "version in yaml",  # Target/flag description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["--output=yaml"],
                    "explanation": "User requested version in YAML format.",
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


@with_planning_prompt_override("version_plan")
def version_plan_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for planning kubectl version commands.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    # Fall back to default prompt (decorator handles plugin override)
    return PLAN_VERSION_PROMPT


@with_summary_prompt_override("version_summary")
def version_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl version output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    return create_summary_prompt(
        description="Interpret Kubernetes version details in a human-friendly way.",
        focus_points=[
            "version compatibility",
            "deprecation notices",
            "update recommendations",
        ],
        example_format=[
            "[bold]Kubernetes v1.26.3[/bold] client and [bold]v1.25.4[/bold] server",
            "[green]Compatible versions[/green] with [italic]patch available[/italic]",
            "[blue]Server components[/blue] all [green]up-to-date[/green]",
            "[yellow]Client will be deprecated in 3 months[/yellow]",
        ],
        config=cfg,
        current_memory=current_memory,
    )
