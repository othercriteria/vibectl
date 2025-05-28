"""
Prompt definitions for kubectl rollout commands.

This module contains prompt templates and functions specific to the
'kubectl rollout' command for managing Kubernetes deployments and rollouts.
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

# Template for planning kubectl rollout commands
PLAN_ROLLOUT_PROMPT: PromptFragments = create_planning_prompt(
    command="rollout",
    description="managing Kubernetes rollouts",
    examples=Examples(
        [
            (
                "status of deployment nginx",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["status", "deployment/nginx"],
                    "explanation": "User asked for the rollout status of a deployment.",
                },
            ),
            (
                "frontend deployment to revision 2",  # rollout action description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["undo", "deployment/frontend", "--to-revision=2"],
                    "explanation": "User asked to roll back to specific revision.",
                },
            ),
            (
                "the rollout of my-app deployment in production namespace",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["pause", "deployment/my-app", "-n", "production"],
                    "explanation": "User asked to pause rollout in a namespace.",
                },
            ),
            (
                "all deployments in default namespace",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": [
                        "restart",
                        "deployment",
                        "-n",
                        "default",
                    ],  # Or add selector if needed
                    "explanation": "User asked to restart deployments in namespace.",
                },
            ),
            (
                "history of statefulset/redis",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["history", "statefulset/redis"],
                    "explanation": "User asked for the rollout history of statefulset.",
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


@with_planning_prompt_override("rollout_plan")
def rollout_plan_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for planning kubectl rollout commands.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    # Fall back to default prompt (decorator handles plugin override)
    return PLAN_ROLLOUT_PROMPT


@with_summary_prompt_override("rollout_status_summary")
def rollout_status_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl rollout status output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    # Fall back to default prompt (decorator handles plugin override)
    return create_summary_prompt(
        description="Summarize rollout status.",
        focus_points=["progress", "completion status", "issues or delays"],
        example_format=[
            "[bold]deployment/frontend[/bold] rollout "
            "[green]successfully completed[/green]",
            "[yellow]Still waiting for 2/5 replicas[/yellow]",
            "[italic]Rollout started 5 minutes ago[/italic]",
        ],
        config=cfg,
        current_memory=current_memory,
    )


@with_summary_prompt_override("rollout_history_summary")
def rollout_history_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl rollout history output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    # Fall back to default prompt (decorator handles plugin override)
    return create_summary_prompt(
        description="Summarize rollout history.",
        focus_points=[
            "key revisions",
            "important changes",
            "patterns across revisions",
        ],
        example_format=[
            "[bold]deployment/app[/bold] has [blue]5 revision history[/blue]",
            "[green]Current active: revision 5[/green] (deployed 2 hours ago)",
            "[yellow]Revision 3 had frequent restarts[/yellow]",
        ],
        config=cfg,
        current_memory=current_memory,
    )


@with_summary_prompt_override("rollout_general_summary")
def rollout_general_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl rollout output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    # Fall back to default prompt (decorator handles plugin override)
    return create_summary_prompt(
        description="Summarize rollout command results.",
        focus_points=["key operation details"],
        example_format=[
            "[bold]Deployment rollout[/bold] [green]successful[/green]",
            "[blue]Updates applied[/blue] to [bold]my-deployment[/bold]",
            "[yellow]Warning: rollout took longer than expected[/yellow]",
        ],
        config=cfg,
        current_memory=current_memory,
    )
