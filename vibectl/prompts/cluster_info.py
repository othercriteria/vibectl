"""
Prompt definitions for kubectl cluster-info commands.

This module contains prompt templates and functions specific to the
'kubectl cluster-info' command for retrieving cluster information.
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


@with_planning_prompt_override("cluster_info_plan")
def cluster_info_plan_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for planning kubectl cluster-info commands.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    # Fall back to default prompt (decorator handles plugin override)
    return create_planning_prompt(
        command="cluster-info",
        description="Kubernetes cluster information",
        examples=Examples(
            [
                (
                    "cluster info",  # Target description
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": ["dump"],
                        "explanation": "User asked for cluster info, defaulting "
                        "to dump.",
                    },
                ),
                (
                    "basic cluster info",  # Target description
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": [],
                        "explanation": "User asked for basic cluster info.",
                    },
                ),
                (
                    "detailed cluster info",  # Target description
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": ["dump"],
                        "explanation": "User asked for detailed cluster info (dump).",
                    },
                ),
            ]
        ),
        schema_definition=_SCHEMA_DEFINITION_JSON,
    )


@with_summary_prompt_override("cluster_info_resource_summary")
def cluster_info_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl cluster-info output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    return create_summary_prompt(
        description="Analyze cluster-info output.",
        focus_points=[
            "cluster version",
            "control plane components",
            "add-ons",
            "notable details",
            "potential issues",
        ],
        example_format=[
            "[bold]Kubernetes v1.26.3[/bold] cluster running on "
            "[blue]Google Kubernetes Engine[/blue]",
            "[green]Control plane healthy[/green] at "
            "[italic]https://10.0.0.1:6443[/italic]",
            "[blue]CoreDNS[/blue] and [blue]KubeDNS[/blue] add-ons active",
            "[yellow]Warning: Dashboard not secured with RBAC[/yellow]",
        ],
        config=cfg,
        current_memory=current_memory,
    )
