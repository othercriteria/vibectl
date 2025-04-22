"""
Prompt templates for LLM interactions with kubectl output.

Each template follows a consistent format using rich.Console() markup for styling,
ensuring clear and visually meaningful summaries of Kubernetes resources.
"""

import datetime

from .config import Config

# No memory imports at the module level to avoid circular imports


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


def get_command_directives() -> str:
    """Get the standard directives for kubectl command planning prompts.

    Returns:
        str: Formatted directives for command planning
    """
    return """Important:
- Return ONLY the list of arguments, one per line
- Do not include 'kubectl' or '{command}' in the output
- Include any necessary flags ({flags})
- Use standard kubectl syntax and conventions
- If the request is unclear, use reasonable defaults
- If the request is invalid or impossible, return 'ERROR: <reason>'"""


def create_planning_prompt(
    command: str,
    description: str,
    examples: list[tuple[str, str]],
    flags: str = "-n, --selector, etc.",
) -> str:
    """Create a standard planning prompt for kubectl commands.

    Args:
        command: The kubectl command (get, describe, etc.)
        description: Description of what the prompt is for
        examples: List of input/output example tuples
        flags: Common flags for this command

    Returns:
        str: Formatted planning prompt template
    """
    directives = get_command_directives().format(command=command, flags=flags)
    formatted_examples = format_examples(examples)

    return f"""Given this natural language request for {description},
determine the appropriate kubectl {command} command arguments.

{directives}

{formatted_examples}

Here's the request:

{{request}}"""


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
    description="Kubernetes resources",
    examples=[
        ("show me pods in kube-system", "pods\n-n\nkube-system"),
        ("get pods with app=nginx label", "pods\n--selector=app=nginx"),
        ("show me all pods in every namespace", "pods\n--all-namespaces"),
    ],
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
        ("tell me about the nginx pod", "pod\nnginx"),
        (
            "describe the deployment in kube-system namespace",
            "deployment\n-n\nkube-system",
        ),
        ("show me details of all pods with app=nginx", "pods\n--selector=app=nginx"),
    ],
)

# Template for planning kubectl logs commands
PLAN_LOGS_PROMPT = create_planning_prompt(
    command="logs",
    description="Kubernetes logs",
    examples=[
        ("show me logs from the nginx pod", "pod/nginx"),
        ("get logs from the api container in my-app pod", "pod/my-app\n-c\napi"),
        (
            "show me the last 100 lines from all pods with app=nginx",
            "--selector=app=nginx\n--tail=100",
        ),
    ],
)

# Template for planning kubectl create commands
PLAN_CREATE_PROMPT = """Given this natural language request to create Kubernetes
resources, determine the appropriate kubectl create command arguments and YAML manifest.

Important:
- Return the list of arguments (if any) followed by '---' and then the YAML manifest
- Do not include 'kubectl' or 'create' in the output
- Include any necessary flags (-n, etc.)
- Use standard kubectl syntax and conventions
- If the request is unclear, use reasonable defaults
- If the request is invalid or impossible, return 'ERROR: <reason>'
- For commands with complex arguments (e.g., --from-literal with spaces, HTML, or
  special characters):
  * PREFER creating a YAML file with '---' separator instead of inline --from-literal
    arguments
  * If --from-literal must be used, ensure values are properly quoted
- For multiple resources in a single manifest:
  * Separate each document with '---' on a line by itself with NO INDENTATION
  * Every YAML document must start with '---' on a line by itself

Example inputs and outputs:

Input: "create an nginx hello world pod"
Output:
-n
default
---
---
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
    - containerPort: 80

Input: "create a configmap with HTML content"
Output:
-n
default
---
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: html-content
data:
  index.html: |
    <html><body><h1>Hello World</h1></body></html>

Input: "create a deployment with 3 nginx replicas in prod namespace"
Output:
-n
prod
---
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-deployment
  labels:
    app: nginx
spec:
  replicas: 3
  selector:
    matchLabels:
      app: nginx
  template:
    metadata:
      labels:
        app: nginx
    spec:
      containers:
      - name: nginx
        image: nginx:latest
        ports:
        - containerPort: 80

Input: "create frontend and backend pods for my application"
Output:
-n
default
---
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

Here's the request:

{request}"""


