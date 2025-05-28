"""
Prompt definitions for kubectl patch commands.

This module contains prompt templates and functions specific to the
'kubectl patch' command for patching Kubernetes resources.
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


@with_planning_prompt_override("patch_plan")
def patch_plan_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for planning kubectl patch commands.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    # Fall back to default prompt (decorator handles plugin override)
    return create_planning_prompt(
        command="patch",
        description=(
            "patching Kubernetes resources with strategic merge patches, "
            "JSON merge patches, or JSON patches"
        ),
        examples=Examples(
            [
                (
                    "scale nginx deployment to 5 replicas",
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": [
                            "deployment",
                            "nginx",
                            "-p",
                            '{"spec":{"replicas":5}}',
                        ],
                        "explanation": (
                            "User asked to patch deployment replicas "
                            "using strategic merge patch."
                        ),
                    },
                ),
                (
                    "update container image to nginx:1.21 in my-app deployment",
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": [
                            "deployment",
                            "my-app",
                            "-p",
                            '{"spec":{"template":{"spec":{"containers":[{"name":"my-app","image":"nginx:1.21"}]}}}}',
                        ],
                        "explanation": "User asked to patch container image "
                        "in deployment.",
                    },
                ),
                (
                    "add label environment=prod to service web-service",
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": [
                            "service",
                            "web-service",
                            "-p",
                            '{"metadata":{"labels":{"environment":"prod"}}}',
                        ],
                        "explanation": "User asked to patch service metadata labels.",
                    },
                ),
                (
                    "patch deployment from file my-patch.yaml",
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": [
                            "deployment",
                            "nginx",
                            "--patch-file",
                            "my-patch.yaml",
                        ],
                        "explanation": "User asked to patch using a patch file.",
                    },
                ),
                (
                    "remove finalizer from namespace stuck-namespace",
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": [
                            "namespace",
                            "stuck-namespace",
                            "--type",
                            "json",
                            "-p",
                            '[{"op": "remove", "path": "/metadata/finalizers"}]',
                        ],
                        "explanation": "User asked to remove finalizers "
                        "using JSON patch.",
                    },
                ),
            ]
        ),
        schema_definition=_SCHEMA_DEFINITION_JSON,
    )


@with_summary_prompt_override("patch_resource_summary")
def patch_resource_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl patch output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    # Fall back to default prompt (decorator handles plugin override)
    return create_summary_prompt(
        description="Summarize kubectl patch results.",
        focus_points=[
            "resource type and name that was patched",
            "namespace if applicable",
            "patch type used (strategic merge, JSON merge, JSON patch)",
            "changes that were applied",
            "any warnings or errors",
        ],
        example_format=[
            "[bold]deployment.apps/nginx[/bold] [green]patched[/green]",
            "[bold]service/web-service[/bold] [green]patched[/green] with labels",
            "[yellow]Warning: strategic merge patch replaced array[/yellow]",
            "[red]Error: patch failed[/red]: cannot change immutable field",
            "[blue]Namespace: production[/blue]",
        ],
        config=config,
        current_memory=current_memory,
    )
