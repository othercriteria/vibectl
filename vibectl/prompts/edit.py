"""
Edit-specific prompts for vibectl edit command.

This module contains prompts specific to the edit functionality,
helping to keep the main prompt.py file more manageable.
"""

from vibectl.config import Config
from vibectl.prompts.schemas import (
    _EDIT_RESOURCESCOPE_SCHEMA_JSON,
    _SCHEMA_DEFINITION_JSON,
)
from vibectl.prompts.shared import (
    create_planning_prompt,
    create_summary_prompt,
    fragment_current_time,
    fragment_json_schema_instruction,
    fragment_memory_context,
    with_custom_prompt_override,
    with_planning_prompt_override,
    with_summary_prompt_override,
)
from vibectl.schema import ActionType
from vibectl.types import (
    Examples,
    Fragment,
    PromptFragments,
    SystemFragments,
    UserFragments,
)


@with_planning_prompt_override("edit_plan")
def edit_plan_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for planning kubectl edit commands.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    # Fall back to default prompt (decorator handles plugin override)
    return create_planning_prompt(
        command="edit",
        description=(
            "editing Kubernetes resources interactively by opening them in an editor. "
            "IMPORTANT: For vibe mode, always include --output-patch to show what "
            "changed, which provides much better output for summarization."
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


@with_summary_prompt_override("edit_resource_summary")
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
            "specific fields/values that were changed",
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


@with_custom_prompt_override("edit_resource_summarization")
def get_resource_summarization_prompt(
    custom_mapping: object,
    resource_yaml: str,
    resource_kind: str,
    resource_name: str,
    edit_context: str | None = None,
) -> PromptFragments:
    """Get prompt for summarizing Kubernetes resource YAML as editable natural language.

    Args:
        custom_mapping: Custom mapping object from plugin (if any)
        resource_yaml: The YAML content of the resource
        resource_kind: The kind of the resource (e.g., "Deployment", "Service")
        resource_name: The name of the resource
        edit_context: Optional context about what aspects to focus on during editing

    Returns:
        PromptFragments with all placeholders substituted
    """
    # Get custom mapping attributes, if provided
    task_description = getattr(custom_mapping, "task_description", "")
    context_instructions = getattr(custom_mapping, "context_instructions", "")

    # Fall back to default implementation
    return create_resource_summarization_prompt(
        resource_yaml,
        resource_kind,
        resource_name,
        edit_context,
        task_description=task_description,
        context_instructions=context_instructions,
    )


def create_resource_summarization_prompt(
    resource_yaml: str,
    resource_kind: str,
    resource_name: str,
    edit_context: str | None = None,
    task_description: str = "",
    context_instructions: str = "",
) -> PromptFragments:
    """Create prompts summarizing Kubernetes resource YAML as editable natural language.

    Args:
        resource_yaml: The YAML content of the resource
        resource_kind: The kind of the resource (e.g., "Deployment", "Service")
        resource_name: The name of the resource
        edit_context: Optional context about what aspects to focus on during editing
        task_description: Custom task description from plugin
        context_instructions: Custom context instructions from plugin

    Returns:
        PromptFragments with placeholders already substituted
    """
    system_fragments: SystemFragments = SystemFragments([])
    user_fragments: UserFragments = UserFragments([])

    # System: Core task description
    system_fragments.append(
        Fragment(task_description)
        or Fragment("""
You are an expert Kubernetes operations assistant. Your task is to
convert Kubernetes resource YAML into a clear, natural language summary
that users can easily edit to make configuration changes.

Create a summary that:
- Focuses on commonly edited configuration aspects
- Uses clear, non-technical language where possible
- Highlights key fields users typically want to modify
- Provides context for configuration options
- Organizes information logically for editing
""")
    )

    # System: Plain text formatting instructions
    system_fragments.append(
        Fragment("""
Format your response as plain text (not JSON, YAML, Markdown, etc.) suitable for
editing in a text editor:
- Use simple formatting like bullet points and numbered lists
- Structure the summary with clear sections and use simple language
- Aim to fit on a classic 80x24 terminal screen
""")
    )

    # User fragments with substitutions already applied
    user_fragments.append(Fragment(f"Resource to summarize:\n\n{resource_yaml}"))

    # Customize the user instruction based on edit context
    if edit_context:
        user_instruction = (
            f"Create a summary for this {resource_kind} "
            f"named '{resource_name}', specifically focused on: {edit_context}. "
        )
    else:
        user_instruction = (
            f"Create a summary for this {resource_kind} named '{resource_name}'."
        )

    if context_instructions:
        user_instruction += f"\n\n{context_instructions}"

    user_fragments.append(Fragment(user_instruction))

    return PromptFragments((system_fragments, user_fragments))


@with_planning_prompt_override("edit_patch_generation")
def patch_generation_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for generating kubectl patch commands from summary diff.

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
            "analyzing unified diffs of resource summaries and generating appropriate "
            "kubectl patch commands to implement those changes. You will receive the "
            "original summary for context and a unified diff showing the specific "
            "changes. Focus on the changes indicated in the diff. "
            "Always use strategic merge patches unless JSON patch is "
            "specifically needed."
        ),
        examples=Examples(
            [
                (
                    "diff shows replicas changed from 3 to 5",
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": [
                            "deployment",
                            "nginx",
                            "-p",
                            '{"spec":{"replicas":5}}',
                        ],
                        "explanation": (
                            "Diff indicates replica count increase from 3 to 5. Using "
                            "strategic merge patch to update the replicas field."
                        ),
                    },
                ),
                (
                    "diff shows image updated from nginx:1.20 to nginx:1.21 and "
                    "memory limit added as 512Mi",
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": [
                            "deployment",
                            "nginx",
                            "-p",
                            '{"spec": {"template": {"spec": {"containers": ['
                            '{"name": "nginx", '
                            '"image": "nginx:1.21", '
                            '"resources": {"limits": {"memory": "512Mi"}}'
                            "}]}}}}",
                        ],
                        "explanation": (
                            "Diff shows image version update and memory limit "
                            "addition. Using strategic merge patch to update both "
                            "container image and resource limits."
                        ),
                    },
                ),
            ]
        ),
        schema_definition=_SCHEMA_DEFINITION_JSON,
    )


