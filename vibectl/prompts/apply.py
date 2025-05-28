"""
Apply-specific prompts for vibectl apply command.

This module contains prompts specific to the apply functionality,
helping to keep the main prompt.py file more manageable.
"""

import json
from typing import Any

from vibectl.config import Config
from vibectl.prompts.schemas import _SCHEMA_DEFINITION_JSON
from vibectl.prompts.shared import (
    create_planning_prompt,
    create_summary_prompt,
    fragment_json_schema_instruction,
    with_custom_prompt_override,
    with_planning_prompt_override,
    with_summary_prompt_override,
)
from vibectl.schema import ActionType, ApplyFileScopeResponse, LLMFinalApplyPlanResponse
from vibectl.types import (
    Examples,
    Fragment,
    PromptFragments,
    SystemFragments,
    UserFragments,
)

# Apply-specific schema constants
_APPLY_FILESCOPE_SCHEMA_JSON = json.dumps(
    ApplyFileScopeResponse.model_json_schema(), indent=2
)
_LLM_FINAL_APPLY_PLAN_RESPONSE_SCHEMA_JSON = json.dumps(
    LLMFinalApplyPlanResponse.model_json_schema(), indent=2
)


@with_planning_prompt_override("apply_plan")
def apply_plan_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for planning kubectl apply commands.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    # Fall back to default prompt (decorator handles plugin override)
    return create_planning_prompt(
        command="apply",
        description=(
            "applying configurations to Kubernetes resources using YAML manifests"
        ),
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
                        "explanation": "User asked to apply all YAML files in "
                        "a directory.",
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
                        "explanation": "A client-side dry-run shows the user a "
                        "manifest.",
                    },
                ),
            ]
        ),
        schema_definition=_SCHEMA_DEFINITION_JSON,
    )


@with_summary_prompt_override("apply_resource_summary")
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
    # Fall back to default prompt (decorator handles plugin override)
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


@with_custom_prompt_override("apply_filescope")
def plan_apply_filescope_prompt_fragments(
    custom_mapping: Any,
    request: str,
) -> PromptFragments:
    """Get prompt fragments for planning kubectl apply file scoping."""

    # Get custom mapping attributes, if provided
    task_description = getattr(custom_mapping, "task_description", "")
    examples = getattr(custom_mapping, "examples", "")
    context_instructions = getattr(custom_mapping, "context_instructions", "")

    system_frags = SystemFragments(
        [
            Fragment(task_description)
            or Fragment(
                """You are an expert Kubernetes assistant. Your task is to analyze
                the user's request for `kubectl apply`. Identify all file paths,
                directory paths, or glob patterns that the user intends to use
                with `kubectl apply -f` or `kubectl apply -k`.
                Also, extract any remaining part of the user's request that
                provides additional context or instructions for the apply
                operation (e.g., '--prune', '--server-side', 'for all
                deployments in the staging namespace')."""
            ),
            Fragment(examples)
            or Fragment(
                """Examples of multi-namespace requests:

                "apply manifests/ to both staging and production namespaces"
                → file_selectors: ["manifests/"]
                → remaining_request_context: "to both staging and production namespaces"

                "deploy ./configs into demo-1 and demo-2 environments"
                → file_selectors: ["./configs"]
                → remaining_request_context: "into demo-1 and demo-2 environments"

                "examples/app/ should go to both test-ns and dev-ns"
                → file_selectors: ["examples/app/"]
                → remaining_request_context: "should go to both test-ns and dev-ns"

                "apply service.yaml and deployment.yaml to namespace-a and namespace-b"
                → file_selectors: ["service.yaml", "deployment.yaml"]
                → remaining_request_context: "to namespace-a and namespace-b"

                The key pattern: extract the files/directories, and preserve the full
                multi-namespace instruction in the remaining context."""
            ),
            fragment_json_schema_instruction(
                _APPLY_FILESCOPE_SCHEMA_JSON, "the ApplyFileScopeResponse"
            ),
        ]
    )

    context_frag = (
        context_instructions
        or """
User Request: {request}

Please provide your analysis in JSON format, adhering to the
ApplyFileScopeResponse schema previously defined.

Focus only on what the user explicitly stated for file/directory
selection and the remaining context.
If no specific files or directories are mentioned, provide an
empty list for `file_selectors`.
If no additional context is provided beyond file selection,
`remaining_request_context` should be an empty string or reflect
that.
Ensure `file_selectors` contains only strings that can be directly
used with `kubectl apply -f` or `-k` or for globbing.

"""
    )

    user_frags = UserFragments([Fragment(context_frag.format(request=request))])

    return PromptFragments((system_frags, user_frags))


