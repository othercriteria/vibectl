"""
Prompt definitions for kubectl diff commands.

This module contains prompt templates and functions specific to the
'kubectl diff' command for comparing configurations against cluster state.
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


@with_planning_prompt_override("diff_plan")
def diff_plan_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for planning kubectl diff commands.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    # Fall back to default prompt (decorator handles plugin override)
    return create_planning_prompt(
        command="diff",
        description="diff'ing a specified configuration against the live cluster state",
        examples=Examples(
            [
                (
                    "server-side diff for local file examples/my-app.yaml",
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": ["--server-side=true", "-f", "my-app.yaml"],
                        "allowed_exit_codes": [0, 1],
                        "explanation": "User asked for a server-side diff of "
                        "a local file.",
                    },
                ),
                (
                    "diff the manifest at https://foo.com/manifests/pod.yaml",
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": ["-f", "https://foo.com/manifests/pod.yaml"],
                        "allowed_exit_codes": [0, 1],
                        "explanation": "User asked to diff a manifest from a URL.",
                    },
                ),
                (
                    "diff a generated minimal nginx deployment in staging",
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": ["-n", "staging", "-f", "-"],
                        "explanation": "User asked to diff generated manifest "
                        "in staging.",
                        "yaml_manifest": (
                            """---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-minimal-diff
  namespace: staging
spec:
  replicas: 1
  selector:
    matchLabels:
      app: nginx-diff
  template:
    metadata:
      labels:
        app: nginx-diff
    spec:
      containers:
      - name: nginx
        image: nginx:alpine
        ports:
        - containerPort: 80"""
                        ),
                        "allowed_exit_codes": [0, 1],
                    },
                ),
            ]
        ),
        schema_definition=_SCHEMA_DEFINITION_JSON,
    )


@with_summary_prompt_override("diff_resource_summary")
def diff_output_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl diff output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    return create_summary_prompt(
        description="Summarize this kubectl diff output, highlighting changes.",
        focus_points=[
            "resources with detected differences",
            "type of change (modified, added, deleted - infer from diff context)",
            "key fields that were changed (e.g., image, replicas, data keys)",
            "newly added or removed resources",
        ],
        example_format=[
            "[bold]ConfigMap/foo[/bold] in [blue]bar[/blue] [yellow]modified[/yellow]:",
            "  - Field [bold]data.key1[/bold] changed from 'old_value' to 'new_value'",
            "  - Added field [bold]data.new_key[/bold]: 'some_value'",
            "[bold]Deployment/baz[/bold] in [blue]qa[/blue] [green]added[/green]",
            "  - Image: [bold]nginx:latest[/bold]",
            "  - Replicas: [bold]3[/bold]",
            "[bold]Secret/old[/bold] in [blue]dev[/blue] [red]removed[/red]",
            "Summary: [bold]1 ConfigMap modified[/bold], ...",
        ],
        config=cfg,
        current_memory=current_memory,
    )
