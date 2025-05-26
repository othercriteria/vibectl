"""
Apply-specific prompts for vibectl apply command.

This module contains prompts specific to the apply functionality,
helping to keep the main prompt.py file more manageable.
"""

import json

from vibectl.prompt import (
    _SCHEMA_DEFINITION_JSON,
    ActionType,
    Config,
    Examples,
    Fragment,
    PromptFragments,
    SystemFragments,
    UserFragments,
    create_planning_prompt,
    create_summary_prompt,
    fragment_json_schema_instruction,
)
from vibectl.schema import ApplyFileScopeResponse, LLMFinalApplyPlanResponse

# Apply-specific schema constants
_APPLY_FILESCOPE_SCHEMA_JSON = json.dumps(
    ApplyFileScopeResponse.model_json_schema(), indent=2
)
_LLM_FINAL_APPLY_PLAN_RESPONSE_SCHEMA_JSON = json.dumps(
    LLMFinalApplyPlanResponse.model_json_schema(), indent=2
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


def plan_apply_filescope_prompt_fragments(request: str) -> PromptFragments:
    """Get prompt fragments for planning kubectl apply file scoping."""
    system_frags = SystemFragments(
        [
            Fragment(
                """You are an expert Kubernetes assistant. Your task is to analyze
                the user's request for `kubectl apply`. Identify all file paths,
                directory paths, or glob patterns that the user intends to use
                with `kubectl apply -f` or `kubectl apply -k`.
                Also, extract any remaining part of the user's request that
                provides additional context or instructions for the apply
                operation (e.g., '--prune', '--server-side', 'for all
                deployments in the staging namespace')."""
            ),
            fragment_json_schema_instruction(
                _APPLY_FILESCOPE_SCHEMA_JSON, "the ApplyFileScopeResponse"
            ),
        ]
    )
    user_frags = UserFragments(
        [
            Fragment(
                f"""User Request: {request}

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
                used with `kubectl apply -f` or `-k` or for globbing."""
            )
        ]
    )
    return PromptFragments((system_frags, user_frags))


def summarize_apply_manifest_prompt_fragments(
    current_memory: str, manifest_content: str
) -> PromptFragments:
    """Get prompt fragments for summarizing a manifest for kubectl apply context."""
    system_frags = SystemFragments(
        [
            Fragment(
                """You are an expert Kubernetes operations assistant. Your task is to
                summarize the provided Kubernetes manifest content. The user is
                preparing for a `kubectl apply` operation, and this summary will
                help build an operational context (memory) for subsequent steps,
                such as correcting other manifests or planning the final apply
                command.

                Focus on:
                - The kind, name, and namespace (if specified) of the primary
                  resource(s) in the manifest.
                - Key distinguishing features (e.g., for a Deployment: replica
                  count, main container image; for a Service: type, ports; for a
                  ConfigMap: key data items).
                - Conciseness. The summary should be a brief textual description,
                  not a reformatted YAML or a full resource dump.
                - If multiple documents are in the manifest, summarize each briefly
                  or provide a collective summary if appropriate.

                Consider the 'Current Operation Memory' which contains summaries of
                previously processed valid manifests for this same `kubectl apply`
                operation. Your new summary should be consistent with and add to
                this existing memory. Avoid redundancy if the current manifest is
                very similar to something already summarized, but still note its
                presence and any key differences."""
            )
        ]
    )
    user_frags = UserFragments(
        [
            Fragment(
                f"""Current Operation Memory (summaries of prior valid manifests for
                this apply operation, if any):
                --------------------
                {current_memory}
                --------------------

                Manifest Content to Summarize:
                --------------------
                {manifest_content}
                --------------------

                Provide your concise summary of the NEW manifest content below.
                This summary will be appended to the operation memory."""
            )
        ]
    )
    return PromptFragments((system_frags, user_frags))


def correct_apply_manifest_prompt_fragments(
    original_file_path: str,
    original_file_content: str | None,
    error_reason: str,
    current_operation_memory: str,
    remaining_user_request: str,
) -> PromptFragments:
    """Get prompt fragments for correcting or generating a Kubernetes manifest."""
    system_frags = SystemFragments(
        [
            Fragment(
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
    user_frags = UserFragments(
        [
            Fragment(
                f"""Original File Path: {original_file_path}

                Original File Content (if available and readable):
                --------------------
                {
                    original_file_content
                    if original_file_content is not None
                    else "[Content not available or not readable]"
                }
                --------------------

                Error Reason Encountered During Initial Validation for this file:
                {error_reason}

                Current Operation Memory (summaries of other valid manifests
                processed for this same `kubectl apply` operation):
                --------------------
                {current_operation_memory}
                --------------------

                Overall User Request (remaining non-file-specific intent for the
                `kubectl apply` operation):
                --------------------
                {remaining_user_request}
                --------------------

                Proposed Corrected/Generated YAML Manifest (output only raw YAML
                or an empty string/comment as instructed):"""
            )
        ]
    )
    return PromptFragments((system_frags, user_frags))


def plan_final_apply_command_prompt_fragments(
    valid_original_manifest_paths: str,
    corrected_temp_manifest_paths: str,
    remaining_user_request: str,
    current_operation_memory: str,
    unresolvable_sources: str,
    final_plan_schema_json: str,  # Renamed from schema_json
) -> PromptFragments:
    """Get prompt fragments for planning the final kubectl apply command(s).

    The LLM should return a JSON object conforming to LLMFinalApplyPlanResponse,
    containing a list of LLMCommandResponse objects under the 'planned_commands' key.
    """
    system_frags = SystemFragments(
        [
            Fragment(
                """You are an expert Kubernetes operations planner. Your task is to
                formulate the final `kubectl apply` command(s) based on a
                collection of validated original Kubernetes manifests, newly
                corrected/generated manifests (in temporary locations), the
                overall user request context, the operational memory built from
                summarizing these manifests, and a list of any sources that could
                not be resolved or corrected. Your goal is to achieve the user's
                intent as closely as possible, using only the provided valid and
                corrected manifests.

                IMPORTANT INSTRUCTIONS:
                - Your response MUST be a JSON object conforming to the
                  LLMFinalApplyPlanResponse schema provided below. This means a
                  single JSON object with one key: 'planned_commands'. The value
                  of 'planned_commands' MUST be a list of valid
                  CommandAction JSON objects (as defined in the LLMPlannerResponse
                  schema).

                - Each CommandAction object in the list represents a single
                  `kubectl apply` command to be executed.

                - For each command, the `action_type` within the CommandAction
                  object MUST be 'COMMAND'.

                - The `commands` field within each CommandAction MUST be a list
                  of strings representing the arguments *after* `kubectl apply`
                  (e.g., ['-f', 'path1.yaml', '-f', 'path2.yaml', '-n', 'namespace']).
                  Do NOT include 'kubectl apply' itself in the `commands` list.

                - If a manifest needs to be applied via stdin (e.g., because it
                  was generated by you and doesn't have a fixed path), use
                  `commands: ['-f', '-']` and provide the manifest content in the
                  `yaml_manifest` field of that CommandAction.

                - Use the `corrected_temp_manifest_paths` for any manifests that
                  were corrected or generated. Prefer these over original paths if a
                  corrected version exists.

                - Use the `valid_original_manifest_paths` for manifests that were
                  initially valid and not subsequently corrected.

                - Combine multiple files into a single `kubectl apply` command
                  using multiple `-f <path>` arguments if they target the same
                  context (e.g., same namespace, same flags like --server-side).
                  Do NOT generate one apply command per file unless necessary.

                - Incorporate the `remaining_user_request` (e.g., target
                  namespace, flags like --prune, --server-side) into the
                  `commands` list of the relevant `kubectl apply`
                  CommandAction(s).

                - If there are no valid or corrected manifests to apply, the
                  `planned_commands` list should be empty ( `[]` ). Do NOT generate
                  an error or a command that will fail in this case.

                - If `unresolvable_sources` lists any files, they CANNOT be used.
                  Your plan should only use files from
                  `valid_original_manifest_paths` and
                  `corrected_temp_manifest_paths`. If any sources were
                  unresolvable and thus excluded from the plan, this information should
                  be conveyed through a separate FEEDBACK or THOUGHT action in a
                  prior step by the calling logic, as CommandAction itself does not
                  have a dedicated 'explanation' field for this purpose.

                - Ensure all paths in the `commands` field are absolute paths
                  as provided in the input lists."""
            ),
            # Use the new schema for LLMFinalApplyPlanResponse
            fragment_json_schema_instruction(
                final_plan_schema_json,
                "LLMFinalApplyPlanResponse (a list of CommandAction plans)",
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
    user_frags_content = f"""Available Valid Original Manifest Paths (prefer corrected
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

        Based on all the above, provide the `kubectl apply` plan as a JSON
        object conforming to the LLMFinalApplyPlanResponse schema."""
    user_frags = UserFragments([Fragment(user_frags_content)])
    return PromptFragments((system_frags, user_frags))
