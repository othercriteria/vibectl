"""
Prompt definitions for kubectl check commands.

This module contains prompt templates and functions specific to the
'vibectl check' command for evaluating predicates against a Kubernetes cluster.
"""

from typing import Any

from vibectl.schema import ActionType
from vibectl.types import (
    Fragment,
    PromptFragments,
    SystemFragments,
    UserFragments,
)

from .schemas import _SCHEMA_DEFINITION_JSON
from .shared import (
    format_ml_examples,
    fragment_json_schema_instruction,
    with_custom_prompt_override,
)


@with_custom_prompt_override("check_plan")
def plan_check_fragments(custom_mapping: Any) -> PromptFragments:
    """Get prompt fragments for planning 'vibectl check' commands."""

    # Get custom mapping attributes, if provided
    task_description = getattr(custom_mapping, "task_description", "")
    check_examples_data = getattr(custom_mapping, "check_examples_data", None)
    context_instructions = getattr(custom_mapping, "context_instructions", "")

    system_fragments: SystemFragments = SystemFragments([])
    user_fragments: UserFragments = UserFragments([])

    # System: Core instructions and role for 'check'
    system_fragments.append(
        Fragment(task_description)
        or Fragment(
            """You are an AI assistant evaluating a predicate against a
Kubernetes cluster.

Your goal is to determine if the given predicate is TRUE or FALSE.

You MUST use read-only kubectl commands (get, describe, logs, events) to
gather information.

Do NOT use commands that modify state (create, delete, apply, patch, edit, scale, etc.).

Your response MUST be a single JSON object conforming to the LLMPlannerResponse schema.
Choose ONE action:
- COMMAND: If you need more information. Specify *full* kubectl command arguments.
- DONE: If you can determine the predicate's truthiness. Include 'exit_code':
    - 0: Predicate is TRUE.
    - 1: Predicate is FALSE.
    - 2: Predicate is ill-posed or ambiguous for a Kubernetes context.
    - 3: Cannot determine truthiness (e.g., insufficient info, timeout, error
         during execution).
  Include an 'explanation' field justifying your conclusion.
- ERROR: If the request is fundamentally flawed (e.g., asks to modify state).

Focus on the original predicate. Base your final DONE action on whether that specific
predicate is true or false based on the information gathered."""
        )
    )

    # System: Schema definition
    system_fragments.append(fragment_json_schema_instruction(_SCHEMA_DEFINITION_JSON))

    # System: Examples for 'check' - use custom examples if provided, otherwise defaults
    if check_examples_data is not None:
        examples_to_use = check_examples_data
    else:
        examples_to_use = [
            (
                "Namespace 'default' has pods: nginx-1 (Running), nginx-2 (Running).",
                "are all pods in the default namespace running?",
                {
                    "action_type": str(ActionType.DONE.value),
                    "exit_code": 0,
                    "explanation": "All pods listed in memory for 'default' "
                    "are Running.",
                },
            ),
            (
                "Pods in 'kube-system': foo (Running), bar (CrashLoopBackOff), "
                "baz (Pending)",
                "are all pods in kube-system healthy?",
                {
                    "action_type": str(ActionType.DONE.value),
                    "exit_code": 1,
                    "explanation": "Pod 'bar' in 'kube-system' is in CrashLoopBackOff "
                    "state.",
                },
            ),
            (
                "",
                "is there a deployment named 'web-server' in 'production'?",
                {
                    "action_type": str(ActionType.COMMAND.value),
                    "commands": ["get", "deployment", "web-server", "-n", "production"],
                    "explanation": "Cannot determine from memory; need to query the "
                    "cluster for the deployment.",
                },
            ),
            (
                "",
                "is the sky blue today in the cluster?",
                {
                    "action_type": str(ActionType.DONE.value),
                    "exit_code": 2,
                    "explanation": "This predicate is ill-posed for a Kubernetes "
                    "cluster context.",
                },
            ),
            (
                "",
                "Attempt deletion of all pods in the cluster and ensure they "
                "are deleted.",
                {
                    "action_type": str(ActionType.ERROR.value),
                    "message": "The 'check' command can't ensure actions; it only "
                    "evaluates predicates.",
                },
            ),
        ]

    system_fragments.append(
        Fragment(f"""Examples for 'vibectl check':

{format_ml_examples(examples_to_use, request_label="Predicate")}

Note on multi-step COMMAND example: If a COMMAND action is planned, `vibectl` will
execute it and the output will be fed back into your memory for a subsequent planning
step. You would then use that new information to issue another COMMAND or a DONE action.
""")
    )

    # User fragments will be added by the caller (memory context, actual predicate)
    user_fragments.append(
        Fragment(context_instructions)
        or Fragment(
            "Evaluate the following based on your memory and the plan you develop:"
        )
    )

    return PromptFragments((system_fragments, user_fragments))
