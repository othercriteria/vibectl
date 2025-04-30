"""
Prompt templates for LLM interactions with kubectl output.

Each template follows a consistent format using rich.Console() markup for styling,
ensuring clear and visually meaningful summaries of Kubernetes resources.
"""

import datetime
import json

from .config import Config
from .schema import LLMCommandResponse

# No memory imports at the module level to avoid circular imports

# Regenerate the shared JSON schema definition string from the Pydantic model
_SCHEMA_DEFINITION_JSON = json.dumps(LLMCommandResponse.model_json_schema(), indent=2)


def refresh_datetime() -> str:
    """Refresh and return the current datetime string.

    Returns:
        str: The current datetime in "%Y-%m-%d %H:%M:%S" format
    """
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def format_examples(examples: list[tuple[str, str]]) -> str:
    """Format a list of input/output examples into a consistent string format.

    Args:
        examples: List of tuples where each tuple contains (input_text, output_text)

    Returns:
        str: Formatted examples string
    """
    formatted_examples = "Example inputs and outputs:\n\n"
    for input_text, output_text in examples:
        formatted_examples += f'Input: "{input_text}"\n'
        formatted_examples += f"Output:\n{output_text}\n\n"
    return formatted_examples.rstrip()


def create_planning_prompt(
    command: str,
    description: str,
    examples: list[tuple[str, dict]],
    schema_definition: str | None = None,
) -> str:
    """Create a standard planning prompt for kubectl commands using JSON schema.

    This prompt assumes the kubectl command verb (get, describe, delete, etc.)
    is already determined by the context (e.g., the specific vibectl subcommand
    being run). The LLM's task is to interpret the natural language request
    to identify the target resource(s) and any necessary arguments/flags
    (like namespace, selectors, specific names), and then format the response
    as JSON according to the provided schema.

    Args:
        command: The kubectl command verb (get, describe, etc.) used for context.
        description: Description of the overall goal (e.g., "getting resources").
        examples: List of tuples where each tuple contains:
                  (natural_language_target_description, expected_json_output_dict)
                  The target description should focus on *what* resource(s) to
                  target, not the action itself (e.g., "pods in kube-system"
                  instead of "get pods in kube-system").
        schema_definition: JSON schema definition string.
                           Must be provided for structured JSON output.

    Returns:
        str: Formatted planning prompt template
    """
    if not schema_definition:
        raise ValueError(
            "schema_definition must be provided for create_planning_prompt"
        )

    # Schema-based prompt
    prompt_header = f"""You are planning arguments for the 'kubectl {command}' command.
Given a natural language request describing the target resource(s), determine the
appropriate arguments *following* 'kubectl {command}' and respond with a JSON
object matching the provided schema.

Focus on extracting resource names, types, namespaces, selectors, and flags
from the request.

The action '{command}' is implied.

Your response MUST be a valid JSON object conforming to this schema:
```json
{schema_definition}
```

Key fields:
- `action_type`: Specify the intended action (usually COMMAND for planning args).
- `commands`: List of string arguments *following* `kubectl {command}`. Include flags
  like `-n`, `-f -`, but *exclude* the command verb itself. **MUST be a JSON array
  of strings, e.g., `["pods", "-n", "kube-system"]`, NOT a single string like
  `"pods -n kube-system"` or `\'["pods", "-n", "kube-system"]\'` **.
- `yaml_manifest`: YAML content as a string (primarily for `create`).
- `explanation`: Brief explanation of the planned arguments.
- `error`: Required if action_type is ERROR (e.g., request is unclear).
- `wait_duration_seconds`: Required if action_type is WAIT.

Example inputs (natural language target descriptions) and expected JSON outputs:
"""
    # Format examples to show expected JSON structure
    # The 'req' here is the *target description*, not the full original request.
    formatted_examples = "\n".join(
        [
            f'- Target: "{req}" -> '
            f"Expected JSON output:\n{json.dumps(output, indent=2)}"
            for req, output in examples
        ]
    )

    # Append the placeholders for memory and request
    # '__REQUEST_PLACEHOLDER__' will contain the user's original request.
    prompt = (
        prompt_header
        + formatted_examples
        + '\n\nHere\'s the request:\n\nMemory: "__MEMORY_CONTEXT_PLACEHOLDER__"'
        + '\nRequest: "__REQUEST_PLACEHOLDER__"'  # The user's original full request
    )

    return prompt


