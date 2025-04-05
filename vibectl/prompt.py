"""
Prompt templates for LLM interactions with kubectl output.

Each template follows a consistent format using rich.Console() markup for styling,
ensuring clear and visually meaningful summaries of Kubernetes resources.
"""

import datetime


def refresh_datetime() -> str:
    """Refresh and return the current datetime string.

    Returns:
        str: The current datetime in "%Y-%m-%d %H:%M:%S" format
    """
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# Common formatting instructions for all prompts
def get_formatting_instructions() -> str:
    """Get formatting instructions with current datetime.

    Returns:
        str: Formatting instructions with current datetime
    """
    current_time = refresh_datetime()
    return f"""Format your response using rich.Console() markup syntax
with matched closing tags:
- [bold]resource names and key fields[/bold] for emphasis
- [green]healthy states[/green] for positive states
- [yellow]warnings or potential issues[/yellow] for concerning states
- [red]errors or critical issues[/red] for problems
- [blue]namespaces and other Kubernetes concepts[/blue] for k8s terms
- [italic]timestamps and metadata[/italic] for timing information

Important:
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
PLAN_LOGS_PROMPT = """Given this natural language request for container logs,
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
{{version_info}}"""
