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
from .schema import LLMCommandResponse
from .types import Examples, Fragment, PromptFragments, SystemFragments, UserFragments

# Regenerate the shared JSON schema definition string from the Pydantic model
_SCHEMA_DEFINITION_JSON = json.dumps(LLMCommandResponse.model_json_schema(), indent=2)

logger = logging.getLogger(__name__)


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
appropriate arguments *following* 'kubectl {command}' and respond with a JSON
object matching the provided schema.

The action '{command}' is implied by the context.

Focus on extracting resource names, types, namespaces, selectors, and flags
from the request.""")
    )

    # System: Schema definition and key fields reminder
    system_fragments.append(
        Fragment(f"""
Your response MUST be a valid JSON object conforming to this schema:
```json
{schema_definition}
```

Key fields:
- `action_type`: Specify the intended action (usually COMMAND for planning args).
- `commands`: List of string arguments *following* `kubectl {command}`. Include flags
  like `-n`, `-f -`, but *exclude* the command verb itself. **MUST be a JSON array
  of strings, e.g., [\"pods\", \"-n\", \"kube-system\"], NOT a single string like
  \"pods -n kube-system\" or '[\"pods\", \"-n\", \"kube-system\"]' **.
- `yaml_manifest`: YAML content as a string (primarily for `create`).
- `explanation`: Brief explanation of the planned arguments.
- `error`: Required if action_type is ERROR (e.g., request is unclear).
- `wait_duration_seconds`: Required if action_type is WAIT.""")
    )

    # System: Formatted examples
    formatted_examples = (
        "Example inputs (natural language target descriptions) and "
        "expected JSON outputs:\n"
    )
    formatted_examples += "\n".join(
        [
            f'- Target: "{req}" -> \n'
            f"Expected JSON output:\n{json.dumps(output, indent=2)}"
            for req, output in examples
        ]
    )
    system_fragments.append(Fragment(formatted_examples))

    # User: Request prompt structure (placeholders removed)
    # Caller will add actual memory and request strings as separate user fragments.
    user_fragments.append(Fragment("Here's the request:"))
    # User fragment for memory will be added by caller
    # User fragment for request will be added by caller

    return PromptFragments((system_fragments, user_fragments))


def create_summary_prompt(
    description: str,
    focus_points: list[str],
    example_format: list[str],
    config: Config | None = None,  # Add config for formatting fragments
) -> PromptFragments:
    """Create standard summary prompt fragments for kubectl command output.

    Args:
        description: Description of what to summarize
        focus_points: List of what to focus on in the summary
        example_format: List of lines showing the expected output format
        config: Optional Config instance to use.

    Returns:
        PromptFragments: System fragments and base user fragments (excluding memory).
                         Caller adds memory fragment first if needed.
    """
    system_fragments: SystemFragments = SystemFragments([])
    user_fragments: UserFragments = UserFragments([])  # Base user fragments

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
                    "action_type": "COMMAND",
                    "commands": ["pods", "-n", "kube-system"],
                    "explanation": "Getting pods in the kube-system namespace.",
                },
            ),
            (
                "pods with app=nginx label",  # Target description
                {
                    "action_type": "COMMAND",
                    "commands": ["pods", "--selector=app=nginx"],
                    "explanation": "Getting pods matching the label app=nginx.",
                },
            ),
            (
                "all pods in every namespace",  # Target description
                {
                    "action_type": "COMMAND",
                    "commands": ["pods", "--all-namespaces"],
                    "explanation": "Getting all pods across all namespaces.",
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


# Template for summarizing 'kubectl get' output
def get_resource_prompt(
    config: Config | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl get output.

    Args:
        config: Optional Config instance.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    return create_summary_prompt(
        description="Summarize this kubectl output.",
        focus_points=["key information", "notable patterns", "potential issues"],
        example_format=[
            "[bold]3 pods[/bold] in [blue]default namespace[/blue], all "
            "[green]Running[/green]",
            "[bold]nginx-pod[/bold] [italic]running for 2 days[/italic]",
            "[yellow]Warning: 2 pods have high restart counts[/yellow]",
        ],
        config=config,
    )


# Template for summarizing 'kubectl describe' output
def describe_resource_prompt(
    config: Config | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl describe output.

    Args:
        config: Optional Config instance.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    return create_summary_prompt(
        description="Summarize this kubectl describe output. Limit to 200 words.",
        focus_points=["key details", "issues needing attention"],
        example_format=[
            "[bold]nginx-pod[/bold] in [blue]default[/blue]: [green]Running[/green]",
            "[yellow]Readiness probe failing[/yellow], "
            "[italic]last restart 2h ago[/italic]",
            "[red]OOMKilled 3 times in past day[/red]",
        ],
        config=config,
    )


# Template for summarizing 'kubectl logs' output
def logs_prompt(
    config: Config | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl logs output.

    Args:
        config: Optional Config instance.

    Returns:
        PromptFragments: System fragments and user fragments
    """
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
        config=config,
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
                    "action_type": "COMMAND",
                    "commands": ["pods", "nginx"],
                    "explanation": "Describing the pod named nginx.",
                },
            ),
            (
                "the deployment in foo namespace",  # Target description
                {
                    "action_type": "COMMAND",
                    "commands": ["deployments", "-n", "foo"],
                    "explanation": "Describing deployments in the foo namespace.",
                },
            ),
            (
                "details of all pods with app=nginx",  # Target description
                {
                    "action_type": "COMMAND",
                    "commands": ["pods", "--selector=app=nginx"],
                    "explanation": "Describing pods matching the label app=nginx.",
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
                    "action_type": "COMMAND",
                    "commands": ["pod/nginx"],
                    "explanation": "Getting logs for the pod named nginx.",
                },
            ),
            (
                "logs from the api container in app pod",  # Target description
                {
                    "action_type": "COMMAND",
                    "commands": ["pod/app", "-c", "api"],
                    "explanation": "Getting logs for the 'api' container in pod 'app'.",
                },
            ),
            (
                "the last 100 lines from all pods with app=nginx",  # Target description
                {
                    "action_type": "COMMAND",
                    "commands": ["--selector=app=nginx", "--tail=100"],
                    "explanation": (
                        "Getting the last 100 log lines for pods with label app=nginx."
                    ),
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
                    "action_type": "COMMAND",
                    "commands": ["-f", "-", "-n", "default"],
                    "yaml_manifest": (
                        "---\n"
                        "apiVersion: v1\n"
                        "kind: Pod\n"
                        "metadata:\n"
                        "  name: nginx-hello\n"
                        "  labels:\n"
                        "    app: nginx\n"
                        "spec:\n"
                        "  containers:\n"
                        "  - name: nginx\n"
                        "    image: nginx:latest\n"
                        "    ports:\n"
                        "    - containerPort: 80"
                    ),
                    "explanation": "Creating a simple Nginx pod.",
                },
            ),
            (
                "create a configmap with HTML content",  # Explicit creation
                {
                    "action_type": "COMMAND",
                    "commands": ["-f", "-"],
                    "yaml_manifest": (
                        "---\n"
                        "apiVersion: v1\n"
                        "kind: ConfigMap\n"
                        "metadata:\n"
                        "  name: html-content\n"
                        "data:\n"
                        "  index.html: |\n"
                        "    <html><body><h1>Hello World</h1></body></html>"
                    ),
                    "explanation": "Creating a ConfigMap with HTML data.",
                },
            ),
            (
                "frontend and backend pods for my application",  # Implicit creation
                {
                    "action_type": "COMMAND",
                    "commands": ["-f", "-"],
                    "yaml_manifest": (
                        "---\n"
                        "apiVersion: v1\n"
                        "kind: Pod\n"
                        "metadata:\n"
                        "  name: frontend\n"
                        "  labels:\n"
                        "    app: myapp\n"
                        "    component: frontend\n"
                        "spec:\n"
                        "  containers:\n"
                        "  - name: frontend\n"
                        "    image: nginx:latest\n"
                        "    ports:\n"
                        "    - containerPort: 80\n"
                        "---\n"
                        "apiVersion: v1\n"
                        "kind: Pod\n"
                        "metadata:\n"
                        "  name: backend\n"
                        "  labels:\n"
                        "    app: myapp\n"
                        "    component: backend\n"
                        "spec:\n"
                        "  containers:\n"
                        "  - name: backend\n"
                        "    image: redis:latest\n"
                        "    ports:\n"
                        "    - containerPort: 6379"
                    ),
                    "explanation": "Creating two pods using a multi-document YAML.",
                },
            ),
            (
                "spin up a basic redis deployment",  # Explicit creation verb
                {
                    "action_type": "COMMAND",
                    "commands": ["-f", "-"],
                    "yaml_manifest": (
                        "---\n"
                        "apiVersion: apps/v1\n"
                        "kind: Deployment\n"
                        "metadata:\n"
                        "  name: redis-deployment\n"
                        "spec:\n"
                        "  replicas: 1\n"
                        "  selector:\n"
                        "    matchLabels:\n"
                        "      app: redis\n"
                        "  template:\n"
                        "    metadata:\n"
                        "      labels:\n"
                        "        app: redis\n"
                        "    spec:\n"
                        "      containers:\n"
                        "      - name: redis\n"
                        "        image: redis:alpine\n"
                        "        ports:\n"
                        "        - containerPort: 6379\n"
                    ),
                    "explanation": "Creating a single-replica Redis deployment.",
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
                    "action_type": "COMMAND",
                    "commands": ["--output=json"],
                    "explanation": "Getting version information in JSON format.",
                },
            ),
            (
                "client version only",  # Target/flag description
                {
                    "action_type": "COMMAND",
                    "commands": ["--client=true", "--output=json"],
                    "explanation": "Getting only the client version in JSON format.",
                },
            ),
            (
                "version in yaml",  # Target/flag description
                {
                    "action_type": "COMMAND",
                    "commands": ["--output=yaml"],
                    "explanation": "Getting version information in YAML format.",
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
                    "action_type": "COMMAND",
                    "commands": ["dump"],  # Default behavior is dump
                    "explanation": "Getting detailed cluster information using dump.",
                },
            ),
            (
                "basic cluster info",  # Target description
                {
                    "action_type": "COMMAND",
                    "commands": [],  # No extra args needed for basic info
                    "explanation": "Getting basic cluster endpoint information.",
                },
            ),
            (
                "detailed cluster info",  # Target description
                {
                    "action_type": "COMMAND",
                    "commands": ["dump"],
                    "explanation": "Getting detailed cluster information using dump.",
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
                    "action_type": "COMMAND",
                    "commands": [],  # Default namespace is implicit
                    "explanation": "Getting events in the default namespace.",
                },
            ),
            (
                "events for pod nginx",  # Target description
                {
                    "action_type": "COMMAND",
                    "commands": ["--for=pod/nginx"],
                    "explanation": "Getting events related to the pod named nginx.",
                },
            ),
            (
                "all events in all namespaces",  # Target description
                {
                    "action_type": "COMMAND",
                    "commands": ["--all-namespaces"],  # Use -A or --all-namespaces
                    "explanation": "Getting all events across all namespaces.",
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


# Template for summarizing 'kubectl cluster-info' output
def cluster_info_prompt(
    config: Config | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl cluster-info output.

    Args:
        config: Optional Config instance.

    Returns:
        PromptFragments: System fragments and user fragments
    """
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
        config=config,
    )


# Template for summarizing 'kubectl version' output
def version_prompt(
    config: Config | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl version output.

    Args:
        config: Optional Config instance.

    Returns:
        PromptFragments: System fragments and user fragments
    """
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
        config=config,
    )


# Template for summarizing 'kubectl events' output
def events_prompt(
    config: Config | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl events output.

    Args:
        config: Optional Config instance.

    Returns:
        PromptFragments: System fragments and user fragments
    """
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
        config=config,
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
                    "action_type": "COMMAND",
                    "commands": ["pod", "nginx"],
                    "explanation": "Deleting the pod named nginx.",
                },
            ),
            (
                "deployment in kube-system namespace",  # Target description
                {
                    "action_type": "COMMAND",
                    "commands": ["deployment", "-n", "kube-system"],
                    "explanation": "Deleting deployments in the kube-system namespace.",
                },
            ),
            (
                "all pods with app=nginx",  # Target description
                {
                    "action_type": "COMMAND",
                    "commands": ["pods", "--selector=app=nginx"],
                    "explanation": "Deleting pods matching the label app=nginx.",
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


# Template for summarizing 'kubectl delete' output
def delete_resource_prompt(
    config: Config | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl delete output.

    Args:
        config: Optional Config instance.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    return create_summary_prompt(
        description="Summarize kubectl delete results.",
        focus_points=["resources deleted", "potential issues", "warnings"],
        example_format=[
            "[bold]3 pods[/bold] successfully deleted from "
            "[blue]default namespace[/blue]",
            "[yellow]Warning: Some resources are still terminating[/yellow]",
        ],
        config=config,
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
                    "action_type": "COMMAND",
                    "commands": ["deployment/nginx", "--replicas=3"],
                    "explanation": "Scaling the nginx deployment to 3 replicas.",
                },
            ),
            (
                "the redis statefulset to 5 replicas in the cache namespace",
                {
                    "action_type": "COMMAND",
                    "commands": ["statefulset/redis", "--replicas=5", "-n", "cache"],
                    "explanation": (
                        "Scaling the redis statefulset in the cache "
                        "namespace to 5 replicas."
                    ),
                },
            ),
            (
                "down the api deployment",
                {
                    "action_type": "COMMAND",
                    "commands": [
                        "deployment/api",
                        "--replicas=1",
                    ],  # Assuming scale down means 1
                    "explanation": "Scaling down the api deployment to 1 replica.",
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


# Template for summarizing 'kubectl scale' output
def scale_resource_prompt(
    config: Config | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl scale output.

    Args:
        config: Optional Config instance.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    return create_summary_prompt(
        description="Summarize scaling operation results.",
        focus_points=["changes made", "current state", "issues or concerns"],
        example_format=[
            "[bold]deployment/nginx[/bold] scaled to [green]3 replicas[/green]",
            "[yellow]Warning: Scale operation might take time to complete[/yellow]",
            "[blue]Namespace: default[/blue]",
        ],
        config=config,
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
                    "action_type": "COMMAND",
                    "commands": ["deployment/my-app", "--for=condition=Available"],
                    "explanation": "Waiting for my-app deployment to become Available.",
                },
            ),
            (
                "until the pod nginx becomes ready with 5 minute timeout",
                {
                    "action_type": "COMMAND",
                    "commands": ["pod/nginx", "--for=condition=Ready", "--timeout=5m"],
                    "explanation": (
                        "Waiting up to 5 minutes for the nginx pod to become Ready."
                    ),
                },
            ),
            (
                "for all jobs in billing namespace to complete",
                {
                    "action_type": "COMMAND",
                    "commands": [
                        "jobs",
                        "--all",
                        "-n",
                        "billing",
                        "--for=condition=Complete",
                    ],
                    "explanation": (
                        "Waiting for all jobs in the billing namespace to Complete."
                    ),
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


# Template for summarizing 'kubectl wait' output
def wait_resource_prompt(
    config: Config | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl wait output.

    Args:
        config: Optional Config instance.

    Returns:
        PromptFragments: System fragments and user fragments
    """
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
        config=config,
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
                    "action_type": "COMMAND",
                    "commands": ["status", "deployment/nginx"],
                    "explanation": "Checking the rollout status of nginx deployment.",
                },
            ),
            (
                "frontend deployment to revision 2",  # rollout action description
                {
                    "action_type": "COMMAND",
                    "commands": ["undo", "deployment/frontend", "--to-revision=2"],
                    "explanation": (
                        "Rolling back the frontend deployment to revision 2."
                    ),
                },
            ),
            (
                "the rollout of my-app deployment in production namespace",
                {
                    "action_type": "COMMAND",
                    "commands": ["pause", "deployment/my-app", "-n", "production"],
                    "explanation": (
                        "Pausing the rollout for the my-app deployment in the "
                        "production namespace."
                    ),
                },
            ),
            (
                "all deployments in default namespace",
                {
                    "action_type": "COMMAND",
                    "commands": [
                        "restart",
                        "deployment",
                        "-n",
                        "default",
                    ],  # Or add selector if needed
                    "explanation": "Restarting all deployments in default namespace.",
                },
            ),
            (
                "history of statefulset/redis",
                {
                    "action_type": "COMMAND",
                    "commands": ["history", "statefulset/redis"],
                    "explanation": (
                        "Showing the rollout history for the redis statefulset."
                    ),
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


# Template for summarizing 'kubectl create' output
def create_resource_prompt(
    config: Config | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl create output.

    Args:
        config: Optional Config instance.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    return create_summary_prompt(
        description="Summarize resource creation results.",
        focus_points=["resources created", "issues or concerns"],
        example_format=[
            "Created [bold]nginx-pod[/bold] in [blue]default namespace[/blue]",
            "[green]Successfully created[/green] with "
            "[italic]default resource limits[/italic]",
            "[yellow]Note: No liveness probe configured[/yellow]",
        ],
        config=config,
    )


# Template for summarizing 'kubectl rollout status' output
def rollout_status_prompt(
    config: Config | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl rollout status output.

    Args:
        config: Optional Config instance.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    return create_summary_prompt(
        description="Summarize rollout status.",
        focus_points=["progress", "completion status", "issues or delays"],
        example_format=[
            "[bold]deployment/frontend[/bold] rollout "
            "[green]successfully completed[/green]",
            "[yellow]Still waiting for 2/5 replicas[/yellow]",
            "[italic]Rollout started 5 minutes ago[/italic]",
        ],
        config=config,
    )


# Template for summarizing 'kubectl rollout history' output
def rollout_history_prompt(
    config: Config | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl rollout history output.

    Args:
        config: Optional Config instance.

    Returns:
        PromptFragments: System fragments and user fragments
    """
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
        config=config,
    )


# Template for summarizing other rollout command outputs
def rollout_general_prompt(
    config: Config | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl rollout output.

    Args:
        config: Optional Config instance.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    return create_summary_prompt(
        description="Summarize rollout command results.",
        focus_points=["key operation details"],
        example_format=[
            "[bold]Deployment rollout[/bold] [green]successful[/green]",
            "[blue]Updates applied[/blue] to [bold]my-deployment[/bold]",
            "[yellow]Warning: rollout took longer than expected[/yellow]",
        ],
        config=config,
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


def fragment_memory_context(current_memory: str) -> Fragment:
    return Fragment(f"Previous Memory:\n{current_memory}")


def memory_update_prompt(
    command: str,
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
Command: {command}
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
    update_text: str | None = None,  # Placeholder for format()
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
                "next steps or fixes. Provide concise bullet "
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

Your options are:
- COMMAND: execute a single kubectl command, to directly advance the user's goal or
  reduce uncertainty about the user's goal and its status.
- FEEDBACK: return feedback to the user explaining uncertainty about the user's goal
  that you cannot reduce by planning a COMMAND.
- ERROR: the user's goal is clear but you cannot plan a next command.
- WAIT: pause further work for at minimum some specified duration.

You may be in a non-interactive context, so do NOT plan blocking commands like
'kubectl wait' or 'kubectl port-forward' unless given an explicit request to the
contrary, and even then use appropriate timeouts.

You cannot run arbitrary shell commands, but planning appropriate `kubectl exec`
commands to run inside pods may be appropriate.""")
    )

    # System: Schema definition (f-string needed here)
    system_fragments.append(
        Fragment(
            f"""Your response MUST be a valid JSON object conforming to this schema:
```json
{_SCHEMA_DEFINITION_JSON}
```

Key fields reminder:
- `action_type`: COMMAND, FEEDBACK, ERROR, or WAIT.
- `commands`: If action_type is COMMAND, this is a JSON list of strings representing the
  *full* kubectl subcommand *including the verb*
  (e.g., ["get", "pods", "-n", "app"]).
- `yaml_manifest`: If action_type is COMMAND and involves creating/applying complex
  resources, provide the YAML here as a single string.
- `error`: A description of why you will not plan a next command. Required if
  action_type is ERROR.
- `explanation`: Brief explanation justifying the action taken.
- `wait_duration_seconds`: Required if action_type is WAIT."""
        )
    )

    # System: Examples
    system_fragments.append(
        Fragment(
            """Examples:

Memory: "We are working in namespace 'app'. Deployed 'frontend' and 'backend' services."
Request: "check if everything is healthy"
Output:
{  "action_type": "COMMAND",
    "commands": ["get", "pods", "-n", "app"],
    "explanation": "Checking pod status in the 'app' namespace."
}

Memory: "The health-check pod is called 'health-check'."
Request: "Tell me about the health-check pod and the database deployment."
Output:
{  "action_type": "COMMAND",
    "commands": ["get", "pods", "-l", "app=health-check"],
    "explanation": "Describing the health-check pod. Database deployment next..."
}

Memory: "We need to debug why the database pod keeps crashing."
Request: ""
Output:
{  "action_type": "COMMAND",
    "commands": ["describe", "pod", "-l", "app=database"],
    "explanation": "Examining the database pod based on memory context."
}

Memory: ""
Request: "help me troubleshoot the database pod"
Output:
{  "action_type": "COMMAND",
    "commands": ["describe", "pod", "-l", "app=database"],
    "explanation": "Describing the database pod as requested."
}

Memory: "Wait until pod 'foo' is deleted"
Request: ""
Output:
{  "action_type": "ERROR",
    "error": "The command 'kubectl wait --for=delete pod/foo' is potentially blocking.",
    "explanation": "Refusing to run a potentially blocking 'wait' command."
}

Memory: "You MUST NOT delete the 'health-check' pod."
Request: "delete the health-check pod"
Output:
{  "action_type": "ERROR",
    "error": "You MUST NOT delete the 'health-check' pod.",
    "explanation": "Memory indicates this pod is not allowed to be deleted."
}

Memory: "The cluster has 64GiB of memory available."
Request: "set the memory request for the app deployment to 128GiB"
Output:
{  "action_type": "FEEDBACK",
    "explanation": "The cluster does not have enough memory to meet the request."
}

Memory: ""
Request: "lkbjwqnfl alkfjlkads"
Output:
{  "action_type": "FEEDBACK",
    "explanation": "It is not clear what you want to do. Please try again."
}

Memory: ""
Request: "wait until pod 'bar' finishes spinning up"
Output:
{  "action_type": "COMMAND",
    "commands": ["wait", "pod", "bar", "--for=condition=ready", "--timeout=10s"],
    "explanation": "Waiting for pod 'bar' to be running, with tight timeout."
}

Memory: "We need to create multiple resources for our application."
Request: "create the frontend and backend pods"
Output:
{  "action_type": "COMMAND",
    "commands": ["create", "-f", "-"],
    "yaml_manifest": (
        "apiVersion: v1\\nkind: Pod\\nmetadata:\\n  name: frontend\\n  labels:\\n"
        "    app: foo\\n    component: frontend\\nspec:\\n  containers:\\n"
        "  - name: frontend\\n    image: nginx:latest\\n    ports:\\n"
        "    - containerPort: 80\\n---\\napiVersion: v1\\nkind: Pod\\nmetadata:\\n"
        "  name: backend\\n  labels:\\n    app: foo\\n    component: backend\\nspec:\\n"
        "  containers:\\n  - name: backend\\n    image: redis:latest\\n    ports:\\n"
        "    - containerPort: 6379"
    ),
    "explanation": "Creating frontend and backend pods using YAML as requested."
}

# END Example inputs (memory and request) and outputs"""
        )
    )

    # User: Instruction for output format and prompt structure (placeholders removed)
    user_fragments.append(
        Fragment(
            "Your output MUST be ONLY the JSON object conforming to the schema, "
            "based on the user's goal:"
        )
    )
    # User fragment for memory will be added by caller
    # User fragment for request will be added by caller
    user_fragments.append(
        Fragment("Output:")
    )  # Instructs where the JSON output should start

    return PromptFragments((system_fragments, user_fragments))


# Template for summarizing vibe autonomous command output
def vibe_autonomous_prompt(config: Config | None = None) -> PromptFragments:
    """Get prompt fragments for summarizing command output in autonomous mode.

    Args:
        config: Optional Config instance.

    Returns:
        PromptFragments: System fragments and user fragments.
    """
    system_fragments: SystemFragments = SystemFragments([])
    user_fragments: UserFragments = UserFragments([])

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
        config
    )
    system_fragments.extend(formatting_system_fragments)
    user_fragments.extend(formatting_user_fragments)  # Includes memory

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
        "port-forward connections to kubernetes resources. IMPORTANT: "
        "1) Resource name MUST be the first argument, "
        "2) followed by port specifications, "
        "3) then any flags. Do NOT include 'kubectl' or '--kubeconfig' in "
        "your response."
    ),
    examples=Examples(
        [
            (
                "port 8080 of pod nginx to my local 8080",
                {
                    "action_type": "COMMAND",
                    "commands": ["pod/nginx", "8080:8080"],
                    "explanation": (
                        "Forwarding local port 8080 to port 8080 of the nginx pod."
                    ),
                },
            ),
            (
                "the redis service port 6379 on local port 6380",
                {
                    "action_type": "COMMAND",
                    "commands": ["service/redis", "6380:6379"],
                    "explanation": (
                        "Forwarding local port 6380 to port 6379 of the redis service."
                    ),
                },
            ),
            (
                "deployment webserver port 80 to my local 8000",
                {
                    "action_type": "COMMAND",
                    "commands": ["deployment/webserver", "8000:80"],
                    "explanation": (
                        "Forwarding local port 8000 to port 80 on webserver deployment."
                    ),
                },
            ),
            (
                "my local 5000 to port 5000 on the api pod in namespace test",
                {
                    "action_type": "COMMAND",
                    "commands": ["pod/api", "5000:5000", "--namespace", "test"],
                    "explanation": (
                        "Forwarding local port 5000 to port 5000 of the "
                        "api pod in the test namespace."
                    ),
                },
            ),
            (
                "ports with the app running on namespace production",
                {
                    "action_type": "COMMAND",
                    "commands": [
                        "pod/app",
                        "8080:80",
                        "--namespace",
                        "production",
                    ],  # Needs better inference?
                    "explanation": (
                        "Forwarding local port 8080 to port 80 of the app "
                        "pod in the production namespace."
                    ),
                },
            ),
        ]
    ),
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


# Template for summarizing 'kubectl port-forward' output
def port_forward_prompt(
    config: Config | None = None,
) -> PromptFragments:
    """Get prompt fragments for summarizing kubectl port-forward output.

    Args:
        config: Optional Config instance.

    Returns:
        PromptFragments: System fragments and user fragments
    """
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
        config=config,
    )