@with_custom_prompt_override("apply_manifest_summary")
def summarize_apply_manifest_prompt_fragments(
    custom_mapping: Any, current_memory: str, manifest_content: str
) -> PromptFragments:
    """Get prompt fragments for summarizing a manifest for kubectl apply context."""

    # Get custom mapping attributes, if provided
    task_description = getattr(custom_mapping, "task_description", "")
    context_instructions = getattr(custom_mapping, "context_instructions", "")

    system_frags = SystemFragments(
        [
            Fragment(task_description)
            or Fragment(
                """You are an expert Kubernetes operations assistant. Your task is to
                summarize the provided Kubernetes manifest content. The user is
                preparing for a `kubectl apply` operation, and this summary will
                help build an operational context (memory) for subsequent steps,
                such as correcting other manifests or planning the final apply
                command.

                Focus on:
                - The kind, name, and (if specified) namespace of the primary
                  resource(s) in the manifest.
                - Key distinguishing features (e.g., for a Deployment: replica
                  count, main container image; for a Service: type, ports; for a
                  ConfigMap: key data items).
                - Conciseness. The summary should be a brief textual description,
                  not a reformatted YAML or a full resource dump.
                - If multiple documents are in the manifest, summarize each briefly
                  or provide a collective summary if appropriate.

                NAMESPACE GUIDANCE:
                - If a manifest specifies a particular namespace, note it but emphasize
                  that the resource type and configuration are the primary focus
                - Avoid letting specific namespace values influence the summary's
                  general applicability to other namespaces
                - Frame namespace information as "currently configured for [namespace]"
                  rather than as a permanent characteristic

                Consider the 'Current Operation Memory' which contains summaries of
                previously processed valid manifests for this same `kubectl apply`
                operation. Your new summary should be consistent with and add to
                this existing memory. Avoid redundancy if the current manifest is
                very similar to something already summarized, but still note its
                presence and any key differences."""
            )
        ]
    )
    context_frag = (
        context_instructions
        or """
Current Operation Memory (summaries of prior valid manifests for
this apply operation, if any):
--------------------
{current_memory}
--------------------

Manifest Content to Summarize:
--------------------
{manifest_content}
--------------------

Provide your concise summary of the NEW manifest content below.
This summary will be appended to the operation memory.
"""
    )

    user_frags = UserFragments(
        [
            Fragment(
                context_frag.format(
                    current_memory=current_memory, manifest_content=manifest_content
                )
            )
        ]
    )

    return PromptFragments((system_frags, user_frags))


