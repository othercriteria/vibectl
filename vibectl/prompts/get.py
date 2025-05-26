"""
Prompt definitions for kubectl get commands.

This module contains prompt templates and functions specific to the 'kubectl get'
command for retrieving and summarizing Kubernetes resources.
"""

from vibectl.config import Config
from vibectl.schema import ActionType
from vibectl.types import Examples, PromptFragments

from .schemas import _SCHEMA_DEFINITION_JSON
from .shared import create_planning_prompt, create_summary_prompt

# Template for planning kubectl get commands
PLAN_GET_PROMPT: PromptFragments = create_planning_prompt(
    command="get",
    description="getting Kubernetes resources",
    examples=Examples(
        [
            (
                "pods in kube-system",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["pods", "-n", "kube-system"],
                },
            ),
            (
                "pods with app=nginx label",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["pods", "--selector=app=nginx"],
                },
            ),
            (
                "all pods in every namespace",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["pods", "--all-namespaces"],
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


def get_resource_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl get output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    return create_summary_prompt(
        description="Summarize this kubectl output.",
        focus_points=["key information", "notable patterns", "potential issues"],
        example_format=[
            "[bold]3 pods[/bold] in [blue]default namespace[/blue], all "
            "[green]Running[/green]",
            "[bold]nginx-pod[/bold] [italic]running for 2 days[/italic]",
            "[yellow]Warning: 2 pods have high restart counts[/yellow]",
        ],
        config=cfg,
        current_memory=current_memory,
    )


__all__ = [
    "PLAN_GET_PROMPT",
    "get_resource_prompt",
]