@with_custom_prompt_override("edit_scope_planning")
def plan_edit_scope(
    custom_mapping: object,
    request: str,
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for planning kubectl edit resource scoping."""
    # Get custom mapping attributes, if provided
    task_description = getattr(custom_mapping, "task_description", "")
    examples = getattr(custom_mapping, "examples", "")
    context_instructions = getattr(custom_mapping, "context_instructions", "")

    # TODO: Make this consistent with other prompts by using get_formatting_fragments()
    # instead of manually adding memory/custom_instructions/time. This will be done
    # in a broader refactoring, not in this feature branch.

    cfg = config or Config()

    system_frags = SystemFragments([])

    # Core task description
    system_frags.extend(
        [
            Fragment(task_description)
            or Fragment(
                """You are an expert Kubernetes assistant. Your task is to analyze
            the user's request for `kubectl edit` and extract three things:

            1. **Resource Selectors**: The specific resources to edit (e.g.,
               'deployment/nginx', 'service frontend', 'pods --selector=app=web')

            2. **Kubectl Arguments**: Any kubectl flags or options that should be
               passed to the kubectl edit command (e.g., '-n staging', '--editor=vim',
               '--output-patch'). Do NOT include resource specifications here.

            3. **Edit Context**: The semantic meaning of what the user wants to
               edit or focus on (e.g., 'readiness and liveness checks', 'resource
               limits', 'environment variables'). This helps guide the intelligent
               editing process but is not passed to kubectl.

            Be liberal in interpreting natural language - extract the intent even
            if the phrasing is informal or incomplete."""
            ),
            fragment_json_schema_instruction(
                _EDIT_RESOURCESCOPE_SCHEMA_JSON, "the EditResourceScopeResponse"
            ),
        ]
    )

    # Add custom instructions if available
    custom_instructions = cfg.get("custom_instructions")
    if custom_instructions:
        system_frags.append(Fragment(f"Custom instructions:\n{custom_instructions}"))

    # Add memory context if provided and not empty
    if current_memory and current_memory.strip():
        system_frags.append(fragment_memory_context(current_memory))

    # Add current time
    system_frags.append(fragment_current_time())

    # User context instructions
    base_context = f"""User Request: {request}

                Please provide your analysis in JSON format, adhering to the
                EditResourceScopeResponse schema previously defined.

                Examples:
                - "nginx deployment readiness checks" ->
                  resource_selectors: ["deployment/nginx"],
                  kubectl_arguments: [],
                  edit_context: "readiness checks"

                - "edit frontend service in staging namespace" ->
                  resource_selectors: ["service/frontend"],
                  kubectl_arguments: ["-n", "staging"],
                  edit_context: "general service configuration"

                - "pods with app=web label using vim editor" ->
                  resource_selectors: ["pods --selector=app=web"],
                  kubectl_arguments: ["--editor=vim"],
                  edit_context: "general pod configuration"

                Focus on extracting the user's intent clearly and precisely."""

    if examples:
        base_context += f"\n\nAdditional examples:\n{examples}"

    if context_instructions:
        base_context += f"\n\n{context_instructions}"

    user_frags = UserFragments([Fragment(base_context)])
    return PromptFragments((system_frags, user_frags))


@with_summary_prompt_override("edit_patch_summary")
def patch_summary_prompt(
    config: Config | None = None, current_memory: str | None = None
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl patch output from intelligent edit.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    return create_summary_prompt(
        description="Summarize kubectl patch results from intelligent edit.",
        focus_points=[
            "resource modified",
            "specific changes applied",
            "any warnings or errors",
            "impact of the changes",
        ],
        example_format=[
            "[bold]deployment/nginx[/bold] [green]successfully updated[/green]",
            "Added [bold]CPU requests[/bold]: [green]500m[/green]",
            "[yellow]Warning: Rolling update in progress[/yellow]",
        ],
        config=config,
        current_memory=current_memory,
    )


# Function to get complete patch generation prompt with context
def get_patch_generation_prompt(
    resource: str,
    args: tuple[str, ...],
    original_summary: str,
    summary_diff: str,
    original_yaml: str,
) -> PromptFragments:
    """Get prompt fragments for generating kubectl patch commands from summary diff.

    Args:
        resource: The resource identifier (e.g., "deployment/nginx")
        args: Additional kubectl arguments from original command
        original_summary: The original natural language summary (TODO: do we need this?)
        summary_diff: Unified diff showing changes between original and edited summaries
        original_yaml: The original YAML configuration

    Returns:
        PromptFragments with all context included
    """
    system_fragments, user_fragments_base = patch_generation_prompt()

    # Build complete user fragments with context
    user_fragments = list(user_fragments_base)
    user_fragments.append(
        Fragment(
            f"Generate kubectl patch command(s) for resource '{resource}' to implement "
            "the changes shown in the diff below. The original summary is provided for "
            "context, but focus on the specific changes indicated in the diff. "
        )
    )
    user_fragments.append(Fragment(f"Original summary:\n{original_summary}"))
    user_fragments.append(
        Fragment(f"Changes requested (unified diff):\n```diff\n{summary_diff}\n```")
    )
    user_fragments.append(
        Fragment(f"Original resource configuration:\n```yaml\n{original_yaml}\n```")
    )
    user_fragments.append(
        Fragment(
            "You should *strongly* prefer to return a COMMAND action, but if this is "
            "not possible, return an ERROR action with an appropriate error message. "
            "When composing the COMMAND action, make sure these additional arguments "
            "are included: "
            f"{' '.join(args)}"
        )
    )

    return PromptFragments((system_fragments, UserFragments(user_fragments)))
