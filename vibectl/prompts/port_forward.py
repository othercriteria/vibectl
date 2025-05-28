"""
Prompt definitions for kubectl port-forward commands.

This module contains prompt templates and functions specific to the
'kubectl port-forward' command for forwarding local ports to Kubernetes resources.
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


@with_planning_prompt_override("port_forward_plan")
def port_forward_plan_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for planning kubectl port-forward commands.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    # Fall back to default prompt (decorator handles plugin override)
    return create_planning_prompt(
        command="port-forward",
        description=(
            """port-forward connections to kubernetes resources. IMPORTANT:
            1) Resource name MUST be the first argument,
            2) followed by port specifications,
            3) then any flags. Do NOT include 'kubectl' or '--kubeconfig' in
            your response."""
        ),
        examples=Examples(
            [
                (
                    "port 8080 of pod nginx to my local 8080",
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": ["pod/nginx", "8080:8080"],
                        "explanation": "User asked to port-forward a pod.",
                    },
                ),
                (
                    "the redis service port 6379 on local port 6380",
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": ["service/redis", "6380:6379"],
                        "explanation": "User asked to port-forward a service to a "
                        "different local port.",
                    },
                ),
                (
                    "deployment webserver port 80 to my local 8000",
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": ["deployment/webserver", "8000:80"],
                        "explanation": "User asked to port-forward a deployment.",
                    },
                ),
                (
                    "my local 5000 to port 5000 on the api pod in namespace test",
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": ["pod/api", "5000:5000", "--namespace", "test"],
                        "explanation": "User asked to port-forward pod in "
                        "test namespace.",
                    },
                ),
                (
                    "ports with the app running on namespace production",
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": [
                            "pod/app",
                            "8080:80",
                            "--namespace",
                            "production",
                        ],
                        "explanation": "User asked to port-forward a pod in "
                        "production, assuming default ports.",
                    },
                ),
            ]
        ),
        schema_definition=_SCHEMA_DEFINITION_JSON,
    )


# Legacy constant for backward compatibility - now points to the function result
PLAN_PORT_FORWARD_PROMPT: PromptFragments = port_forward_plan_prompt()


@with_summary_prompt_override("port_forward_resource_summary")
def port_forward_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl port-forward output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    # Fall back to default prompt (decorator handles plugin override)
    return create_summary_prompt(
        description="Summarize this kubectl port-forward output.",
        focus_points=[
            "connection status",
            "port mappings",
            "any errors or issues",
        ],
        example_format=[
            (
                "[green]Connected[/green] to [bold]pod/nginx[/bold] "
                "in [blue]default namespace[/blue]"
            ),
            "Forwarding from [bold]127.0.0.1:8080[/bold] -> [bold]8080[/bold]",
            (
                "[red]Error[/red] forwarding to [bold]service/database[/bold]: "
                "[red]connection refused[/red]"
            ),
        ],
        config=cfg,
        current_memory=current_memory,
    )
