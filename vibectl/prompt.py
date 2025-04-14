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
PLAN_GET_PROMPT = """Given this natural language request for Kubernetes resources,
determine the appropriate kubectl get command arguments.

Important:
- Return ONLY the list of arguments, one per line
- Do not include 'kubectl' or 'get' in the output
- Include any necessary flags (-n, --selector, etc.)
- Use standard kubectl syntax and conventions
- If the request is unclear, use reasonable defaults
- If the request is invalid or impossible, return 'ERROR: <reason>'

Example inputs and outputs:

Input: "show me pods in kube-system"
Output:
pods
-n
kube-system

Input: "get pods with app=nginx label"
Output:
pods
--selector=app=nginx

Input: "show me all pods in every namespace"
Output:
pods
--all-namespaces

Here's the request:

{request}"""


# Template for summarizing 'kubectl get' output
def get_resource_prompt() -> str:
    """Get the prompt template for summarizing kubectl get output with current datetime.

    Returns:
        str: The get resource prompt template with current formatting instructions
    """
    return f"""Summarize this kubectl output focusing on key information,
notable patterns, and potential issues.

{get_formatting_instructions()}

Example format:
[bold]3 pods[/bold] in [blue]default namespace[/blue], all [green]Running[/green]
[bold]nginx-pod[/bold] [italic]running for 2 days[/italic]
[yellow]Warning: 2 pods have high restart counts[/yellow]

Here's the output:

{{output}}"""


# Template for summarizing 'kubectl describe' output
def describe_resource_prompt() -> str:
    """Get the prompt template for summarizing kubectl describe output.

    Includes current datetime information for timestamp context.

    Returns:
        str: The describe resource prompt template with current formatting instructions
    """
    return f"""Summarize this kubectl describe output.
Focus only on the most important details and any issues that need attention.
Keep the response under 200 words.

{get_formatting_instructions()}

Example format:
[bold]nginx-pod[/bold] in [blue]default[/blue]: [green]Running[/green]
[yellow]Readiness probe failing[/yellow], [italic]last restart 2h ago[/italic]
[red]OOMKilled 3 times in past day[/red]

Here's the output:

{{output}}"""


# Template for summarizing 'kubectl logs' output
def logs_prompt() -> str:
    """Get the prompt template for summarizing kubectl logs output.

    Includes current datetime information for timestamp context.

    Returns:
        str: The logs prompt template with current formatting instructions
    """
    return f"""Analyze these container logs and provide a concise summary.
Focus on key events, patterns, errors, and notable state changes.
If the logs are truncated, mention this in your summary.

{get_formatting_instructions()}

Example format:
[bold]Container startup[/bold] at [italic]2024-03-20 10:15:00[/italic]
[green]Successfully connected[/green] to [blue]database[/blue]
[yellow]Slow query detected[/yellow] [italic]10s ago[/italic]
[red]3 connection timeouts[/red] in past minute

Here's the output:

{{output}}"""


# Template for planning kubectl describe commands
PLAN_DESCRIBE_PROMPT = """Given this natural language request for Kubernetes
resource details, determine the appropriate kubectl describe command arguments.

Important:
- Return ONLY the list of arguments, one per line
- Do not include 'kubectl' or 'describe' in the output
- Include any necessary flags (-n, etc.)
- Use standard kubectl syntax and conventions
- If the request is unclear, use reasonable defaults
- If the request is invalid or impossible, return 'ERROR: <reason>'

Example inputs and outputs:

Input: "tell me about the nginx pod"
Output:
pod
nginx

Input: "describe the deployment in kube-system namespace"
Output:
deployment
-n
kube-system

Input: "show me details of all pods with app=nginx"
Output:
pods
--selector=app=nginx

Here's the request:

{request}"""


# Template for planning kubectl logs commands
PLAN_LOGS_PROMPT = """Given this natural language request for Kubernetes logs,
determine the appropriate kubectl logs command arguments.

Important:
- Return ONLY the list of arguments, one per line
- Do not include 'kubectl' or 'logs' in the output
- Include any necessary flags (-n, -c, --tail, etc.)
- Use standard kubectl syntax and conventions
- If the request is unclear, use reasonable defaults
- If the request is invalid or impossible, return 'ERROR: <reason>'

Example inputs and outputs:

Input: "show me logs from the nginx pod"
Output:
pod/nginx

Input: "get logs from the api container in my-app pod"
Output:
pod/my-app
-c
api

Input: "show me the last 100 lines from all pods with app=nginx"
Output:
--selector=app=nginx
--tail=100

Here's the request:

{request}"""


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

