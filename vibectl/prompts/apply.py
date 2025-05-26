"""
Apply-specific prompts for vibectl apply command.

This module contains prompts specific to the apply functionality,
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

# Template for planning kubectl apply commands
PLAN_APPLY_PROMPT: PromptFragments = create_planning_prompt(
    command="apply",
    description="applying configurations to Kubernetes resources using YAML manifests",
    examples=Examples(
        [
            (
                "apply the deployment from my-deployment.yaml",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["-f", "my-deployment.yaml"],
                    "explanation": "User asked to apply a deployment from a file.",
                },
            ),
            (
                "apply all yaml files in the ./manifests directory",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["-f", "./manifests"],
                    "explanation": "User asked to apply all YAML files in a directory.",
                },
            ),
            (
                "apply the following nginx pod manifest",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["-f", "-"],
                    "explanation": "User asked to apply a provided YAML manifest.",
                    "yaml_manifest": (
                        """---
apiVersion: v1
kind: Pod
metadata:
  name: nginx-applied
spec:
  containers:
  - name: nginx
    image: nginx:latest
    ports:
    - containerPort: 80"""
                    ),
                },
            ),
            (
                "apply the kustomization in ./my-app",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["-k", "./my-app"],
                    "explanation": "User asked to apply a kustomization.",
                },
            ),
            (
                "see what a standard nginx pod would look like",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["--output=yaml", "--dry-run=client", "-f", "-"],
                    "explanation": "A client-side dry-run shows the user a manifest.",
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


# Template for summarizing 'kubectl apply' output
def apply_output_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl apply output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    return create_summary_prompt(
        description="Summarize kubectl apply results.",
        focus_points=[
            "namespace of the resources affected",
            "resources configured, created, or unchanged",
            "any warnings or errors",
            "server-side apply information if present",
        ],
        example_format=[
            "[bold]pod/nginx-applied[/bold] [green]configured[/green]",
            "[bold]deployment/frontend[/bold] [yellow]unchanged[/yellow]",
            "[bold]service/backend[/bold] [green]created[/green]",
            "[red]Error: unable to apply service/broken-svc[/red]: invalid spec",
            "[yellow]Warning: server-side apply conflict for deployment/app[/yellow]",
        ],
        config=cfg,
        current_memory=current_memory,
    )
