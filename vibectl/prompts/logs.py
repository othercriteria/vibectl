"""
Prompt definitions for kubectl logs commands.

This module contains prompt templates and functions specific to the 'kubectl logs'
command for retrieving and analyzing container logs.
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


@with_planning_prompt_override("logs_plan")
def logs_plan_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for planning kubectl logs commands.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    # Fall back to default prompt (decorator handles plugin override)
    return create_planning_prompt(
        command="logs",
        description="Kubernetes logs",
        examples=Examples(
            [
                (
                    "logs from the nginx pod",
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": ["pod/nginx"],
                        "explanation": "User asked for logs from a specific pod.",
                    },
                ),
                (
                    "logs from the api container in app pod",
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": ["pod/app", "-c", "api"],
                        "explanation": "User asked for pod logs from a specific "
                        "container.",
                    },
                ),
                (
                    "the last 100 lines from all pods with app=nginx",
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": ["--selector=app=nginx", "--tail=100"],
                        "explanation": "User requested some log lines from matching "
                        "pods.",
                    },
                ),
            ]
        ),
        schema_definition=_SCHEMA_DEFINITION_JSON,
    )


@with_summary_prompt_override("logs_resource_summary")
def logs_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl logs output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    # Fall back to default prompt (decorator handles plugin override)
    return create_summary_prompt(
        description="Analyze these container logs concisely.",
        focus_points=[
            "key events",
            "patterns",
            "errors",
            "state changes",
            "note if truncated",
        ],
        example_format=[
            "[bold]Container startup[/bold] at [italic]2024-03-20 10:15:00[/italic]",
            "[green]Successfully connected[/green] to [blue]database[/blue]",
            "[yellow]Slow query detected[/yellow] [italic]10s ago[/italic]",
            "[red]3 connection timeouts[/red] in past minute",
        ],
        config=cfg,
        current_memory=current_memory,
    )