Example inputs and outputs:

Input: "create an nginx hello world pod"
Output:
-n
default
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

Here's the request:

{request}"""


# Template for planning kubectl version commands
PLAN_VERSION_PROMPT = """Given this natural language request for Kubernetes
version information, determine the appropriate kubectl version command arguments.

Important:
- Return ONLY the list of arguments, one per line
- Do not include 'kubectl' or 'version' in the output
- Include any necessary flags (--output, --short, etc.)
- Use standard kubectl syntax and conventions
- If the request is unclear, use reasonable defaults (like --output=json)
- If the request is invalid or impossible, return 'ERROR: <reason>'

Example inputs and outputs:

Input: "show version in json format"
Output:
--output=json

Input: "get client version only"
Output:
--client=true
--output=json

Input: "show version in yaml"
Output:
--output=yaml

Here's the request:

{request}"""


# Template for summarizing 'kubectl create' output
def create_resource_prompt() -> str:
    """Get the prompt template for summarizing kubectl create output.

    Includes current datetime information for timestamp context.

    Returns:
        str: The create resource prompt template with current formatting instructions
    """
    return f"""Summarize the result of creating Kubernetes resources.
Focus on what was created and any issues that need attention.

{get_formatting_instructions()}

Example format:
Created [bold]nginx-pod[/bold] in [blue]default namespace[/blue]
[green]Successfully created[/green] with [italic]default resource limits[/italic]
[yellow]Note: No liveness probe configured[/yellow]

Here's the output:

{{output}}"""


# Template for planning kubectl cluster-info commands
PLAN_CLUSTER_INFO_PROMPT = """Given this natural language request for Kubernetes
cluster information, determine the appropriate kubectl cluster-info command arguments.

Important:
- Return ONLY the list of arguments, one per line
- Do not include 'kubectl' or 'cluster-info' in the output
- Include any necessary flags (--context, etc.)
- Use standard kubectl syntax and conventions
- If the request is unclear, use reasonable defaults
- If the request is invalid or impossible, return 'ERROR: <reason>'

Example inputs and outputs:

Input: "show cluster info"
Output:
dump

Input: "show basic cluster info"
Output:


Input: "show detailed cluster info"
Output:
dump

Here's the request:

{request}"""


# Template for summarizing 'kubectl cluster-info' output
def cluster_info_prompt() -> str:
    """Get the prompt template for summarizing kubectl cluster-info output.

    Includes current datetime information for timestamp context.

    Returns:
        str: The cluster info prompt with current formatting instructions
    """
    return f"""Analyze this Kubernetes cluster-info output and provide a
comprehensive but concise summary.
Focus on cluster version, control plane components, add-ons, and any
notable details or potential issues.

{get_formatting_instructions()}

Example format:
[bold]Kubernetes v1.26.3[/bold] cluster running on [blue]Google Kubernetes Engine[/blue]
[green]Control plane healthy[/green] at [italic]https://10.0.0.1:6443[/italic]
[blue]CoreDNS[/blue] and [blue]KubeDNS[/blue] add-ons active
[yellow]Warning: Dashboard not secured with RBAC[/yellow]

Here's the output:

{{output}}"""


# Template for summarizing 'kubectl version' output
def version_prompt() -> str:
    """Get the prompt template for summarizing kubectl version output.

    Includes current datetime information for timestamp context.

    Returns:
        str: The version prompt template with current formatting instructions
    """
    return f"""Interpret this Kubernetes version information in a human-friendly way.
Highlight important details like version compatibility, deprecation notices,
or update recommendations.

{get_formatting_instructions()}

Example format:
[bold]Kubernetes v1.26.3[/bold] client and [bold]v1.25.4[/bold] server
[green]Compatible versions[/green] with [italic]patch available[/italic]
[blue]Server components[/blue] all [green]up-to-date[/green]
[yellow]Client will be deprecated in 3 months[/yellow]

Here's the version information:
{{output}}"""


# Template for planning kubectl events commands
PLAN_EVENTS_PROMPT = """Given this natural language request for Kubernetes events,
determine the appropriate kubectl get events command arguments.

Important:
- Return ONLY the list of arguments, one per line
- Do not include 'kubectl' or 'get events' in the output
- Include any necessary flags (-n, --field-selector, --sort-by, etc.)
- Use standard kubectl syntax and conventions
- If the request is unclear, use reasonable defaults
- If the request is invalid or impossible, return 'ERROR: <reason>'

Example inputs and outputs:

Input: "show events in default namespace"
Output:
-n
default