@with_custom_prompt_override("apply_manifest_correction")
def correct_apply_manifest_prompt_fragments(
    custom_mapping: Any,
    original_file_path: str,
    original_file_content: str | None,
    error_reason: str,
    current_operation_memory: str,
    remaining_user_request: str,
) -> PromptFragments:
    """Get prompt fragments for correcting or generating a Kubernetes manifest."""

    # Get custom mapping attributes, if provided
    task_description = getattr(custom_mapping, "task_description", "")
    context_instructions = getattr(custom_mapping, "context_instructions", "")

    system_frags = SystemFragments(
        [
            Fragment(task_description)
            or Fragment(
                """You are an expert Kubernetes manifest correction and generation
                assistant. Your primary goal is to produce valid Kubernetes YAML
                manifests. Based on the provided original file content (if any),
                the error encountered during its initial validation, the broader
                context from other valid manifests already processed for this
                `kubectl apply` operation (current operation memory), and the
                overall user request, you must attempt to either:
                1. Correct the existing content into a valid Kubernetes manifest.
                2. Generate a new manifest that fulfills the likely intent for the
                   given file path, especially if the original content is
                   irrelevant, unreadable, or significantly flawed.

                CRITICAL NAMESPACE GUIDANCE:
                - Do NOT hardcode specific namespace values in manifests
                - Generate namespace-agnostic resources that can be applied to
                  any namespace
                - If a manifest needs a namespace, use a generic placeholder
                  like "default" or omit the namespace field entirely to let
                  kubectl apply with -n flag
                - The user's request may specify multiple target namespaces
                  for deployment, so avoid locking manifests to specific
                  namespace values

                Output ONLY the proposed YAML manifest string. Do not include
                any explanations, apologies, or preamble. If you are highly
                confident the source is not meant to be a Kubernetes manifest and
                cannot be transformed into one (e.g., it's a text note, a
                script, or completely unrelated data), or if you cannot produce a
                valid YAML manifest with reasonable confidence based on the
                inputs, output an empty string or a single YAML comment line like
                '# Cannot automatically correct/generate a manifest for this source.'
                Prefer generating a plausible manifest based on the filename and
                context if the content itself is unhelpful. Ensure your output is
                raw YAML, not enclosed in triple backticks or any other
                formatting."""
            )
        ]
    )

    original_file_content_str = (
        original_file_content
        if original_file_content is not None
        else "[Content not available or not readable]"
    )

    context_frag = (
        context_instructions
        or """
Original File Path: {original_file_path}

Original File Content (if available and readable):
```
{original_file_content_str}
```

Error Reason Encountered During Initial Validation for this file:
{error_reason}

Current Operation Memory (summaries of other valid manifests
processed for this same `kubectl apply` operation):
```
{current_operation_memory}
```

Overall User Request (remaining non-file-specific intent for the
`kubectl apply` operation):
```
{remaining_user_request}
```

Proposed Corrected/Generated YAML Manifest (output only raw YAML
or an empty string/comment as instructed):
"""
    )

    user_frags = UserFragments(
        [
            Fragment(
                context_frag.format(
                    original_file_path=original_file_path,
                    original_file_content_str=original_file_content_str,
                    error_reason=error_reason,
                    current_operation_memory=current_operation_memory,
                    remaining_user_request=remaining_user_request,
                )
            )
        ]
    )

    return PromptFragments((system_frags, user_frags))


