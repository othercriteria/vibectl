"""
Prompt definitions for kubectl events commands.

This module contains prompt templates and functions specific to the 'kubectl events'
command for retrieving and analyzing Kubernetes events.
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


@with_planning_prompt_override("events_plan")
def events_plan_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for planning kubectl events commands.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    # Fall back to default prompt (decorator handles plugin override)
    return create_planning_prompt(
        command="events",
        description="Kubernetes events",
        examples=Examples(
            [
                (
                    "events in default namespace",  # Target description
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": ["-n", "default"],
                    },
                ),
                (
                    "events related to nginx",  # Target description
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": ["--field-selector", "involvedObject.name=nginx"],
                    },
                ),
                (
                    "recent events sorted by time",  # Target description
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": ["--sort-by", ".metadata.creationTimestamp"],
                    },
                ),
            ]
        ),
        schema_definition=_SCHEMA_DEFINITION_JSON,
    )


@with_summary_prompt_override("events_resource_summary")
def events_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl events output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    # Fall back to default prompt (decorator handles plugin override)
    return create_summary_prompt(
        description="Summarize these Kubernetes events concisely.",
        focus_points=[
            "critical events",
            "patterns",
            "resource issues",
            "timing patterns",
            "state changes",
        ],
        example_format=[
            "[bold]3 events[/bold] for [blue]nginx deployment[/blue]",
            "[green]Successfully scheduled[/green] pod at [italic]10:15:23[/italic]",
            "[yellow]2 pull warnings[/yellow] for image [code]nginx:latest[/code]",
            "[red]Failed to mount volume[/red] [italic]5 minutes ago[/italic]",
        ],
        config=cfg,
        current_memory=current_memory,
    )