Input: "get events for pod nginx"
Output:
--field-selector=involvedObject.name=nginx,involvedObject.kind=Pod

Input: "show all events in all namespaces"
Output:
--all-namespaces

Here's the request:

{request}"""


# Template for summarizing 'kubectl events' output
def events_prompt() -> str:
    """Get the prompt template for summarizing kubectl events output.

    Includes current datetime information for timestamp context.

    Returns:
        str: The events prompt template with current formatting instructions
    """
    return f"""Analyze these Kubernetes events and provide a concise summary.
Focus on recent events, patterns, warnings, and notable occurrences.
Group related events and highlight potential issues.

{get_formatting_instructions()}  # pragma: no cover - tested in other prompt functions

Example format:
[bold]12 events[/bold] in the last [italic]10 minutes[/italic]
[green]Successfully scheduled[/green] pods: [bold]nginx-1[/bold], [bold]nginx-2[/bold]
[yellow]ImagePullBackOff[/yellow] for [bold]api-server[/bold]
[italic]5 minutes ago[/italic]
[red]OOMKilled[/red] events for [bold]db-pod[/bold], [italic]happened 3 times[/italic]

Here's the output:

{{output}}"""


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

    return f"""You are an AI assistant maintaining a memory state for a \
Kubernetes CLI tool.
The memory contains essential context to help you better assist with future requests.

Current memory:
{current_memory}

