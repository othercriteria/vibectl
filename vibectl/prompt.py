"""
Prompt templates for LLM interactions with kubectl output.

Each template follows a consistent format using rich.Console() markup for styling,
ensuring clear and visually meaningful summaries of Kubernetes resources.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from .config import Config
from .schema import (
    ActionType,
    ApplyFileScopeResponse,
    LLMAction,
    LLMFinalApplyPlanResponse,
    LLMPlannerResponse,
)
from .types import (
    Examples,
    Fragment,
    MLExampleItem,
    PromptFragments,
    SystemFragments,
    UserFragments,
)

# Regenerate the shared JSON schema definition string from the Pydantic model
_SCHEMA_DEFINITION_JSON = json.dumps(LLMPlannerResponse.model_json_schema(), indent=2)
_APPLY_FILESCOPE_SCHEMA_JSON = json.dumps(
    ApplyFileScopeResponse.model_json_schema(), indent=2
)
# Schema for the new response structure that wraps a list of commands
_LLM_FINAL_APPLY_PLAN_RESPONSE_SCHEMA_JSON = json.dumps(
    LLMFinalApplyPlanResponse.model_json_schema(), indent=2
)

logger = logging.getLogger(__name__)


def format_ml_examples(
    examples: list[MLExampleItem],
    request_label: str = "Request",
    action_schema: type[LLMAction] | None = None,  # Schema for validation
) -> str:
    """Formats a list of Memory, Request, and Output examples into a string.

    Args:
        examples: A list of tuples, where each tuple contains:
                  (memory_context: str, request_text: str, output_action: dict).
                  The output_action is a dict representing the JSON action.
        request_label: The label to use for the request/predicate part.
        action_schema: Optional Pydantic model to validate the output_action against.

    Returns:
        str: A string containing all formatted examples.
    """
    formatted_str = ""
    for i, (memory, request, output_action_item) in enumerate(examples):
        if action_schema:
            try:
                action_schema.model_validate(output_action_item)
            except Exception as e:  # Catch Pydantic ValidationError and others
                logger.warning(
                    f"Example {i + 1} (Request: '{request}') has an "
                    "invalid 'output_action' against schema "
                    f"{action_schema.__name__}: {e}"
                    f"Action details: {output_action_item}"
                )

        formatted_str += f"Memory: {memory}\n"
        formatted_str += f"{request_label}: {request}\n"
        formatted_str += (
            f"Output:\n{json.dumps({'action': output_action_item}, indent=2)}\n\n"
        )
    return formatted_str.strip()


def format_examples(examples: list[tuple[str, str]]) -> str:
    """Format a list of input/output examples into a consistent string format.

    Args:
        examples: List of tuples where each tuple contains (input_text, output_text)

    Returns:
        str: Formatted examples string
    """
    formatted_examples = "Example inputs and outputs:\\n\\n"
    for input_text, output_text in examples:
        formatted_examples += f'Input: "{input_text}"\\n'
        formatted_examples += f"Output:\\n{output_text}\\n\\n"
    return formatted_examples.rstrip()


def create_planning_prompt(
    command: str,
    description: str,
    examples: Examples,
    schema_definition: str | None = None,
) -> PromptFragments:
    """Create standard planning prompt fragments for kubectl commands.

    This prompt assumes the kubectl command verb (get, describe, delete, etc.)
    is already determined by the context. The LLM's task is to interpret the
    natural language request to identify the target resource(s) and arguments,
    and format the response as JSON according to the provided schema.

    Args:
        command: The kubectl command verb (get, describe, etc.) used for context.
        description: Description of the overall goal (e.g., "getting resources").
        examples: List of tuples where each tuple contains:
                  (natural_language_target_description, expected_json_output_dict)
        schema_definition: JSON schema definition string.
                           Must be provided for structured JSON output.

    Returns:
        PromptFragments: System fragments and base user fragments.
                         Caller adds memory and request fragments.
    """
    if not schema_definition:
        raise ValueError(
            "schema_definition must be provided for create_planning_prompt"
        )

    system_fragments: SystemFragments = SystemFragments([])
    user_fragments: UserFragments = UserFragments(
        []
    )  # Base user fragments, caller adds dynamic ones

    # System: Core task description
    system_fragments.append(
        Fragment(f"""You are planning arguments for the 'kubectl {command}' command,
which is used for {description}.

Given a natural language request describing the target resource(s), determine the
appropriate arguments *following* 'kubectl {command}'.

The kubectl command '{command}' is implied by the context of this planning task.

