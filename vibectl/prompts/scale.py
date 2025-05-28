"""
Prompt definitions for kubectl scale commands.

This module contains prompt templates and functions specific to the 'kubectl scale'
command for scaling Kubernetes resources.
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

# Template for planning kubectl scale commands
PLAN_SCALE_PROMPT: PromptFragments = create_planning_prompt(
    command="scale",
    description="scaling Kubernetes resources",
    examples=Examples(
        [
            (
                "deployment nginx to 3 replicas",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["deployment/nginx", "--replicas=3"],
                    "explanation": "User asked to scale a deployment to 3 replicas.",
                },
            ),
            (
                "the redis statefulset to 5 replicas in the cache namespace",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["statefulset/redis", "--replicas=5", "-n", "cache"],
                    "explanation": "User asked to scale statefulset in namespace.",
                },
            ),
            (
                "down the api deployment",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": [
                        "deployment/api",
                        "--replicas=1",
                    ],  # Assuming scale down means 1
                    "explanation": "User asked to scale down a deployment, "
                    "defaulting to 1 replica.",
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


@with_planning_prompt_override("scale_plan")
def scale_plan_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for planning kubectl scale commands.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    # Fall back to default prompt (decorator handles plugin override)
    return PLAN_SCALE_PROMPT


@with_summary_prompt_override("scale_summary")
def scale_resource_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl scale output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    return create_summary_prompt(
        description="Summarize scaling operation results.",
        focus_points=["changes made", "current state", "issues or concerns"],
        example_format=[
            "[bold]deployment/nginx[/bold] scaled to [green]3 replicas[/green]",
            "[yellow]Warning: Scale operation might take time to complete[/yellow]",
            "[blue]Namespace: default[/blue]",
        ],
        config=cfg,
        current_memory=current_memory,
    )