The user just ran this command:
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
```

Based on this new information, update the memory to maintain the most \
relevant context.
Focus on cluster state, conditions, and configurations that will help with \
future requests.

IMPORTANT:
1. If the command output was empty or indicates "No resources found", \
this is still crucial information. Update the memory to include the fact that \
the specified resources don't exist in the queried context or namespace.

2. If the command output contains an error (starts with "Error:"), this is \
extremely important information. Always incorporate the exact error into memory \
to prevent repeating failed commands and to help guide future operations.

Be concise - memory is limited to {max_chars} characters (about 2-3 short paragraphs).
Only include things actually observed from the output, no speculation or generalization.

IMPORTANT: Do NOT include any prefixes like "Updated memory:" or headings \
in your response. Just provide the direct memory content itself with \
no additional labels or headers."""


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

    return f"""You are an AI assistant maintaining a memory state for a \
Kubernetes CLI tool.
The memory contains essential context to help you better assist with future requests.

Current memory:
{current_memory}

The user wants to update the memory with this new information:
```
{update_text}
```

Based on this new information, update the memory to integrate this information \
while preserving other important existing context.
Focus on cluster state, conditions, and configurations that will help with \
future requests.
Be concise - memory is limited to {max_chars} characters (about 2-3 short paragraphs).

IMPORTANT:
- Integrate the new information seamlessly with existing memory
- Prioritize recent information when space is limited
- Remove outdated or less important information if needed
- Do NOT include any prefixes like "Updated memory:" or headings in your response
- Just provide the direct memory content itself with no additional labels or headers
"""


# Template for planning kubectl delete commands
PLAN_DELETE_PROMPT = """Given this natural language request to delete Kubernetes
resources, determine the appropriate kubectl delete command arguments.

Important:
- Return ONLY the list of arguments, one per line
- Do not include 'kubectl' or 'delete' in the output
- Include any necessary flags (-n, --grace-period, etc.)
- Use standard kubectl syntax and conventions
- If the request is unclear, use reasonable defaults
- If the request is invalid or impossible, return 'ERROR: <reason>'

Example inputs and outputs:

Input: "delete the nginx pod"
Output:
pod
nginx

Input: "remove deployment in kube-system namespace"
Output:
deployment
-n
kube-system

Input: "delete all pods with app=nginx"
Output:
pods
--selector=app=nginx

Here's the request:

{request}"""


# Template for summarizing 'kubectl delete' output
def delete_resource_prompt() -> str:
    """Get the prompt template for summarizing kubectl delete output.

    Returns:
        str: The delete resource prompt template with current formatting instructions
    """
    return f"""Summarize this kubectl delete output focusing on key information,
which resources were deleted, and any potential issues or warnings.

{get_formatting_instructions()}

Example format:
[bold]3 pods[/bold] successfully deleted from [blue]default namespace[/blue]
[yellow]Warning: Some resources are still terminating[/yellow]

Here's the output:

{{output}}"""


# Template for planning kubectl scale commands
PLAN_SCALE_PROMPT = """Given this natural language request for scaling Kubernetes
resources, determine the appropriate kubectl scale command arguments.

Important:
- Return ONLY the list of arguments, one per line
- Do not include 'kubectl' or 'scale' in the output
- Include any necessary flags (--replicas, -n, etc.)
- Use standard kubectl syntax and conventions
- If the request is unclear, use reasonable defaults
- If the request is invalid or impossible, return 'ERROR: <reason>'

Example inputs and outputs:

Input: "scale deployment nginx to 3 replicas"
Output:
deployment/nginx
--replicas=3

Input: "increase the redis statefulset to 5 replicas in the cache namespace"
Output:
statefulset/redis
--replicas=5
-n
cache

Input: "scale down the api deployment"
Output:
deployment/api
--replicas=1

Here's the request:

{request}"""


# Template for summarizing 'kubectl scale' output
def scale_resource_prompt() -> str:
    """Get the prompt template for summarizing kubectl scale output.

    Includes current datetime information for timestamp context.

    Returns:
        str: The scale resource prompt template with formatting instructions
    """
    return f"""Summarize this kubectl scale output focusing on what changed
and the current state after scaling. Highlight any issues or noteworthy details.

{get_formatting_instructions()}

Example format:
[bold]deployment/nginx[/bold] scaled to [green]3 replicas[/green]
[yellow]Warning: Scale operation might take time to complete[/yellow]
[blue]Namespace: default[/blue]

Here's the output:

{{output}}"""


# Template for planning kubectl rollout commands
PLAN_ROLLOUT_PROMPT = """Given this natural language request for managing Kubernetes
rollouts, determine the appropriate kubectl rollout command arguments.

Important:
- Return ONLY the list of arguments, one per line
- Do not include 'kubectl' or 'rollout' in the output
- The first argument should be the subcommand (status, history, undo,
  restart, pause, resume)
- Include any necessary flags (-n, --revision, etc.)
- Use standard kubectl syntax and conventions
- If the request is unclear, use reasonable defaults
- If the request is invalid or impossible, return 'ERROR: <reason>'

Example inputs and outputs:

Input: "check status of deployment nginx"
Output:
status
deployment/nginx

Input: "rollback frontend deployment to revision 2"
Output:
undo
deployment/frontend
--to-revision=2

Input: "pause the rollout of my-app deployment in production namespace"
Output:
pause
deployment/my-app
-n
production

Input: "restart all deployments in default namespace"
Output:
restart
deployment
-l
app

Input: "show history of statefulset/redis"
Output:
history
statefulset/redis

Here's the request:

{request}"""


# Template for summarizing 'kubectl rollout status' output
def rollout_status_prompt() -> str:
    """Get the prompt template for summarizing kubectl rollout status output.

    Includes current datetime information for timestamp context.

    Returns:
        str: The rollout status prompt template with formatting instructions
    """
    return f"""Summarize this kubectl rollout status output, focusing on current
progress, completion status, and any issues or delays.

{get_formatting_instructions()}

Example format:
[bold]deployment/frontend[/bold] rollout [green]successfully completed[/green]
[yellow]Still waiting for 2/5 replicas[/yellow]
[italic]Rollout started 5 minutes ago[/italic]

Here's the output:

{{output}}"""


# Template for summarizing 'kubectl rollout history' output
def rollout_history_prompt() -> str:
    """Get the prompt template for summarizing kubectl rollout history output.

    Includes current datetime information for timestamp context.

    Returns:
        str: The rollout history prompt template with formatting instructions
    """
    return f"""Summarize this kubectl rollout history output, highlighting key
revisions, important changes, and patterns across revisions.

{get_formatting_instructions()}

Example format:
[bold]deployment/app[/bold] has [blue]5 revision history[/blue]
[green]Current active: revision 5[/green] (deployed 2 hours ago)
[yellow]Revision 3 had frequent restarts[/yellow]

Here's the output:

{{output}}"""


# Template for summarizing other rollout command outputs
def rollout_general_prompt() -> str:
    """Get the prompt template for summarizing kubectl rollout output.

    Returns:
        str: The rollout general prompt template with current formatting instructions
    """
    return f"""Summarize this kubectl rollout command output.
Focus on the key information about the rollout operation.

{get_formatting_instructions()}

Example format:
[bold]Deployment rollout[/bold] [green]successful[/green]
[blue]Updates applied[/blue] to [bold]my-deployment[/bold]
[yellow]Warning: rollout took longer than expected[/yellow]

Here's the output:

{{output}}"""


# Template for planning autonomous vibe commands
PLAN_VIBE_PROMPT = """You are an AI assistant managing a Kubernetes cluster.
Based on the current memory context and request, plan the next kubectl command
to execute.

Important:
- Return ONLY the kubectl command to execute, formatted as shown in examples
- Include the full command with 'kubectl' and all necessary arguments
- If more information is needed, use discovery commands
- If the request is unclear but memory has context, use memory to guide your decision
- If no context exists, start with basic discovery commands like 'kubectl cluster-info'
- In the absence of any specific instruction or context, focus on gathering information
  before making changes
- If the command is potentially destructive, add a note about the impact
- If the request is invalid or impossible, return 'ERROR: <reason>'
- If previous commands returned empty results, use that information to intelligently
  progress to the next logical step (e.g., checking other namespaces, trying different
  resource types, or suggesting resource creation)
- After discovering empty namespaces or no pods/resources, progress to create
  needed resources rather than repeatedly checking empty resources

Command Structure Guidelines:
- For creating resources with complex data (HTML, strings with spaces, etc.):
  * PREFER using YAML manifests with 'kubectl create -f <file.yaml>' approach
  * If command-line flags like --from-literal must be used, ensure correct quoting
- Avoid spaces in resource names when possible
- Use YAML format for creation of all non-trivial resources (configmaps, secrets, etc.)
- Each multi-line command should be explicit about line continuation with backslashes

Example inputs and outputs:

Memory: "We are working in namespace 'app'. We have deployed 'frontend' and
'backend' services."
Input: "check if everything is healthy"
Output:
kubectl get pods -n app

Memory: "We need to debug why the database pod keeps crashing."
Input: "help me troubleshoot"
Output:
kubectl describe pod -l app=database

Memory: <empty>
Input: <empty>
Output:
kubectl cluster-info

Memory: "We are working on deploying a three-tier application. We've created a
frontend deployment."
Input: "keep working on the application deployment"
Output:
kubectl get deployment frontend -o yaml
NOTE: Will examine frontend configuration to help determine next steps

Memory: "We're working only in the 'sandbox' namespace to demonstrate new features.
Checked for pods but found none in the sandbox namespace."
Input: "keep building the nginx demo"
Output:
kubectl create -f - << EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx
  namespace: sandbox
spec:
  replicas: 1
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
EOF
NOTE: Creating nginx deployment as first step in building the demo

Memory: "We need to create a configmap with HTML content in the 'web' namespace."
Input: "create the configmap for the nginx website"
Output:
kubectl create -f - << EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: nginx-html
  namespace: web
data:
  index.html: |
    <html><body><h1>Welcome to Nginx</h1><p>This is a demo website.</p></body></html>
EOF
NOTE: Creating configmap with HTML content for the nginx website

Here's the current memory context and request:

{memory_context}

Request: {request}"""


# Template for summarizing vibe autonomous command output
def vibe_autonomous_prompt() -> str:
    """Get the prompt for generating autonomous kubectl commands based on
    natural language.

    Returns:
        str: The autonomous command generation prompt
    """
    return f"""Analyze this kubectl command output and provide a concise summary.
Focus on the state of the resources, any issues detected, and suggest logical
next steps.

If the output indicates "Command returned no output" or "No resources found",
this is still valuable information! It means the requested resources don't exist
in the specified namespace or context. Include this fact in your interpretation
and suggest appropriate next steps (e.g., creating resources, checking namespace,
confirming context, etc.).

When suggesting next steps that involve creating resources with complex data:
- Suggest using YAML manifest approaches rather than inline flags like --from-literal
- For ConfigMaps, Secrets, or other resources with complex content (HTML, multi-line
  text), recommend explicit YAML creation using kubectl create/apply -f
- Avoid suggesting command line arguments with quoted content when possible

{get_formatting_instructions()}

Example format:
[bold]3 pods[/bold] running in [blue]app namespace[/blue]
[green]All deployments healthy[/green] with proper replica counts
[yellow]Note: database pod has high CPU usage[/yellow]
Next steps: Consider checking logs for database pod or scaling the deployment

For empty output examples:
[yellow]No pods found[/yellow] in [blue]sandbox namespace[/blue]
Next steps: Create the first pod or deployment in this namespace using a YAML manifest

Here's the output:

{{output}}"""


def recovery_prompt(command: str, error: str) -> str:
    """Get the prompt template for generating recovery suggestions when a command fails.

    Args:
        command: The kubectl command that failed
        error: The error message

    Returns:
        str: The recovery prompt template
    """
    return f"""
The following kubectl command failed with an error:
kubectl {command}

Error: {error}

Explain the error in simple terms and provide 2-3 alternative approaches to
fix the issue.

Focus on common syntax issues or kubectl command structure problems.

Keep your response under 400 tokens.
"""