Focus on extracting resource names, types, namespaces, selectors, and flags
from the request to populate the 'commands' field of the 'COMMAND' action.""")
    )

    system_fragments.append(
        Fragment(f"""
Your response MUST be a valid JSON object conforming to this schema:
```json
{schema_definition}
```

This means your output should have syntax that aligns with this:
{{
  "action": {{
    "action_type": "COMMAND",
    "commands": ["<arg1>", "<arg2>", ...],
    "yaml_manifest": "<yaml_string_if_applicable>",
    "allowed_exit_codes": [0]
    "explanation": "Optional string."
  }}
}}

Key fields within the nested "COMMAND" action object:
- `action_type`: MUST be "COMMAND".
- `commands`: List of string arguments *following* `kubectl {command}`. Include flags
  like `-n`, `-f -`, but *exclude* the command verb itself. **MUST be a JSON array
  of strings, e.g., ["pods", "-n", "kube-system"], NOT a single string like
  "pods -n kube-system" or '["pods", "-n", "kube-system"]' **.
- `yaml_manifest`: YAML content as a string (for actions like `create` that use stdin).
- `allowed_exit_codes`: Optional. List of integers representing allowed exit codes
  for the command (e.g., [0, 1] for diff). Defaults to [0] if not provided.
- `explanation`: Optional. A brief string explaining why this command was chosen.""")
    )

    # System: Formatted examples
    formatted_examples = (
        "Example inputs (natural language target descriptions) and "
        "expected JSON outputs (LLMPlannerResponse wrapping a CommandAction):\n"
    )
    formatted_examples += "\n".join(
        [
            f'- Target: "{req}" -> \n'
            f"Expected JSON output:\\n{json.dumps({'action': output}, indent=2)}"
            for req, output in examples
        ]
    )
    system_fragments.append(Fragment(formatted_examples))

    # Caller will add actual memory and request strings as separate user fragments.
    user_fragments.append(Fragment("Here's the request:"))

    return PromptFragments((system_fragments, user_fragments))


def create_summary_prompt(
    description: str,
    focus_points: list[str],
    example_format: list[str],
    config: Config | None = None,  # Add config for formatting fragments
    current_memory: str | None = None,  # New argument
) -> PromptFragments:
    """Create standard summary prompt fragments for kubectl command output.

    Args:
        description: Description of what to summarize
        focus_points: List of what to focus on in the summary
        example_format: List of lines showing the expected output format
        config: Optional Config instance to use.
        current_memory: Optional current memory string. # New docstring

    Returns:
        PromptFragments: System fragments and base user fragments (excluding memory).
                         Caller adds memory fragment first if needed.
    """
    system_fragments: SystemFragments = SystemFragments([])
    user_fragments: UserFragments = UserFragments([])  # Base user fragments

    # Add memory context if provided and not empty
    if current_memory and current_memory.strip():
        system_fragments.append(fragment_memory_context(current_memory))

    # System: Core task description and focus points
    focus_text = "\n".join([f"- {point}" for point in focus_points])
    system_fragments.append(
        Fragment(f"""{description}
Focus on:
{focus_text}""")
    )

    # System: Formatting instructions (get system fragments ONLY)
    # User fragments from get_formatting_fragments contain only the dynamic time note.
    formatting_system_fragments, formatting_user_fragments = get_formatting_fragments(
        config
    )
    system_fragments.extend(formatting_system_fragments)
    # Add the dynamic time note as a user fragment here
    user_fragments.extend(formatting_user_fragments)

    # System: Example format
    formatted_example = "\n".join(example_format)
    system_fragments.append(Fragment(f"Example format:\n{formatted_example}"))

    # User: The actual output to summarize (placeholder)
    # Caller will add the memory fragment (if enabled) BEFORE this one.
    user_fragments.append(Fragment("Here's the output:\n\n{output}"))

    return PromptFragments((system_fragments, user_fragments))


# Common formatting instructions fragments
def get_formatting_fragments(
    config: Config | None = None,
) -> PromptFragments:
    """Get formatting instructions as fragments (system, user).

    Args:
        config: Optional Config instance to use. If not provided, creates a new one.

    Returns:
        PromptFragments: System fragments and user fragments (excluding memory).
                         Caller is responsible for adding memory context fragment.
    """
    system_fragments: SystemFragments = SystemFragments([])
    user_fragments: UserFragments = UserFragments([])

    cfg = config or Config()

    # System: Static Rich markup instructions
    system_fragments.append(
        Fragment("""Format your response using rich.Console() markup syntax
