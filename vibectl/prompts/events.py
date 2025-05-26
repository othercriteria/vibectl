"""
Prompt definitions for kubectl events commands.

This module contains prompt templates and functions specific to the 'kubectl events'
command for retrieving and analyzing Kubernetes events.
"""

from vibectl.config import Config
from vibectl.schema import ActionType
from vibectl.types import Examples, PromptFragments

from .schemas import _SCHEMA_DEFINITION_JSON
from .shared import create_planning_prompt, create_summary_prompt

# Template for planning kubectl events commands
# more idiomatic command for viewing events and offers specific flags like --for.
PLAN_EVENTS_PROMPT: PromptFragments = create_planning_prompt(
    command="events",  # Use the dedicated 'events' command
    description="Kubernetes events",
    examples=Examples(
        [
            (
                "events in default namespace",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": [],  # Default namespace is implicit
                    "explanation": "User asked for events in the default namespace.",
                },
            ),
            (
                "events for pod nginx",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["--for=pod/nginx"],
                    "explanation": "User asked for events related to a specific pod.",
                },
            ),
            (
                "all events in all namespaces",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["--all-namespaces"],  # Use -A or --all-namespaces
                    "explanation": "User asked for all events across all namespaces.",
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


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
    return create_summary_prompt(
        description="Analyze these Kubernetes events concisely.",
        focus_points=[
            "recent events",
            "patterns",
            "warnings",
            "notable issues",
            "group related events",
        ],
        example_format=[
            "[bold]12 events[/bold] in the last [italic]10 minutes[/italic]",
            "[green]Successfully scheduled[/green] pods: [bold]nginx-1[/bold], "
            "[bold]nginx-2[/bold]",
            "[yellow]ImagePullBackOff[/yellow] for [bold]api-server[/bold]",
            "[italic]5 minutes ago[/italic]",
            "[red]OOMKilled[/red] events for [bold]db-pod[/bold], "
            "[italic]happened 3 times[/italic]",
        ],
        config=cfg,
        current_memory=current_memory,
    )


__all__ = [
    "PLAN_EVENTS_PROMPT",
    "events_prompt",
]
