"""
Prompt definitions for kubectl wait commands.

This module contains prompt templates and functions specific to the
'kubectl wait' command for waiting on Kubernetes resource conditions.
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

# Template for planning kubectl wait commands
PLAN_WAIT_PROMPT: PromptFragments = create_planning_prompt(
    command="wait",
    description="waiting on Kubernetes resources",
    examples=Examples(
        [
            (
                "for the deployment my-app to be ready",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["deployment/my-app", "--for=condition=Available"],
                    "explanation": "User asked to wait on deployment availability.",
                },
            ),
            (
                "until the pod nginx becomes ready with 5 minute timeout",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["pod/nginx", "--for=condition=Ready", "--timeout=5m"],
                    "explanation": "User asked to wait for pod readiness with timeout.",
                },
            ),
            (
                "for all jobs in billing namespace to complete",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": [
                        "jobs",
                        "--all",
                        "-n",
                        "billing",
                        "--for=condition=Complete",
                    ],
                    "explanation": "User asked to wait on all jobs done in namespace.",
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


@with_planning_prompt_override("wait_plan")
def wait_plan_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for planning kubectl wait commands.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    # Fall back to default prompt (decorator handles plugin override)
    return PLAN_WAIT_PROMPT


@with_summary_prompt_override("wait_summary")
def wait_resource_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl wait output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    return create_summary_prompt(
        description="Summarize this kubectl wait output.",
        focus_points=[
            "whether resources met their conditions",
            "timing information",
            "any errors or issues",
        ],
        example_format=[
            (
                "[bold]pod/nginx[/bold] in [blue]default namespace[/blue] "
                "now [green]Ready[/green]"
            ),
            (
                "[bold]Deployment/app[/bold] successfully rolled out after "
                "[italic]35s[/italic]"
            ),
            (
                "[red]Timed out[/red] waiting for "
                "[bold]StatefulSet/database[/bold] to be ready"
            ),
        ],
        config=cfg,
        current_memory=current_memory,
    )