with matched closing tags:
- [bold]resource names and key fields[/bold] for emphasis
- [green]healthy states[/green] for positive states
- [yellow]warnings or potential issues[/yellow] for concerning states
- [red]errors or critical issues[/red] for problems
- [blue]namespaces and other Kubernetes concepts[/blue] for k8s terms
- [italic]timestamps and metadata[/italic] for timing information""")
    )

    # System: Custom instructions (less frequent change than memory)
    custom_instructions = cfg.get("custom_instructions")
    if custom_instructions:
        system_fragments.append(
            Fragment(f"Custom instructions:\n{custom_instructions}")
        )

    system_fragments.append(fragment_current_time())

    # User: Important notes including dynamic time (most frequent change)
    user_fragments.append(
        Fragment("""Important:
- Timestamps in the future relative to this are not anomalies
- Do NOT use markdown formatting (e.g., #, ##, *, -)
- Use plain text with rich.Console() markup only
- Skip any introductory phrases like "This output shows" or "I can see"
- Be direct and concise""")
    )

    return PromptFragments((system_fragments, user_fragments))


# Template for planning kubectl get commands
PLAN_GET_PROMPT: PromptFragments = create_planning_prompt(
    command="get",
    description="getting Kubernetes resources",
    examples=Examples(
        [
            (
                "pods in kube-system",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["pods", "-n", "kube-system"],
                },
            ),
            (
                "pods with app=nginx label",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["pods", "--selector=app=nginx"],
                },
            ),
            (
                "all pods in every namespace",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["pods", "--all-namespaces"],
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


# Template for summarizing 'kubectl get' output
def get_resource_prompt(
    config: Config | None = None,
    current_memory: str | None = None,  # New parameter
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl get output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string. # New docstring

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    # Removed: current_memory_text = get_memory(cfg)
    return create_summary_prompt(
        description="Summarize this kubectl output.",
        focus_points=["key information", "notable patterns", "potential issues"],
        example_format=[
            "[bold]3 pods[/bold] in [blue]default namespace[/blue], all "
            "[green]Running[/green]",
            "[bold]nginx-pod[/bold] [italic]running for 2 days[/italic]",
            "[yellow]Warning: 2 pods have high restart counts[/yellow]",
        ],
        config=cfg,
        current_memory=current_memory,  # Pass through the parameter
    )


# Template for summarizing 'kubectl describe' output
def describe_resource_prompt(
    config: Config | None = None,
    current_memory: str | None = None,  # New parameter
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl describe output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string. # New docstring

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    # Removed: current_memory_text = get_memory(cfg)
    return create_summary_prompt(
        description="Summarize this kubectl describe output. Limit to 200 words.",
        focus_points=["key details", "issues needing attention"],
        example_format=[
            "[bold]nginx-pod[/bold] in [blue]default[/blue]: [green]Running[/green]",
            "[yellow]Readiness probe failing[/yellow], "
            "[italic]last restart 2h ago[/italic]",
            "[red]OOMKilled 3 times in past day[/red]",
        ],
        config=cfg,
        current_memory=current_memory,  # Pass through the parameter
    )


# Template for summarizing 'kubectl logs' output
def logs_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl logs output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    return create_summary_prompt(
        description="Analyze these container logs concisely.",
        focus_points=[
            "key events",
            "patterns",
            "errors",
            "state changes",
            "note if truncated",
        ],
        example_format=[
            "[bold]Container startup[/bold] at [italic]2024-03-20 10:15:00[/italic]",
            "[green]Successfully connected[/green] to [blue]database[/blue]",
            "[yellow]Slow query detected[/yellow] [italic]10s ago[/italic]",
            "[red]3 connection timeouts[/red] in past minute",
        ],
        config=cfg,
        current_memory=current_memory,
    )


# Template for planning kubectl describe commands
PLAN_DESCRIBE_PROMPT: PromptFragments = create_planning_prompt(
    command="describe",
    description="Kubernetes resource details",
    examples=Examples(
        [
            (
                "the nginx pod",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["pods", "nginx"],
                    "explanation": "User asked to describe the nginx pod.",
                },
            ),
            (
                "the deployment in foo namespace",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["deployments", "-n", "foo"],
                    "explanation": "User asked a deployment in a specific namespace.",
                },
            ),
            (
                "details of all pods with app=nginx",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["pods", "--selector=app=nginx"],
                    "explanation": "User requested pods matching a specific label.",
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)

# Template for planning kubectl logs commands
PLAN_LOGS_PROMPT: PromptFragments = create_planning_prompt(
    command="logs",
    description="Kubernetes logs",
    examples=Examples(
        [
            (
                "logs from the nginx pod",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["pod/nginx"],
                    "explanation": "User asked for logs from a specific pod.",
                },
            ),
            (
                "logs from the api container in app pod",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["pod/app", "-c", "api"],
                    "explanation": "User asked for pod logs from a specific container.",
                },
            ),
            (
                "the last 100 lines from all pods with app=nginx",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["--selector=app=nginx", "--tail=100"],
                    "explanation": "User requested some log lines from matching pods.",
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)

# Template for planning kubectl create commands - Uses the new schema approach
PLAN_CREATE_PROMPT: PromptFragments = create_planning_prompt(
    command="create",
    description="creating Kubernetes resources using YAML manifests",
    examples=Examples(
        [
            (
                "an nginx hello world pod in default",  # Implicit creation request
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["-f", "-", "-n", "default"],
                    "explanation": "Creating an nginx pod as requested by the user.",
                    "yaml_manifest": (
                        """---
apiVersion: v1
kind: Pod
metadata:
  name: nginx-hello
  labels:
    app: nginx
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
                "create a configmap with HTML content",  # Explicit creation
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["-f", "-"],
                    "explanation": "Creating requested configmap with HTML content.",
                    "yaml_manifest": (
                        """---
apiVersion: v1
kind: ConfigMap
metadata:
  name: html-content
data:
  index.html: |
    <html><body><h1>Hello World</h1></body></html>"""
                    ),
                },
            ),
            (
                "frontend and backend pods for my application",  # Implicit creation
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["-f", "-"],
                    "explanation": "Creating frontend and backend pods as requested.",
                    "yaml_manifest": (
                        """---
apiVersion: v1
kind: Pod
metadata:
  name: frontend
  labels:
    app: myapp
    component: frontend
spec:
  containers:
  - name: frontend
    image: nginx:latest
    ports:
    - containerPort: 80
---
apiVersion: v1
kind: Pod
metadata:
  name: backend
  labels:
    app: myapp
    component: backend
spec:
  containers:
  - name: backend
    image: redis:latest
    ports:
    - containerPort: 6379"""
                    ),
                },
            ),
            (
                "spin up a basic redis deployment",  # Explicit creation verb
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["-f", "-"],
                    "explanation": "Creating a redis deployment as requested.",
                    "yaml_manifest": (
                        """---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis-deployment
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:alpine
        ports:
        - containerPort: 6379
"""
                    ),
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


# Template for planning kubectl version commands
PLAN_VERSION_PROMPT: PromptFragments = create_planning_prompt(
    command="version",
    description="Kubernetes version information",
    examples=Examples(
        [
            (
                "version in json format",  # Target/flag description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["--output=json"],
                    "explanation": "User requested version in JSON format.",
                },
            ),
            (
                "client version only",  # Target/flag description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["--client=true", "--output=json"],
                    "explanation": "User requested client version only, JSON format.",
                },
            ),
            (
                "version in yaml",  # Target/flag description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["--output=yaml"],
                    "explanation": "User requested version in YAML format.",
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)

# Template for planning kubectl cluster-info commands
PLAN_CLUSTER_INFO_PROMPT: PromptFragments = create_planning_prompt(
    command="cluster-info",
    description="Kubernetes cluster information",
    examples=Examples(
        [
            (
                "cluster info",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["dump"],
                    "explanation": "User asked for cluster info, defaulting to dump.",
                },
            ),
            (
                "basic cluster info",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": [],
                    "explanation": "User asked for basic cluster info.",
                },
            ),
            (
                "detailed cluster info",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["dump"],
                    "explanation": "User asked for detailed cluster info (dump).",
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)

# Template for planning kubectl events commands
# Note: We deliberately use the 'kubectl events' command here instead of
# 'kubectl get events'. While 'get events' works, 'kubectl events' is the
# more idiomatic command for viewing events and offers specific flags like --for.
PLAN_EVENTS_PROMPT: PromptFragments = create_planning_prompt(
    command="events",  # Use the dedicated 'events' command
    description="Kubernetes events",
    examples=Examples(
        [
            (
                "events in default namespace",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": [],  # Default namespace is implicit
                    "explanation": "User asked for events in the default namespace.",
                },
            ),
            (
                "events for pod nginx",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["--for=pod/nginx"],
                    "explanation": "User asked for events related to a specific pod.",
                },
            ),
            (
                "all events in all namespaces",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["--all-namespaces"],  # Use -A or --all-namespaces
                    "explanation": "User asked for all events across all namespaces.",
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


# Template for summarizing 'kubectl cluster-info' output
def cluster_info_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl cluster-info output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    return create_summary_prompt(
        description="Analyze cluster-info output.",
        focus_points=[
            "cluster version",
            "control plane components",
            "add-ons",
            "notable details",
            "potential issues",
        ],
        example_format=[
            "[bold]Kubernetes v1.26.3[/bold] cluster running on "
            "[blue]Google Kubernetes Engine[/blue]",
            "[green]Control plane healthy[/green] at "
            "[italic]https://10.0.0.1:6443[/italic]",
            "[blue]CoreDNS[/blue] and [blue]KubeDNS[/blue] add-ons active",
            "[yellow]Warning: Dashboard not secured with RBAC[/yellow]",
        ],
        config=cfg,
        current_memory=current_memory,
    )


# Template for summarizing 'kubectl version' output
def version_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl version output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    return create_summary_prompt(
        description="Interpret Kubernetes version details in a human-friendly way.",
        focus_points=[
            "version compatibility",
            "deprecation notices",
            "update recommendations",
        ],
        example_format=[
            "[bold]Kubernetes v1.26.3[/bold] client and [bold]v1.25.4[/bold] server",
            "[green]Compatible versions[/green] with [italic]patch available[/italic]",
            "[blue]Server components[/blue] all [green]up-to-date[/green]",
            "[yellow]Client will be deprecated in 3 months[/yellow]",
        ],
        config=cfg,
        current_memory=current_memory,
    )


# Template for summarizing 'kubectl events' output
def events_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl events output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    return create_summary_prompt(
        description="Analyze these Kubernetes events concisely.",
        focus_points=[
            "recent events",
            "patterns",
            "warnings",
            "notable issues",
            "group related events",
        ],
        example_format=[
            "[bold]12 events[/bold] in the last [italic]10 minutes[/italic]",
            "[green]Successfully scheduled[/green] pods: [bold]nginx-1[/bold], "
            "[bold]nginx-2[/bold]",
            "[yellow]ImagePullBackOff[/yellow] for [bold]api-server[/bold]",
            "[italic]5 minutes ago[/italic]",
            "[red]OOMKilled[/red] events for [bold]db-pod[/bold], "
            "[italic]happened 3 times[/italic]",
        ],
        config=cfg,
        current_memory=current_memory,
    )


# Template for planning kubectl delete commands
PLAN_DELETE_PROMPT: PromptFragments = create_planning_prompt(
    command="delete",
    description="Kubernetes resources",
    examples=Examples(
        [
            (
                "the nginx pod",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["pod", "nginx"],
                    "explanation": "User asked to delete a specific pod.",
                },
            ),
            (
                "deployment in kube-system namespace",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["deployment", "-n", "kube-system"],
                    "explanation": "User asked to delete deployment in namespace.",
                },
            ),
            (
                "all pods with app=nginx",  # Target description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["pods", "--selector=app=nginx"],
                    "explanation": "User asked to delete all pods matching a label.",
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


# Template for summarizing 'kubectl delete' output
def delete_resource_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl delete output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    return create_summary_prompt(
        description="Summarize kubectl delete results.",
        focus_points=["resources deleted", "potential issues", "warnings"],
        example_format=[
            "[bold]3 pods[/bold] successfully deleted from "
            "[blue]default namespace[/blue]",
            "[yellow]Warning: Some resources are still terminating[/yellow]",
        ],
        config=cfg,
        current_memory=current_memory,
    )


# Template for planning kubectl scale commands
PLAN_SCALE_PROMPT: PromptFragments = create_planning_prompt(
    command="scale",
    description="scaling Kubernetes resources",
    examples=Examples(
        [
            (
                "deployment nginx to 3 replicas",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["deployment/nginx", "--replicas=3"],
                    "explanation": "User asked to scale a deployment to 3 replicas.",
                },
            ),
            (
                "the redis statefulset to 5 replicas in the cache namespace",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["statefulset/redis", "--replicas=5", "-n", "cache"],
                    "explanation": "User asked to scale statefulset in namespace.",
                },
            ),
            (
                "down the api deployment",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": [
                        "deployment/api",
                        "--replicas=1",
                    ],  # Assuming scale down means 1
                    "explanation": "User asked to scale down a deployment, "
                    "defaulting to 1 replica.",
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


# Template for summarizing 'kubectl scale' output
def scale_resource_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl scale output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    return create_summary_prompt(
        description="Summarize scaling operation results.",
        focus_points=["changes made", "current state", "issues or concerns"],
        example_format=[
            "[bold]deployment/nginx[/bold] scaled to [green]3 replicas[/green]",
            "[yellow]Warning: Scale operation might take time to complete[/yellow]",
            "[blue]Namespace: default[/blue]",
        ],
        config=cfg,
        current_memory=current_memory,
    )


# Template for planning kubectl wait commands
PLAN_WAIT_PROMPT: PromptFragments = create_planning_prompt(
    command="wait",
    description="waiting on Kubernetes resources",
    examples=Examples(
        [
            (
                "for the deployment my-app to be ready",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["deployment/my-app", "--for=condition=Available"],
                    "explanation": "User asked to wait on deployment availability.",
                },
            ),
            (
                "until the pod nginx becomes ready with 5 minute timeout",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["pod/nginx", "--for=condition=Ready", "--timeout=5m"],
                    "explanation": "User asked to wait for pod readiness with timeout.",
                },
            ),
            (
                "for all jobs in billing namespace to complete",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": [
                        "jobs",
                        "--all",
                        "-n",
                        "billing",
                        "--for=condition=Complete",
                    ],
                    "explanation": "User asked to wait on all jobs done in namespace.",
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


# Template for summarizing 'kubectl wait' output
def wait_resource_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl wait output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    return create_summary_prompt(
        description="Summarize this kubectl wait output.",
        focus_points=[
            "whether resources met their conditions",
            "timing information",
            "any errors or issues",
        ],
        example_format=[
            (
                "[bold]pod/nginx[/bold] in [blue]default namespace[/blue] "
                "now [green]Ready[/green]"
            ),
            (
                "[bold]Deployment/app[/bold] successfully rolled out after "
                "[italic]35s[/italic]"
            ),
            (
                "[red]Timed out[/red] waiting for "
                "[bold]StatefulSet/database[/bold] to be ready"
            ),
        ],
        config=cfg,
        current_memory=current_memory,
    )


# Template for planning kubectl rollout commands
PLAN_ROLLOUT_PROMPT: PromptFragments = create_planning_prompt(
    command="rollout",
    description="managing Kubernetes rollouts",
    examples=Examples(
        [
            (
                "status of deployment nginx",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["status", "deployment/nginx"],
                    "explanation": "User asked for the rollout status of a deployment.",
                },
            ),
            (
                "frontend deployment to revision 2",  # rollout action description
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["undo", "deployment/frontend", "--to-revision=2"],
                    "explanation": "User asked to roll back to specific revision.",
                },
            ),
            (
                "the rollout of my-app deployment in production namespace",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["pause", "deployment/my-app", "-n", "production"],
                    "explanation": "User asked to pause rollout in a namespace.",
                },
            ),
            (
                "all deployments in default namespace",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": [
                        "restart",
                        "deployment",
                        "-n",
                        "default",
                    ],  # Or add selector if needed
                    "explanation": "User asked to restart deployments in namespace.",
                },
            ),
            (
                "history of statefulset/redis",
                {
                    "action_type": ActionType.COMMAND.value,
                    "commands": ["history", "statefulset/redis"],
                    "explanation": "User asked for the rollout history of statefulset.",
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


# Template for summarizing 'kubectl create' output
def create_resource_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl create output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    return create_summary_prompt(
        description="Summarize resource creation results.",
        focus_points=["resources created", "issues or concerns"],
        example_format=[
            "Created [bold]nginx-pod[/bold] in [blue]default namespace[/blue]",
            "[green]Successfully created[/green] with "
            "[italic]default resource limits[/italic]",
            "[yellow]Note: No liveness probe configured[/yellow]",
        ],
        config=cfg,
        current_memory=current_memory,
    )


# Template for summarizing 'kubectl rollout status' output
def rollout_status_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl rollout status output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    return create_summary_prompt(
        description="Summarize rollout status.",
        focus_points=["progress", "completion status", "issues or delays"],
        example_format=[
            "[bold]deployment/frontend[/bold] rollout "
            "[green]successfully completed[/green]",
            "[yellow]Still waiting for 2/5 replicas[/yellow]",
            "[italic]Rollout started 5 minutes ago[/italic]",
        ],
        config=cfg,
        current_memory=current_memory,
    )


# Template for summarizing 'kubectl rollout history' output
def rollout_history_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl rollout history output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    return create_summary_prompt(
        description="Summarize rollout history.",
        focus_points=[
            "key revisions",
            "important changes",
            "patterns across revisions",
        ],
        example_format=[
            "[bold]deployment/app[/bold] has [blue]5 revision history[/blue]",
            "[green]Current active: revision 5[/green] (deployed 2 hours ago)",
            "[yellow]Revision 3 had frequent restarts[/yellow]",
        ],
        config=cfg,
        current_memory=current_memory,
    )


# Template for summarizing other rollout command outputs
def rollout_general_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl rollout output.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    cfg = config or Config()
    return create_summary_prompt(
        description="Summarize rollout command results.",
        focus_points=["key operation details"],
        example_format=[
            "[bold]Deployment rollout[/bold] [green]successful[/green]",
            "[blue]Updates applied[/blue] to [bold]my-deployment[/bold]",
            "[yellow]Warning: rollout took longer than expected[/yellow]",
        ],
        config=cfg,
        current_memory=current_memory,
    )


FRAGMENT_MEMORY_ASSISTANT: Fragment = Fragment("""
You are an AI agent maintaining memory state for a Kubernetes CLI tool.
The memory contains essential context to help you better assist with future requests.

Based on new information, update the memory to maintain the most relevant context.

IMPORTANT: Do NOT include any prefixes like \"Updated memory:\" or headings in
your response. Just provide the direct memory content itself with no additional
labels or headers.
""")


def fragment_concision(max_chars: int) -> Fragment:
    return Fragment(f"Be concise. Limit your response to {max_chars} characters.")


def fragment_current_time() -> Fragment:
    return Fragment(f"Current time is {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.")


def fragment_json_schema_instruction(
    schema_json: str, schema_name: str = "the provided"
) -> Fragment:
    """Creates a system fragment instructing the LLM to adhere to a JSON schema."""
    return Fragment(f"""
Your response MUST be a valid JSON object conforming to {schema_name} schema:
```json
{schema_json}
```
""")


def fragment_memory_context(current_memory: str) -> Fragment:
    return Fragment(f"Previous Memory:\n{current_memory}")


def memory_update_prompt(
    command_message: str,
    command_output: str,
    vibe_output: str,
    current_memory: str,
    config: Config | None = None,
) -> PromptFragments:
    """Generate system and user fragments for memory update."""
    cfg = config or Config()
    max_chars = int(cfg.get("memory_max_chars", 500))

    system_fragments: SystemFragments = SystemFragments(
        [
            FRAGMENT_MEMORY_ASSISTANT,
            fragment_concision(max_chars),
            Fragment("Based on the context and interaction, give the updated memory."),
        ]
    )

    fragment_interaction = Fragment(f"""Interaction:
Action: {command_message}
Output: {command_output}
Vibe: {vibe_output}
""")

    user_fragments: UserFragments = UserFragments(
        [
            fragment_current_time(),
            fragment_memory_context(current_memory),
            fragment_interaction,
            Fragment("New Memory Summary:"),
        ]
    )
    return PromptFragments((system_fragments, user_fragments))


def memory_fuzzy_update_prompt(
    current_memory: str,
    update_text: str | None = None,
    config: Config | None = None,
) -> PromptFragments:
    """Generate system and user fragments for fuzzy memory update."""
    cfg = config or Config()
    max_chars = int(cfg.get("memory_max_chars", 500))

    system_fragments: SystemFragments = SystemFragments(
        [
            FRAGMENT_MEMORY_ASSISTANT,
            fragment_concision(max_chars),
            Fragment("Based on the user's new information, give the updated memory."),
        ]
    )

    user_fragments: UserFragments = UserFragments(
        [
            fragment_current_time(),
            fragment_memory_context(current_memory),
            Fragment(f"User Update: {update_text}"),
            Fragment("New Memory Summary:"),
        ]
    )
    return PromptFragments((system_fragments, user_fragments))


def recovery_prompt(
    failed_command: str,
    error_output: str,
    current_memory: str,
    original_explanation: str | None = None,
    config: Config | None = None,
) -> PromptFragments:
    """Generate system and user fragments for suggesting recovery actions."""
    cfg = config or Config()
    max_chars = int(cfg.get("memory_max_chars", 500))

    system_fragments: SystemFragments = SystemFragments(
        [
            Fragment(
                "You are a Kubernetes troubleshooting assistant. A kubectl "
                "command failed. Analyze the error and suggest potential "
                "next steps or fixes. Provide concise bullet points."
            ),
            fragment_concision(max_chars),
        ]
    )

    fragment_failure = Fragment(f"""Failed Command: {failed_command}
Error Output: {error_output}
{(original_explanation or "") and f"Explanation: {original_explanation}"}""")

    user_fragments: UserFragments = UserFragments(
        [
            fragment_current_time(),
            fragment_failure,
            Fragment(
                "Troubleshooting Suggestions (provide concise bullet points "
                "or a brief explanation):"
            ),
        ]
    )
    return PromptFragments((system_fragments, user_fragments))


# Template for planning autonomous vibe commands
def plan_vibe_fragments() -> PromptFragments:
    """Get prompt fragments for planning autonomous vibe commands.

    Args:
        config: Optional Config instance.

    Returns:
        PromptFragments: System fragments and base user fragments.
                         Caller adds memory and request fragments.
    """
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
            "wait until pod 'bar' finishes spinning up",
            {
                "action_type": str(ActionType.COMMAND.value),
                "commands": [
                    "wait",
                    "pod",
                    "bar",
                    "--for=condition=ready",
                    "--timeout=10s",
                ],
                "explanation": "Waiting on pod ready with 10s timeout to avoid "
                "indefinite blocking.",
            },
        ),
        (
            "We need to create multiple resources for our application.",
            "create the frontend and backend pods",
            {
                "action_type": str(ActionType.COMMAND.value),
                "commands": ["create", "-f", "-"],
                "yaml_manifest": (
                    "apiVersion: v1\\n"
                    "kind: Pod\\n"
                    "metadata:\\n"
                    "  name: frontend\\n"
                    "  labels:\\n"
                    "    app: foo\\n"
                    "    component: frontend\\n"
                    "spec:\\n"
                    "  containers:\\n"
                    "  - name: nginx\\n"
                    "    image: nginx\\n"
                    "---\\n"
                    "apiVersion: v1\\n"
                    "kind: Pod\\n"
                    "metadata:\\n"
                    "  name: backend\\n"
                    "  labels:\\n"
                    "    app: foo\\n"
                    "    component: backend\\n"
                    "spec:\\n"
                    "  containers:\\n"
                    "  - name: alpine\\n"
                    "    image: alpine\\n"
                    '    command: ["sleep", "infinity"]'
                ),
                "explanation": "Creating frontend and backend pods using the "
                "provided YAML manifest.",
            },
        ),
    ]
    system_fragments.append(
        Fragment(f"""Examples:\n\n{format_ml_examples(vibe_examples_data)}
""")
    )

    # User fragments will be added by the caller (memory context, actual request)
    user_fragments.append(
        Fragment(
            "Consider the user's goal and current memory context to plan the next "
            "action:"
        )
    )

    return PromptFragments((system_fragments, user_fragments))


# Template for summarizing vibe autonomous command output
def vibe_autonomous_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing command output in autonomous mode.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string. # New docstring

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


# Template for planning kubectl port-forward commands
PLAN_PORT_FORWARD_PROMPT: PromptFragments = create_planning_prompt(
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
                    "explanation": "User asked to port-forward pod in test namespace.",
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
                    "explanation": "User asked to port-forward a pod in production, "
                    "assuming default ports.",
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


# Template for summarizing 'kubectl port-forward' output
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


# Template for summarizing 'kubectl diff' output
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


# Template for planning kubectl diff commands
PLAN_DIFF_PROMPT: PromptFragments = create_planning_prompt(
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
                    "explanation": "User asked for a server-side diff of a local file.",
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
                    "explanation": "User asked to diff generated manifest in staging.",
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


# This is the correct function, the tuple definition below will be removed.
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


# Template for planning 'vibectl check' commands
def plan_check_fragments() -> PromptFragments:
    """Get prompt fragments for planning 'vibectl check' commands."""
    system_fragments: SystemFragments = SystemFragments([])
    user_fragments: UserFragments = UserFragments([])

    # System: Core instructions and role for 'check'
    system_fragments.append(
        Fragment(
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

    # System: Examples for 'check'
    check_examples_data: list[MLExampleItem] = [
        (
            "Namespace 'default' has pods: nginx-1 (Running), nginx-2 (Running).",
            "are all pods in the default namespace running?",
            {
                "action_type": str(ActionType.DONE.value),
                "exit_code": 0,
                "explanation": "All pods listed in memory for 'default' are Running.",
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
            "Attempt deletion of all pods in the cluster and ensure they are deleted.",
            {
                "action_type": str(ActionType.ERROR.value),
                "message": "The 'check' command can't ensure actions; it only "
                "evaluates predicates.",
            },
        ),
    ]
    system_fragments.append(
        Fragment(f"""Examples for 'vibectl check':

{format_ml_examples(check_examples_data, request_label="Predicate")}

Note on multi-step COMMAND example: If a COMMAND action is planned, `vibectl` will
execute it and the output will be fed back into your memory for a subsequent planning
step. You would then use that new information to issue another COMMAND or a DONE action.
""")
    )

    # User fragments will be added by the caller (memory context, actual predicate)
    user_fragments.append(
        Fragment(
            "Evaluate the following based on your memory and the plan you develop:"
        )
    )

    return PromptFragments((system_fragments, user_fragments))
