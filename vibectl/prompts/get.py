"""
Prompt definitions for kubectl get commands.

This module contains prompt templates and functions specific to the 'kubectl get'
command for retrieving and summarizing Kubernetes resources.
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


@with_planning_prompt_override("get_plan")
def get_plan_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for planning kubectl get commands.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    # Fall back to default prompt (decorator handles plugin override)
    return create_planning_prompt(
        command="get",
        description="Kubernetes resources",
        examples=Examples(
            [
                (
                    "pods in default namespace",  # Target description
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": ["pods", "-n", "default"],
                        "explanation": "User asked for pods in a specific namespace.",
                    },
                ),
                (
                    "all services with labels",  # Target description
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": [
                            "services",
                            "--show-labels",
                            "--all-namespaces",
                        ],
                        "explanation": "User asked for services with labels across "
                        "all namespaces.",
                    },
                ),
                (
                    "deployment nginx with yaml output",  # Target description
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": ["deployment", "nginx", "-o", "yaml"],
                        "explanation": "User asked for a specific deployment in "
                        "YAML format.",
                    },
                ),
            ]
        ),
        schema_definition=_SCHEMA_DEFINITION_JSON,
    )


@with_summary_prompt_override("get_resource_summary")
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
    # Fall back to default prompt (decorator handles plugin override)
    return create_summary_prompt(
        description="Summarize this Kubernetes resource information concisely.",
        focus_points=[
            "resource status",
            "availability",
            "notable conditions",
            "key metadata",
            "relationships",
        ],
        example_format=[
            "[bold]3 pods[/bold] in [blue]nginx namespace[/blue]",
            "[green]2 running[/green], [yellow]1 pending[/yellow]",
            "[italic]nginx-7d5c[/italic]: Ready, [green]up 2d[/green]",
            "[italic]nginx-8f4b[/italic]: [red]ImagePullBackOff[/red]",
        ],
        config=cfg,
        current_memory=current_memory,
    )
