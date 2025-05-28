"""
Prompt definitions for kubectl create commands.

This module contains prompt templates and functions specific to the 'kubectl create'
command for creating Kubernetes resources using YAML manifests.
"""

from vibectl.config import Config
from vibectl.schema import ActionType
from vibectl.types import Examples, PromptFragments

from .schemas import _SCHEMA_DEFINITION_JSON
from .shared import (
    create_planning_prompt,
    create_summary_prompt,
    with_planning_prompt_override,
    with_summary_prompt_override,
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
                    "explanation": ("Creating an nginx pod as requested by the user."),
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
                    "explanation": ("Creating requested configmap with HTML content."),
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
                    "explanation": ("Creating frontend and backend pods as requested."),
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


@with_planning_prompt_override("create_plan")
def create_plan_prompt(
    config: Config | None = None,
    current_memory: str | None = None,
) -> PromptFragments:
    """Get prompt fragments for planning kubectl create commands.

    Args:
        config: Optional Config instance.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and user fragments
    """
    # Fall back to default prompt (decorator handles plugin override)
    return create_planning_prompt(
        command="create",
        description="creating Kubernetes resources using YAML manifests",
        examples=Examples(
            [
                (
                    "an nginx hello world pod in default",  # Implicit creation request
                    {
                        "action_type": ActionType.COMMAND.value,
                        "commands": ["-f", "-", "-n", "default"],
                        "explanation": (
                            "Creating an nginx pod as requested by the user."
                        ),
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
                        "explanation": (
                            "Creating requested configmap with HTML content."
                        ),
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
                        "explanation": (
                            "Creating frontend and backend pods as requested."
                        ),
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


@with_summary_prompt_override("create_resource_summary")
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