def create_summary_prompt(
    description: str,
    focus_points: list[str],
    example_format: list[str],
) -> str:
    """Create a standard summary prompt for kubectl command output.

    Args:
        description: Description of what to summarize
        focus_points: List of what to focus on in the summary
        example_format: List of lines showing the expected output format

    Returns:
        str: Formatted summary prompt with formatting instructions
    """
    focus_text = "\n".join([f"- {point}" for point in focus_points])
    formatted_example = "\n".join(example_format)

    # Get the formatting instructions directly
    formatting_instructions = get_formatting_instructions()

    return f"""{description}
Focus on {focus_text}.

{formatting_instructions}

Example format:
{formatted_example}

Here's the output:

{{output}}"""


# Common formatting instructions for all prompts
def get_formatting_instructions(config: Config | None = None) -> str:
    """Get formatting instructions with current datetime.

    Args:
        config: Optional Config instance to use. If not provided, creates a new one.

    Returns:
        str: Formatting instructions with current datetime
    """
    # Import here to avoid circular dependency
    from .memory import get_memory, is_memory_enabled

    current_time = refresh_datetime()
    cfg = config or Config()

    # Get custom instructions if they exist
    custom_instructions = cfg.get("custom_instructions")
    custom_instructions_section = ""
    if custom_instructions:
        custom_instructions_section = f"""
Custom instructions:
{custom_instructions}

"""

    # Get memory if it's enabled and exists
    memory_section = ""
    if is_memory_enabled(cfg):
        memory = get_memory(cfg)
        if memory:
            memory_section = f"""
Memory context:
{memory}

"""

    return f"""Format your response using rich.Console() markup syntax
with matched closing tags:
- [bold]resource names and key fields[/bold] for emphasis
- [green]healthy states[/green] for positive states
- [yellow]warnings or potential issues[/yellow] for concerning states
- [red]errors or critical issues[/red] for problems
- [blue]namespaces and other Kubernetes concepts[/blue] for k8s terms
- [italic]timestamps and metadata[/italic] for timing information

{custom_instructions_section}{memory_section}Important:
- Current date and time is {current_time}
- Timestamps in the future relative to this are not anomalies
- Do NOT use markdown formatting (e.g., #, ##, *, -)
- Use plain text with rich.Console() markup only
- Skip any introductory phrases like "This output shows" or "I can see"
- Be direct and concise"""


