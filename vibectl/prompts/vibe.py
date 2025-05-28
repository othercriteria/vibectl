"""
Prompt templates for vibe-specific LLM interactions.

This module contains prompts for:
- Autonomous vibe command planning
- Vibe command output summarization
"""

from __future__ import annotations

from typing import Any

from vibectl.config import Config
from vibectl.schema import ActionType
from vibectl.types import (
    Examples,
    Fragment,
    MLExampleItem,
    PromptFragments,
    SystemFragments,
    UserFragments,
)

from .schemas import _SCHEMA_DEFINITION_JSON
from .shared import (
    create_planning_prompt,
    format_ml_examples,
    fragment_memory_context,
    get_formatting_fragments,
    with_custom_prompt_override,
    with_summary_prompt_override,
)


# Template for planning autonomous vibe commands
@with_custom_prompt_override("vibe_plan")
def plan_vibe_fragments(custom_mapping: Any = None) -> PromptFragments:
    """Get prompt fragments for planning autonomous vibe commands.

    Args:
        custom_mapping: Plugin mapping with custom instructions (may be None)

    Returns:
        PromptFragments: System fragments and base user fragments.
                         Caller adds memory and request fragments.
    """
    # Handle custom plugin mapping if provided
    if custom_mapping:
        # Use the plugin-provided custom mapping
        # Get values from custom mapping with fallbacks
        command = custom_mapping.get("command", "vibe")
        description = custom_mapping.get("description", "autonomous vibe commands")
        examples_data = custom_mapping.get("examples", [])

        examples = Examples(examples_data)

        # Use the standard planning prompt creation with custom data
        return create_planning_prompt(
            command=command,
            description=description,
            examples=examples,
            schema_definition=_SCHEMA_DEFINITION_JSON,
        )

    # Default implementation (existing code)
    system_fragments: SystemFragments = SystemFragments([])
    user_fragments: UserFragments = UserFragments(
        []
    )  # Base user fragments, caller adds dynamic ones

    # System: Core instructions and role
    system_fragments.append(
        Fragment("""
You are a highly agentic and capable AI assistant delegated to work for a user
in a Kubernetes cluster.

Your will return a single action object, which can be one of:
- COMMAND: execute a single kubectl command, to directly advance the user's goal or
  reduce uncertainty about the user's goal and its status.
- THOUGHT: record a thought or reasoning step, to improve your working memory.
- FEEDBACK: return feedback to the user explaining uncertainty about the user's goal
  that you cannot reduce by planning a COMMAND, and soliciting clarification.
- WAIT: pause further work, for (at least) some specified duration.
- DONE: (Primarily for 'vibectl check') signal that the predicate evaluation is complete
  and provide an exit code.
- ERROR: you cannot or should not act otherwise.

All actions will update working memory, so THOUGHT and FEEDBACK are only needed
if you must make specific changes to the memory context.

You may be in a non-interactive context, so do NOT plan blocking commands like
'kubectl wait' or 'kubectl port-forward' or 'kubectl get --watch' unless given an
explicit request to the contrary, and even then use appropriate timeouts.

You cannot run arbitrary shell commands, but a COMMAND planning appropriate
`kubectl exec` commands to run inside pods may be appropriate.""")
    )

    # System: Schema definition (f-string needed here)
    system_fragments.append(
        Fragment(
            f"""Your response MUST be a valid JSON object conforming to the
LLMPlannerResponse schema:
```json
{_SCHEMA_DEFINITION_JSON}
```

Example structure for a COMMAND action:
{{
  "action": {{
    "action_type": "COMMAND",
    "commands": ["get", "pods", "-n", "app"],
    "yaml_manifest": null, // or YAML string
    "allowed_exit_codes": [0],
    "explanation": "The user's goal is to check the pods in the 'app' namespace."
  }}
}}

Key fields for each Action Type within the "action" object:

1.  `action_type`: "COMMAND", "THOUGHT", "FEEDBACK", "ERROR", "WAIT", or "DONE".

2.  If `action_type` is "COMMAND":
    - `commands` (list of strings, required if no `yaml_manifest`): The *full* kubectl
      subcommand *including the verb* (e.g., ["get", "pods", "-n", "app"]).
    - `yaml_manifest` (string, optional): YAML content if creating/applying complex
      resources.
    - `allowed_exit_codes` (list of int, optional): Allowed exit codes for the
      command (e.g., [0, 1] for diff). Defaults to [0].
    - `explanation` (string, optional): Reasoning for why this specific command is the
      next best step towards the user's goal.

3.  If `action_type` is "THOUGHT":
    - `text` (string, required): The textual content of your thought.

4.  If `action_type` is "FEEDBACK":
    - `message` (string, required): Textual feedback to the user.
    - `explanation` (string, optional): Reasoning for providing this feedback (e.g.,
      why clarification is needed).
    - `suggestion` (string, optional): A suggested change to the memory context to
      help clarify the request or situation.

5.  If `action_type` is "WAIT":
    - `duration_seconds` (int, required): Duration in seconds to wait.

6.  If `action_type` is "DONE":
    - `exit_code` (int, optional): The intended exit code for vibectl.
      Defaults to 3 ('cannot determine') if not provided for 'vibectl check'.

7.  If `action_type` is "ERROR":
    - `message` (string, required): Description of why you cannot plan a command
      or why the request is problematic.

Remember to choose only ONE action per response."""
        )
    )

    # System: Examples
    vibe_examples_data: list[MLExampleItem] = [
        (
            "We are working in namespace 'app'. Deployed 'frontend' and "
            "'backend' services.",
            "check if everything is healthy",
            {
                "action_type": str(ActionType.COMMAND.value),
                "commands": ["get", "pods", "-n", "app"],
                "explanation": "Viewing pods in 'app' namespace, as first step in "
                "overall check.",
            },
        ),
        (
            "The health-check pod is called 'health-check'.",
            "Tell me about the health-check pod and the database deployment.",
            {
                "action_type": str(ActionType.COMMAND.value),
                "commands": ["get", "pods", "-l", "app=health-check"],
                "explanation": "Addressing the health-check pod first; database "
                "deployment next...",
            },
        ),
        (
            "",
            "What are the differences for my-deployment.yaml?",
            {
                "action_type": str(ActionType.COMMAND.value),
                "commands": ["diff", "-f", "my-deployment.yaml"],
                "allowed_exit_codes": [0, 1],
                "explanation": "User wants a diff for my-deployment.yaml. (Exit code "
                "1 is normal.)",
            },
        ),
        (
            "We need to debug why the database pod keeps crashing.",
            "",  # Empty request, relying on memory
            {
                "action_type": str(ActionType.COMMAND.value),
                "commands": ["describe", "pod", "-l", "app=database"],
                "explanation": "My memory shows database pod crashing. Describe it "
                "for details...",
            },
        ),
        (
            "",  # Empty memory, relying on request
            "help me troubleshoot the database pod",
            {
                "action_type": str(ActionType.COMMAND.value),
                "commands": ["describe", "pod", "-l", "app=database"],
                "explanation": "User claims trouble with database pod. First, let's "
                "describe it.",
            },
        ),
        (
            "Wait until pod 'foo' is deleted",
            "",  # Empty request, relying on memory
            {
                "action_type": str(ActionType.ERROR.value),
                "message": "Command 'kubectl wait --for=delete pod/foo' may "
                "indefinitely block.",
            },
        ),
        (
            "You MUST NOT delete the 'health-check' pod.",
            "delete the health-check pod",
            {
                "action_type": str(ActionType.ERROR.value),
                "message": "Memory indicates 'health-check' pod MUST NOT be deleted.",
            },
        ),
        (
            "The cluster has 64GiB of memory available.",
            "set the memory request for the app deployment to 128GiB",
            {
                "action_type": str(ActionType.FEEDBACK.value),
                "message": "The cluster lacks memory (64GiB available) to meet "
                "request for 128GiB.",
                "explanation": "User's request exceeds available cluster resources.",
                "suggestion": "Set a reduced memory request for the app deployment "
                "of 32GiB.",
            },
        ),
        (
            "",
            "lkbjwqnfl alkfjlkads",  # Unintelligible request
            {
                "action_type": str(ActionType.FEEDBACK.value),
                "message": "It is not clear what you want to do. Try again with a "
                "clearer request.",
                "explanation": "The user's request is unintelligible.",
                "suggestion": "Check user input for unclear requests. Provide detailed "
                "examples.",
            },
        ),
        (
            "",
            "check deployment 'demo' with 2 minutes timeout",
            {
                "action_type": str(ActionType.COMMAND.value),
                "commands": [
                    "wait",
                    "--for=condition=Available",
                    "deployment/demo",
                    "--timeout=120s",
                ],
                "explanation": "User requested explicit timeout for deployment check.",
            },
        ),
    ]
    system_fragments.append(
        Fragment(f"""Examples:

{format_ml_examples(vibe_examples_data, request_label="Request")}""")
    )

    # User fragments will be added by the caller (memory context, actual request)
    user_fragments.append(
        Fragment("Plan the next action based on your memory and the request:")
    )

    return PromptFragments((system_fragments, user_fragments))