# Template for planning kubectl version commands
PLAN_VERSION_PROMPT = create_planning_prompt(
    command="version",
    description="Kubernetes version information",
    examples=[
        ("show version in json format", "--output=json"),
        ("get client version only", "--client=true\n--output=json"),
        ("show version in yaml", "--output=yaml"),
    ],
    flags="--output, --short, etc.",
)

# Template for planning kubectl cluster-info commands
PLAN_CLUSTER_INFO_PROMPT = create_planning_prompt(
    command="cluster-info",
    description="Kubernetes cluster information",
    examples=[
        ("show cluster info", "dump"),
        ("show basic cluster info", ""),
        ("show detailed cluster info", "dump"),
    ],
    flags="--context, etc.",
)

# Template for planning kubectl events commands
PLAN_EVENTS_PROMPT = create_planning_prompt(
    command="get events",
    description="Kubernetes events",
    examples=[
        ("show events in default namespace", "-n\ndefault"),
        (
            "get events for pod nginx",
            "--field-selector=involvedObject.name=nginx,involvedObject.kind=Pod",
        ),
        ("show all events in all namespaces", "--all-namespaces"),
    ],
    flags="-n, --field-selector, --sort-by, etc.",
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
    # Note: keep the pragma comment for test coverage
    formatted = prompt_template.format(output="{output}")
    return formatted + "  # pragma: no cover - tested in other prompt functions"


# Template for planning kubectl delete commands
PLAN_DELETE_PROMPT = create_planning_prompt(
    command="delete",
    description="Kubernetes resources",
    examples=[
        ("delete the nginx pod", "pod\nnginx"),
        ("remove deployment in kube-system namespace", "deployment\n-n\nkube-system"),
        ("delete all pods with app=nginx", "pods\n--selector=app=nginx"),
    ],
    flags="-n, --grace-period, etc.",
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
        ("scale deployment nginx to 3 replicas", "deployment/nginx\n--replicas=3"),
        (
            "increase the redis statefulset to 5 replicas in the cache namespace",
            "statefulset/redis\n--replicas=5\n-n\ncache",
        ),
        ("scale down the api deployment", "deployment/api\n--replicas=1"),
    ],
    flags="--replicas, -n, etc.",
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
            "wait for the deployment my-app to be ready",
            "deployment/my-app\n--for=condition=Available",
        ),
        (
            "wait until the pod nginx becomes ready with 5 minute timeout",
            "pod/nginx\n--for=condition=Ready\n--timeout=5m",
        ),
        (
            "wait for all jobs in billing namespace to complete",
            "jobs\n--all\n-n\nbilling\n--for=condition=Complete",
        ),
    ],
    flags="--for, --timeout, -n, etc.",
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
        ("check status of deployment nginx", "status\ndeployment/nginx"),
        (
            "rollback frontend deployment to revision 2",
            "undo\ndeployment/frontend\n--to-revision=2",
        ),
        (
            "pause the rollout of my-app deployment in production namespace",
            "pause\ndeployment/my-app\n-n\nproduction",
        ),
        (
            "restart all deployments in default namespace",
            "restart\ndeployment\n-l\napp",
        ),
        ("show history of statefulset/redis", "history\nstatefulset/redis"),
    ],
    flags="-n, --revision, etc.",
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

Memory: "{memory_context}"
Request: "{request}"
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
        ("forward port 8080 of pod nginx to my local 8080", "pod/nginx\n8080:8080"),
        (
            "connect to the redis service port 6379 on local port 6380",
            "service/redis\n6380:6379",
        ),
        (
            "forward deployment webserver port 80 to my local 8000",
            "deployment/webserver\n8000:80",
        ),
        (
            "proxy my local 5000 to port 5000 on the api pod in namespace test",
            "pod/api\n5000:5000\n--namespace\ntest",
        ),
        (
            "forward ports with the app running on namespace production",
            "pod/app\n8080:80\n--namespace\nproduction",
        ),
    ],
    flags="--namespace, --address, --pod-running-timeout",
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
