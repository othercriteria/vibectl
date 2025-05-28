"""
Prompt definitions for kubectl delete commands.

This module contains prompt templates and functions specific to the 'kubectl delete'
command for removing Kubernetes resources.
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

# Template for planning kubectl delete commands
PLAN_DELETE_PROMPT: PromptFragments = create_planning_prompt(
    command="delete",
    description="Kubernetes resources",
    examples=Examples(
        [
            (
                "the nginx pod",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["pod", "nginx"],
                    "explanation": "User asked to delete a specific pod.",
                },
            ),
            (
                "deployment in kube-system namespace",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["deployment", "-n", "kube-system"],
                    "explanation": "User asked to delete deployment in namespace.",
                },
            ),
            (
                "all pods with app=nginx",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["pods", "--selector=app=nginx"],
                    "explanation": ("User asked to delete all pods matching a label."),
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


@with_planning_prompt_override("delete_plan")
def delete_plan_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for planning kubectl delete commands.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    # Fall back to default prompt (decorator handles plugin override)
    return create_planning_prompt(
        command="delete",
        description="Kubernetes resources",
        examples=Examples(
            [
                (
                    "the nginx pod",  # Target description
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": ["pod", "nginx"],
                        "explanation": "User asked to delete a specific pod.",
                    },
                ),
                (
                    "deployment in kube-system namespace",  # Target description
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": ["deployment", "-n", "kube-system"],
                        "explanation": "User asked to delete deployment in namespace.",
                    },
                ),
                (
                    "all pods with app=nginx",  # Target description
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": ["pods", "--selector=app=nginx"],
                        "explanation": (
                            "User asked to delete all pods matching a label."
                        ),
                    },
                ),
            ]
        ),
        schema_definition=_SCHEMA_DEFINITION_JSON,
    )


@with_summary_prompt_override("delete_resource_summary")
def delete_resource_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl delete output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    return create_summary_prompt(
        description="Summarize kubectl delete results.",
        focus_points=["resources deleted", "potential issues", "warnings"],
        example_format=[
            "[bold]3 pods[/bold] successfully deleted from "
            "[blue]default namespace[/blue]",
            "[yellow]Warning: Some resources are still terminating[/yellow]",
        ],
        config=cfg,
        current_memory=current_memory,
    )