# Template for summarizing vibe autonomous command output
@with_summary_prompt_override("vibe_resource_summary")
def vibe_autonomous_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing command output in autonomous mode.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments.
    """
    system_fragments: SystemFragments = SystemFragments([])
    user_fragments: UserFragments = UserFragments([])

    if current_memory and current_memory.strip():
        system_fragments.append(fragment_memory_context(current_memory))

    # System: Core instructions
    system_fragments.append(
        Fragment("""Analyze this kubectl command output and provide a concise summary.
Focus on the state of the resources, issues detected, and suggest logical next steps.

If the output indicates \"Command returned no output\" or \"No resources found\",
this is still valuable information! It means the requested resources don't exist
in the specified namespace or context. Include this fact and suggest appropriate
next steps (checking namespace, creating resources, etc.).

For resources with complex data:
- Suggest YAML manifest approaches over inline flags
- For ConfigMaps, Secrets with complex content, recommend kubectl create/apply -f
- Avoid suggesting command line arguments with quoted content""")
    )

    # System: Formatting instructions
    formatting_system_fragments, formatting_user_fragments = get_formatting_fragments(
        config  # Pass original config parameter
    )
    system_fragments.extend(formatting_system_fragments)
    # User fragments from get_formatting_fragments might include dynamic time notes.
    # These should come after general instructions but before specific
    # output placeholders.
    user_fragments.extend(formatting_user_fragments)

    # System: Example format
    system_fragments.append(
        Fragment(
            """Example format:
[bold]3 pods[/bold] running in [blue]app namespace[/blue]
[green]All deployments healthy[/green] with proper replica counts
[yellow]Note: database pod has high CPU usage[/yellow]
Next steps: Consider checking logs for database pod
or scaling the deployment

For empty output:
[yellow]No pods found[/yellow] in [blue]sandbox namespace[/blue]
Next steps: Create the first pod or deployment using a YAML manifest"""
        )
    )

    # User: Placeholder for actual output (needs formatting by caller)
    user_fragments.append(Fragment("Here's the output:\n\n{output}"))

    return PromptFragments((system_fragments, user_fragments))
