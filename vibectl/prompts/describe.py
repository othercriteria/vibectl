"""
Prompt definitions for kubectl describe commands.

This module contains prompt templates and functions specific to the 'kubectl describe'
command for getting detailed information about Kubernetes resources.
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


@with_planning_prompt_override("describe_plan")
def describe_plan_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for planning kubectl describe commands.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    # Fall back to default prompt (decorator handles plugin override)
    return create_planning_prompt(
        command="describe",
        description="Kubernetes resource details",
        examples=Examples(
            [
                (
                    "the nginx pod",  # Target description
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": ["pods", "nginx"],
                        "explanation": "User asked to describe the nginx pod.",
                    },
                ),
                (
                    "the deployment in foo namespace",  # Target description
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": ["deployments", "-n", "foo"],
                        "explanation": "User asked a deployment in a "
                        "specific namespace.",
                    },
                ),
                (
                    "details of all pods with app=nginx",  # Target description
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": ["pods", "--selector=app=nginx"],
                        "explanation": "User requested pods matching a specific label.",
                    },
                ),
            ]
        ),
        schema_definition=_SCHEMA_DEFINITION_JSON,
    )


# Legacy template for backward compatibility
PLAN_DESCRIBE_PROMPT: PromptFragments = create_planning_prompt(
    command="describe",
    description="Kubernetes resource details",
    examples=Examples(
        [
            (
                "the nginx pod",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["pods", "nginx"],
                    "explanation": "User asked to describe the nginx pod.",
                },
            ),
            (
                "the deployment in foo namespace",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["deployments", "-n", "foo"],
                    "explanation": "User asked a deployment in a specific namespace.",
                },
            ),
            (
                "details of all pods with app=nginx",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["pods", "--selector=app=nginx"],
                    "explanation": "User requested pods matching a specific label.",
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


@with_summary_prompt_override("describe_resource_summary")
def describe_resource_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl describe output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    # Fall back to default prompt (decorator handles plugin override)
    return create_summary_prompt(
        description="Summarize this kubectl describe output. Limit to 200 words.",
        focus_points=["key details", "issues needing attention"],
        example_format=[
            "[bold]nginx-pod[/bold] in [blue]default[/blue]: [green]Running[/green]",
            "[yellow]Readiness probe failing[/yellow], "
            "[italic]last restart 2h ago[/italic]",
            "[red]OOMKilled 3 times in past day[/red]",
        ],
        config=cfg,
        current_memory=current_memory,
    )