@with_custom_prompt_override("apply_final_planning")
def plan_final_apply_command_prompt_fragments(
    custom_mapping: Any,
    valid_original_manifest_paths: str,
    corrected_temp_manifest_paths: str,
    remaining_user_request: str,
    current_operation_memory: str,
    unresolvable_sources: str,
    final_plan_schema_json: str,
) -> PromptFragments:
    """Get prompt fragments for planning the final kubectl apply command(s).

    The LLM should return a JSON object conforming to LLMFinalApplyPlanResponse,
    containing a list of LLMCommandResponse objects under the 'planned_commands' key.
    """

    # Get custom mapping attributes, if provided
    command_construction = getattr(custom_mapping, "command_construction", "")
    task_description = getattr(custom_mapping, "task_description", "")
    examples = getattr(custom_mapping, "examples", "")
    context_instructions = getattr(custom_mapping, "context_instructions", "")

    command_construction_guidelines_frag = command_construction or Fragment(
        """Command Construction Guidelines:
            - Each `commands` array should contain kubectl apply arguments
                (excluding the 'kubectl apply' prefix)
                - Use `-f` to specify manifest files or directories
                - Add `-n <namespace>` when targeting specific namespaces
                - For multi-namespace requests, create separate commands for
                    each namespace
                - Include appropriate flags like `--server-side`, `--prune` if
                    contextually relevant

            Output Schema:
            {final_plan_schema_json}
            """
    )

    system_frags = SystemFragments(
        [
            Fragment(task_description)
            or Fragment(
                """You are a Kubernetes expert assistant responsible for planning
                final kubectl apply commands. Given a collection of valid manifest
                files and the user's remaining request context, determine the
                appropriate kubectl apply commands to execute.

                Your output must be valid JSON that conforms to the provided
                schema. Each command in the `planned_commands` array represents
                a single kubectl apply execution."""
            ),
            Fragment(examples)
            or Fragment(
                """Key examples of fan-out behavior for multi-namespace requests:

                Example 1: "apply examples/manifests/ to both dev-ns and prod-ns"
                → Multiple commands applying same files to different namespaces:
                  - "kubectl apply -f examples/manifests/ -n dev-ns"
                  - "kubectl apply -f examples/manifests/ -n prod-ns"

                Example 2: "deploy config/ into staging and production environments"
                → Separate commands for each environment:
                    - "kubectl apply -f config/ -n staging"
                    - "kubectl apply -f config/ -n production"

                Example 3: "apply service.yaml to namespace-a and namespace-b"
                → Fan out single file to multiple namespaces:
                    - "kubectl apply -f service.yaml -n namespace-a"
                    - "kubectl apply -f service.yaml -n namespace-b"

                Example 4: "deploy app/ to test-1, test-2, and test-3"
                → Create separate command for each target namespace:
                    - "kubectl apply -f app/ -n test-1"
                    - "kubectl apply -f app/ -n test-2"
                    - "kubectl apply -f app/ -n test-3"

                The pattern: When user specifies multiple target namespaces,
                create one command per namespace, each applying the same manifests."""
            ),
            Fragment(
                command_construction_guidelines_frag.format(
                    final_plan_schema_json=final_plan_schema_json
                )
            ),
        ]
    )

    valid_original_manifest_paths_str = (
        valid_original_manifest_paths
        if valid_original_manifest_paths.strip()
        else "None"
    )
    corrected_temp_manifest_paths_str = (
        corrected_temp_manifest_paths
        if corrected_temp_manifest_paths.strip()
        else "None"
    )
    remaining_user_request_str = (
        remaining_user_request if remaining_user_request.strip() else "None"
    )
    current_operation_memory_str = (
        current_operation_memory
        if current_operation_memory.strip()
        else "None available"
    )
    unresolvable_sources_str = (
        unresolvable_sources if unresolvable_sources.strip() else "None"
    )

    context_frag = (
        context_instructions
        or """
Available Valid Original Manifest Paths (prefer corrected
versions if they exist for these original sources):
{valid_original_manifest_paths_str}

Available Corrected/Generated Temporary Manifest Paths (use these for apply):
{corrected_temp_manifest_paths_str}

Remaining User Request Context (apply this to the command(s), e.g.,
namespace, flags):
{remaining_user_request_str}

Current Operation Memory (context from other manifests):
{current_operation_memory_str}

Unresolvable Sources (cannot be used in the apply plan):
{unresolvable_sources_str}

Example for multi-namespace requests:
If remaining context says "into both apply-demo-1 and apply-demo-2 namespaces"
and you have valid manifests at "examples/manifests/apply/", create:
[
  {{"action_type": "COMMAND", "commands": ["-f",
   "examples/manifests/apply/", "-n", "apply-demo-1"]}},
  {{"action_type": "COMMAND", "commands": ["-f",
   "examples/manifests/apply/", "-n", "apply-demo-2"]}}
]

Based on all the above, provide the `kubectl apply` plan as a JSON
object conforming to the LLMFinalApplyPlanResponse schema.
"""
    )

    user_frags = UserFragments(
        [
            Fragment(
                context_frag.format(
                    valid_original_manifest_paths_str=valid_original_manifest_paths_str,
                    corrected_temp_manifest_paths_str=corrected_temp_manifest_paths_str,
                    remaining_user_request_str=remaining_user_request_str,
                    current_operation_memory_str=current_operation_memory_str,
                    unresolvable_sources_str=unresolvable_sources_str,
                )
            )
        ]
    )

    return PromptFragments((system_frags, user_frags))
