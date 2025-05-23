"""
Edit-specific prompts for vibectl edit command.

This module contains prompts specific to the edit functionality,
helping to keep the main prompt.py file more manageable.
"""

from vibectl.prompt import (
    _SCHEMA_DEFINITION_JSON,
    ActionType,
    Config,
    Examples,
    PromptFragments,
    create_planning_prompt,
    create_summary_prompt,
)

# Template for planning kubectl edit commands
PLAN_EDIT_PROMPT: PromptFragments = create_planning_prompt(
    command="edit",
    description=(
        "editing Kubernetes resources interactively by opening them in an editor. "
        "IMPORTANT: For vibe mode, always include --output-patch to show what changed, "
        "which provides much better output for summarization."
    ),
    examples=Examples(
        [
            (
                "deployment nginx with vim editor",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": [
                        "deployment",
                        "nginx",
                        "--editor=vim",
                        "--output-patch",
                    ],
                    "explanation": (
                        "User asked to edit deployment with specific editor. "
                        "Using --output-patch to show changes."
                    ),
                },
            ),
            (
                "the frontend service configuration",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["service", "frontend", "--output-patch", "--record"],
                    "explanation": (
                        "User asked to edit service configuration. "
                        "Using --output-patch for better summary and --record to "
                        "track changes."
                    ),
                },
            ),
            (
                "configmap app-config in production namespace",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": [
                        "configmap",
                        "app-config",
                        "-n",
                        "production",
                        "--output-patch",
                    ],
                    "explanation": (
                        "User asked to edit configmap in specific "
                        "namespace. Using --output-patch to show what changed."
                    ),
                },
            ),
            (
                "nginx deployment's resource limits and requests",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["deployment", "nginx", "--output-patch", "--record"],
                    "explanation": "User wants to edit deployment configuration, "
                    "specifically resource limits. Using --output-patch and --record.",
                },
            ),
            (
                "secret database-credentials with nano",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": [
                        "secret",
                        "database-credentials",
                        "--editor=nano",
                        "--output-patch",
                    ],
                    "explanation": "User asked to edit secret with nano editor. "
                    "Using --output-patch to show changes made.",
                },
            ),
            (
                "ingress api-gateway to update host rules",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": [
                        "ingress",
                        "api-gateway",
                        "--output-patch",
                        "--validate=true",
                    ],
                    "explanation": "User wants to edit ingress configuration. "
                    "Using --output-patch and --validate for better feedback.",
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


# Template for summarizing 'kubectl edit' output
def edit_resource_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl edit output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    return create_summary_prompt(
        description="Summarize kubectl edit results, focusing on changes made.",
        focus_points=[
            "resource type and name that was edited",
            "namespace if applicable",
            "whether changes were saved or cancelled",
            "specific fields/values that were changed (from --output-patch if present)",
            "any validation errors or warnings",
            "impact of the changes on resource functionality",
        ],
        example_format=[
            "[bold]deployment.apps/nginx[/bold] [green]edited successfully[/green]",
            "Updated [bold]spec.replicas[/bold] from [red]2[/red] to [green]3[/green]",
            "Added [bold]resources.limits.memory[/bold]: [green]512Mi[/green]",
            "[bold]service/backend[/bold] [yellow]edit cancelled[/yellow] (no changes)",
            "[red]Error: validation failed[/red] for [bold]configmap/app-config[/bold]",
            "[green]Successfully updated[/green] resource limits for [bold]foo[/bold]",
            "[blue]Namespace: production[/blue]",
        ],
        config=cfg,
        current_memory=current_memory,
    )