# Template for planning kubectl get commands
PLAN_GET_PROMPT = create_planning_prompt(
    command="get",
    description="getting Kubernetes resources",
    examples=[
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
    ],
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


# Template for summarizing 'kubectl get' output
def get_resource_prompt() -> str:
    """Get the prompt template for summarizing kubectl get output with current datetime.

    Returns:
        str: The get resource prompt template with current formatting instructions
    """
    prompt_template = create_summary_prompt(
        description="Summarize this kubectl output.",
        focus_points=["key information", "notable patterns", "potential issues"],
        example_format=[
            "[bold]3 pods[/bold] in [blue]default namespace[/blue], all "
            "[green]Running[/green]",
            "[bold]nginx-pod[/bold] [italic]running for 2 days[/italic]",
            "[yellow]Warning: 2 pods have high restart counts[/yellow]",
        ],
    )
    return prompt_template.format(output="{output}")


# Template for summarizing 'kubectl describe' output
def describe_resource_prompt() -> str:
    """Get the prompt template for summarizing kubectl describe output.

    Includes current datetime information for timestamp context.

    Returns:
        str: The describe resource prompt template with current formatting instructions
    """
    prompt_template = create_summary_prompt(
        description="Summarize this kubectl describe output. Limit to 200 words.",
        focus_points=["key details", "issues needing attention"],
        example_format=[
            "[bold]nginx-pod[/bold] in [blue]default[/blue]: [green]Running[/green]",
            "[yellow]Readiness probe failing[/yellow], "
            "[italic]last restart 2h ago[/italic]",
            "[red]OOMKilled 3 times in past day[/red]",
        ],
    )
    return prompt_template.format(output="{output}")


# Template for summarizing 'kubectl logs' output
def logs_prompt() -> str:
    """Get the prompt template for summarizing kubectl logs output.

    Includes current datetime information for timestamp context.

    Returns:
        str: The logs prompt template with current formatting instructions
    """
    prompt_template = create_summary_prompt(
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
    )
    return prompt_template.format(output="{output}")


# Template for planning kubectl describe commands
PLAN_DESCRIBE_PROMPT = create_planning_prompt(
    command="describe",
    description="Kubernetes resource details",
    examples=[
        (
            "the nginx pod",  # Target description
            {
                "action_type": "COMMAND",
                "commands": ["pods", "nginx"],
                "explanation": "Describing the pod named nginx.",
            },
        ),
        (
            "the deployment in kube-system namespace",  # Target description
            {
                "action_type": "COMMAND",
                "commands": ["deployments", "-n", "kube-system"],
                "explanation": "Describing deployments in the kube-system namespace.",
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
    ],
    schema_definition=_SCHEMA_DEFINITION_JSON,
)

# Template for planning kubectl logs commands
PLAN_LOGS_PROMPT = create_planning_prompt(
    command="logs",
    description="Kubernetes logs",
    examples=[
        (
            "logs from the nginx pod",  # Target description
            {
                "action_type": "COMMAND",
                "commands": ["pod/nginx"],
                "explanation": "Getting logs for the pod named nginx.",
            },
        ),
        (
            "logs from the api container in my-app pod",  # Target description
            {
                "action_type": "COMMAND",
                "commands": ["pod/my-app", "-c", "api"],
                "explanation": "Getting logs for the 'api' container in pod 'my-app'.",
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
    ],
    schema_definition=_SCHEMA_DEFINITION_JSON,
)

# Template for planning kubectl create commands - Uses the new schema approach
PLAN_CREATE_PROMPT = create_planning_prompt(
    command="create",
    description="creating Kubernetes resources using YAML manifests",
    examples=[
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
            "create a configmap with HTML content",  # Explicit creation request
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
            "frontend and backend pods for my application",  # Implicit creation request
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
    ],
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


# Template for planning kubectl version commands
PLAN_VERSION_PROMPT = create_planning_prompt(
    command="version",
    description="Kubernetes version information",
    examples=[
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
    ],
    schema_definition=_SCHEMA_DEFINITION_JSON,
)

# Template for planning kubectl cluster-info commands
PLAN_CLUSTER_INFO_PROMPT = create_planning_prompt(
    command="cluster-info",
    description="Kubernetes cluster information",
    examples=[
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
    ],
    schema_definition=_SCHEMA_DEFINITION_JSON,
)

# Template for planning kubectl events commands
# Note: We deliberately use the 'kubectl events' command here instead of
# 'kubectl get events'. While 'get events' works, 'kubectl events' is the
# more idiomatic command for viewing events and offers specific flags like --for.
PLAN_EVENTS_PROMPT = create_planning_prompt(
    command="events",  # Use the dedicated 'events' command
    description="Kubernetes events",
    examples=[
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
    ],
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


# Template for summarizing 'kubectl cluster-info' output
def cluster_info_prompt() -> str:
    """Get the prompt template for summarizing kubectl cluster-info output.

    Includes current datetime information for timestamp context.

    Returns:
        str: The cluster info prompt with current formatting instructions
    """
    prompt_template = create_summary_prompt(
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
    )
    return prompt_template.format(output="{output}")


# Template for summarizing 'kubectl version' output
def version_prompt() -> str:
    """Get the prompt template for summarizing kubectl version output.

    Includes current datetime information for timestamp context.

    Returns:
        str: The version prompt template with current formatting instructions
    """
    prompt_template = create_summary_prompt(
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
    )
    return prompt_template.format(output="{output}")


# Template for summarizing 'kubectl events' output
def events_prompt() -> str:
    """Get the prompt template for summarizing kubectl events output.

    Includes current datetime information for timestamp context.

    Returns:
        str: The events prompt template with current formatting instructions
    """
    prompt_template = create_summary_prompt(
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
    )
    return prompt_template.format(output="{output}")


# Template for planning kubectl delete commands
PLAN_DELETE_PROMPT = create_planning_prompt(
    command="delete",
    description="Kubernetes resources",
    examples=[
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
    ],
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


# Template for summarizing 'kubectl delete' output
def delete_resource_prompt() -> str:
    """Get the prompt template for summarizing kubectl delete output.

    Returns:
        str: The delete resource prompt template with current formatting instructions
    """
    prompt_template = create_summary_prompt(
        description="Summarize kubectl delete results.",
        focus_points=["resources deleted", "potential issues", "warnings"],
        example_format=[
            "[bold]3 pods[/bold] successfully deleted from "
            "[blue]default namespace[/blue]",
            "[yellow]Warning: Some resources are still terminating[/yellow]",
        ],
    )
    return prompt_template.format(output="{output}")


# Template for planning kubectl scale commands
PLAN_SCALE_PROMPT = create_planning_prompt(
    command="scale",
    description="scaling Kubernetes resources",
    examples=[
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
    ],
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


# Template for summarizing 'kubectl scale' output
def scale_resource_prompt() -> str:
    """Get the prompt template for summarizing kubectl scale output.

    Includes current datetime information for timestamp context.

    Returns:
        str: The scale resource prompt template with formatting instructions
    """
    prompt_template = create_summary_prompt(
        description="Summarize scaling operation results.",
        focus_points=["changes made", "current state", "issues or concerns"],
        example_format=[
            "[bold]deployment/nginx[/bold] scaled to [green]3 replicas[/green]",
            "[yellow]Warning: Scale operation might take time to complete[/yellow]",
            "[blue]Namespace: default[/blue]",
        ],
    )
    return prompt_template.format(output="{output}")


# Template for planning kubectl wait commands
PLAN_WAIT_PROMPT = create_planning_prompt(
    command="wait",
    description="waiting on Kubernetes resources",
    examples=[
        (
            "for the deployment my-app to be ready",
            {
                "action_type": "COMMAND",
                "commands": ["deployment/my-app", "--for=condition=Available"],
                "explanation": "Waiting for the my-app deployment to become Available.",
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
    ],
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


# Template for summarizing 'kubectl wait' output
def wait_resource_prompt() -> str:
    """Get the prompt template for summarizing kubectl wait output with current
    datetime.

    Returns:
        str: The wait resource prompt template with current formatting instructions
    """
    prompt_template = create_summary_prompt(
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
    )
    return prompt_template


# Template for planning kubectl rollout commands
PLAN_ROLLOUT_PROMPT = create_planning_prompt(
    command="rollout",
    description="managing Kubernetes rollouts",
    examples=[
        (
            "status of deployment nginx",
            {
                "action_type": "COMMAND",
                "commands": ["status", "deployment/nginx"],
                "explanation": "Checking the rollout status of the nginx deployment.",
            },
        ),
        (
            "frontend deployment to revision 2",  # Target/rollout action description
            {
                "action_type": "COMMAND",
                "commands": ["undo", "deployment/frontend", "--to-revision=2"],
                "explanation": ("Rolling back the frontend deployment to revision 2."),
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
                "explanation": "Restarting all deployments in the default namespace.",
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
    ],
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


# Template for summarizing 'kubectl create' output
def create_resource_prompt() -> str:
    """Get the prompt template for summarizing kubectl create output.

    Includes current datetime information for timestamp context.

    Returns:
        str: The create resource prompt template with current formatting instructions
    """
    prompt_template = create_summary_prompt(
        description="Summarize resource creation results.",
        focus_points=["resources created", "issues or concerns"],
        example_format=[
            "Created [bold]nginx-pod[/bold] in [blue]default namespace[/blue]",
            "[green]Successfully created[/green] with "
            "[italic]default resource limits[/italic]",
            "[yellow]Note: No liveness probe configured[/yellow]",
        ],
    )
    return prompt_template.format(output="{output}")


# Template for summarizing 'kubectl rollout status' output
def rollout_status_prompt() -> str:
    """Get the prompt template for summarizing kubectl rollout status output.

    Includes current datetime information for timestamp context.

    Returns:
        str: The rollout status prompt template with formatting instructions
    """
    prompt_template = create_summary_prompt(
        description="Summarize rollout status.",
        focus_points=["progress", "completion status", "issues or delays"],
        example_format=[
            "[bold]deployment/frontend[/bold] rollout "
            "[green]successfully completed[/green]",
            "[yellow]Still waiting for 2/5 replicas[/yellow]",
            "[italic]Rollout started 5 minutes ago[/italic]",
        ],
    )
    return prompt_template.format(output="{output}")


# Template for summarizing 'kubectl rollout history' output
def rollout_history_prompt() -> str:
    """Get the prompt template for summarizing kubectl rollout history output.

    Includes current datetime information for timestamp context.

    Returns:
        str: The rollout history prompt template with formatting instructions
    """
    prompt_template = create_summary_prompt(
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
    )
    return prompt_template.format(output="{output}")


# Template for summarizing other rollout command outputs
def rollout_general_prompt() -> str:
    """Get the prompt template for summarizing kubectl rollout output.

    Returns:
        str: The rollout general prompt template with current formatting instructions
    """
    prompt_template = create_summary_prompt(
        description="Summarize rollout command results.",
        focus_points=["key operation details"],
        example_format=[
            "[bold]Deployment rollout[/bold] [green]successful[/green]",
            "[blue]Updates applied[/blue] to [bold]my-deployment[/bold]",
            "[yellow]Warning: rollout took longer than expected[/yellow]",
        ],
    )
    return prompt_template.format(output="{output}")


def create_memory_prompt(
    prompt_type: str,
    instructions: list[str],
    max_chars: int = 500,
) -> str:
    """Create a standard memory-related prompt with consistent formatting.

    Args:
        prompt_type: The type of memory prompt (update, fuzzy_update)
        instructions: Special instructions for this memory prompt type
        max_chars: Maximum characters for memory

    Returns:
        str: Base template for memory-related prompts
    """
    formatted_instructions = "\n".join(
        [f"- {instruction}" for instruction in instructions]
    )

    return f"""You are an AI assistant maintaining a memory state for a
Kubernetes CLI tool.
The memory contains essential context to help you better assist with future requests.

Current memory:
{{current_memory}}

{prompt_type}

Based on this new information, update the memory to maintain the most relevant context.
Focus on cluster state, conditions, and configurations that will help with
future requests.
Be concise - memory is limited to {max_chars} characters.

IMPORTANT:
{formatted_instructions}

IMPORTANT: Do NOT include any prefixes like "Updated memory:" or headings in
your response.
Just provide the direct memory content itself with no additional labels or headers."""


# Update the recovery_prompt function to use the helper function
def recovery_prompt(command: str, error: str, max_chars: int = 1500) -> str:
    """Get the prompt template for generating recovery suggestions when a command fails.

    Args:
        command: The kubectl command that failed
        error: The error message
        max_chars: Maximum characters for the response

    Returns:
        str: The recovery prompt template
    """
    return f"""
The following kubectl command failed with an error:
```
{command}
```

Error:
```
{error}
```

- Explain the error in simple terms and provide 2-3 alternative approaches to
fix the issue.
- Focus on common syntax issues or kubectl command structure problems
- Keep your response under {max_chars} characters.
"""


# Update the memory_update_prompt function to use the helper function
def memory_update_prompt(
    command: str,
    command_output: str,
    vibe_output: str,
    config: Config | None = None,
) -> str:
    """Get the prompt template for updating memory.

    Args:
        command: The command that was executed
        command_output: The raw output from the command
        vibe_output: The AI's interpretation of the command output
        config: Optional Config instance to use. If not provided, creates a new one.

    Returns:
        str: The memory update prompt with current memory and size limit information
    """
    # Import here to avoid circular dependency
    from .memory import get_memory

    cfg = config or Config()
    current_memory = get_memory(cfg)
    max_chars = cfg.get("memory_max_chars", 500)

    # Define the special type-specific content
    command_section = f"""The user just ran this command:
```
{command}
```

Command output:
```
{command_output}
```

Your interpretation of the output:
```
{vibe_output}
```"""

    # Special instructions for this memory prompt type
    instructions = [
        'If the command output was empty or indicates "No resources found", '
        "this is still crucial information. Update the memory to include the fact that "
        "the specified resources don't exist in the queried context or namespace.",
        'If the command output contains an error (starts with "Error:"), this is '
        "extremely important information. Always incorporate the exact error "
        "into memory to prevent repeating failed commands and to help guide "
        "future operations.",
    ]

    # Get the base template
    base_template = create_memory_prompt("update", instructions, max_chars)

    # Insert the current memory and command-specific content
    return base_template.format(current_memory=current_memory).replace(
        "update", command_section
    )


# Update the memory_fuzzy_update_prompt function to include the expected text
def memory_fuzzy_update_prompt(
    current_memory: str,
    update_text: str,
    config: Config | None = None,
) -> str:
    """Get the prompt template for user-initiated memory updates.

    Args:
        current_memory: The current memory content
        update_text: The text the user wants to update or add to memory
        config: Optional Config instance to use. If not provided, creates a new one.

    Returns:
        str: Prompt for user-initiated memory updates with size limit information
    """
    cfg = config or Config()
    max_chars = cfg.get("memory_max_chars", 500)

    # Define the special type-specific content
    fuzzy_section = f"""The user wants to update the memory with this new information:
```
{update_text}
```

Based on this new information, update the memory to integrate this information while
preserving other important existing context."""

    # Special instructions for this memory prompt type
    instructions = [
        "Integrate the new information seamlessly with existing memory",
        "Prioritize recent information when space is limited",
        "Remove outdated or less important information if needed",
        'Do NOT include any prefixes like "Updated memory:" or headings in '
        "your response",
        "Just provide the direct memory content itself with no additional labels "
        "or headers",
    ]

    # Get the base template
    base_template = create_memory_prompt("fuzzy_update", instructions, max_chars)

    # Insert current memory and fuzzy-specific content with explicit text to match tests
    return base_template.format(current_memory=current_memory).replace(
        "fuzzy_update", fuzzy_section
    )


# Template for planning autonomous vibe commands
PLAN_VIBE_PROMPT = """You are an AI assistant delegated to work in a Kubernetes cluster.

The user's goal is expressed in the inputs--the current memory context and a
request--either of which may be empty.

Plan a single next kubectl command to execute which will:
- reduce uncertainty about the user's goal and its status, or if no uncertainty remains:
- advance the user's goal, or if that is impossible:
- reduce uncertainty about how to advance the user's goal, or if that is impossible:
- reduce uncertainty about the current state of the cluster

You may be in a non-interactive context, so do NOT plan blocking commands like
'kubectl wait' or 'kubectl port-forward' unless given an explicit request to the
contrary, and even then use appropriate timeouts.

Syntax requirements (follow these STRICTLY):
- If the request is invalid, impossible, or incoherent, output 'ERROR: <reason>'
- If the planned command is disruptive to the cluster or contrary to the user's
  overall intent, output 'ERROR: not executing <command> because <reason>'
- Otherwise, output ONLY the command arguments
  * Do not include a leading 'kubectl' in the output
  * Do not include any other text in the output
- For creating resources with complex data (HTML, strings with spaces, etc.):
  * PREFER using YAML manifests with 'create -f -' approach
  * If command-line flags like --from-literal must be used, ensure correct quoting
  * For multiple resources, separate each YAML document with '---' on its own
    line with NO INDENTATION

# BEGIN Example inputs and outputs:

Memory: "We are working in namespace 'app'. We have deployed 'frontend' and
'backend' services."
Request: "check if everything is healthy"
Output:
get pods -n app

Memory: "We need to debug why the database pod keeps crashing."
Request: "help me troubleshoot"
Output:
describe pod -l app=database

Memory: "We need to debug why the database pod keeps crashing."
Request: ""
Output:
describe pod -l app=database

Memory: ""
Request: "help me troubleshoot the database pod"
Output:
describe pod -l app=database

Memory: "Wait until pod 'foo' is deleted"
Request: ""
Output:
ERROR: not executing kubectl wait --for=delete pod/foo because it is blocking

Memory: "We need to create multiple resources for our application."
Request: "create the frontend and backend pods"
Output:
create -f - << EOF
---
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
    - containerPort: 6379
EOF

# END Example inputs and outputs

Recall the syntax requirements above and follow them strictly in responding to
the user's goal:

Memory: "__MEMORY_CONTEXT_PLACEHOLDER__"
Request: "__REQUEST_PLACEHOLDER__"
Output:
"""


# Template for summarizing vibe autonomous command output
def vibe_autonomous_prompt() -> str:
    """Get the prompt for generating autonomous kubectl commands based on
    natural language.

    Returns:
        str: The autonomous command generation prompt
    """
    return f"""Analyze this kubectl command output and provide a concise summary.
Focus on the state of the resources, issues detected, and suggest logical next steps.

If the output indicates "Command returned no output" or "No resources found",
this is still valuable information! It means the requested resources don't exist
in the specified namespace or context. Include this fact and suggest appropriate
next steps (checking namespace, creating resources, etc.).

For resources with complex data:
- Suggest YAML manifest approaches over inline flags
- For ConfigMaps, Secrets with complex content, recommend kubectl create/apply -f
- Avoid suggesting command line arguments with quoted content

{get_formatting_instructions()}

Example format:
[bold]3 pods[/bold] running in [blue]app namespace[/blue]
[green]All deployments healthy[/green] with proper replica counts
[yellow]Note: database pod has high CPU usage[/yellow]
Next steps: Consider checking logs for database pod or scaling the deployment

For empty output:
[yellow]No pods found[/yellow] in [blue]sandbox namespace[/blue]
Next steps: Create the first pod or deployment using a YAML manifest

Here's the output:

{{output}}"""


# Template for planning kubectl port-forward commands
PLAN_PORT_FORWARD_PROMPT = create_planning_prompt(
    command="port-forward",
    description=(
        "port-forward connections to kubernetes resources. IMPORTANT: "
        "1) Resource name MUST be the first argument, "
        "2) followed by port specifications, "
        "3) then any flags. Do NOT include 'kubectl' or '--kubeconfig' in "
        "your response."
    ),
    examples=[
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
                    "Forwarding local port 8000 to port 80 of the webserver deployment."
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
    ],
    schema_definition=_SCHEMA_DEFINITION_JSON,
)


# Template for summarizing 'kubectl port-forward' output
def port_forward_prompt() -> str:
    """Get the prompt template for summarizing kubectl port-forward output with
    current datetime.

    Returns:
        str: The port-forward prompt template with current formatting instructions
    """
    prompt_template = create_summary_prompt(
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
    )
    return prompt_template
