"""Common test fixtures for vibectl tests.

This module contains reusable fixtures to reduce duplication across test files.
"""

from collections.abc import Callable, Generator
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from vibectl.types import Error, Success


@pytest.fixture
def mock_run_kubectl() -> Generator[Mock, None, None]:
    """Mock the run_kubectl function to prevent actual kubectl calls.

    Returns:
        Mock: Mocked run_kubectl function that returns a Success object by default.
    """
    with patch("vibectl.command_handler.run_kubectl") as mock:
        # Default to successful output
        mock.return_value = Success(data="test output")

        # Helper for setting up error responses when needed in tests
        def set_error_response(stderr: str = "test error") -> None:
            """Configure mock to return an Error response."""
            error_msg = stderr if stderr else "Command failed"
            mock.return_value = Error(error=error_msg)

        # Add the helper method to the mock
        mock.set_error_response = set_error_response

        yield mock


@pytest.fixture
def mock_handle_command_output() -> Generator[Mock, None, None]:
    """Mock the handle_command_output function to prevent actual output processing.

    Returns:
        Mock: Mocked handle_command_output function.
    """
    with patch("vibectl.command_handler.handle_command_output") as mock:
        yield mock


@pytest.fixture
def mock_handle_vibe_request() -> Generator[Mock, None, None]:
    """Mock the handle_vibe_request function to prevent actual LLM calls.

    Returns:
        Mock: Mocked handle_vibe_request function.
    """
    with patch("vibectl.command_handler.handle_vibe_request") as mock:
        yield mock


@pytest.fixture
def mock_summary_prompt() -> Callable[..., str]:
    """Mock summary prompt function that ignores extra parameters."""

    def _prompt(*_args: Any, **_kwargs: Any) -> str:
        return "Summarize this: {output}"

    return _prompt


@pytest.fixture
def prevent_exit() -> Generator[MagicMock, None, None]:
    """Prevent sys.exit from exiting the tests.

    This fixture is useful for testing error cases where sys.exit would normally
    terminate the test.
    """
    with patch("sys.exit") as mock_exit:
        yield mock_exit


@pytest.fixture
def mock_kubectl_output() -> str:
    """Provide sample kubectl output for tests."""
    return """
NAME                    READY   STATUS    RESTARTS   AGE
test-pod-1              1/1     Running   0          24h
test-pod-2              0/1     Error     5          12h
"""


@pytest.fixture
def mock_yaml_output() -> str:
    """Provide sample YAML output for tests."""
    return """
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
  namespace: default
spec:
  containers:
  - name: nginx
    image: nginx:latest
status:
  phase: Running
  conditions:
  - type: Ready
    status: "True"
"""


@pytest.fixture
def mock_json_output() -> str:
    """Provide sample JSON output for tests."""
    return """
{
  "apiVersion": "v1",
  "kind": "Pod",
  "metadata": {
    "name": "test-pod",
    "namespace": "default"
  },
  "spec": {
    "containers": [
      {
        "name": "nginx",
        "image": "nginx:latest"
      }
    ]
  },
  "status": {
    "phase": "Running",
    "conditions": [
      {
        "type": "Ready",
        "status": "True"
      }
    ]
  }
}
"""


@pytest.fixture
def sample_kubernetes_resources() -> dict:
    """Provide sample Kubernetes resource data for tests.

    Returns:
        dict: Sample resource data including pods, deployments, and services.
    """
    return {
        "pods": [
            {
                "metadata": {
                    "name": "test-pod-1",
                    "namespace": "default",
                    "uid": "123",
                },
                "status": {
                    "phase": "Running",
                    "containerStatuses": [
                        {
                            "name": "main",
                            "ready": True,
                            "restartCount": 0,
                        }
                    ],
                },
                "spec": {
                    "containers": [
                        {
                            "name": "main",
                            "image": "nginx:1.14.2",
                        }
                    ],
                },
            },
            {
                "metadata": {
                    "name": "test-pod-2",
                    "namespace": "default",
                    "uid": "456",
                },
                "status": {
                    "phase": "Failed",
                    "containerStatuses": [
                        {
                            "name": "main",
                            "ready": False,
                            "restartCount": 5,
                        }
                    ],
                },
                "spec": {
                    "containers": [
                        {
                            "name": "main",
                            "image": "postgres:13",
                        }
                    ],
                },
            },
        ],
        "deployments": [
            {
                "metadata": {
                    "name": "test-deployment-1",
                    "namespace": "default",
                    "uid": "789",
                },
                "spec": {
                    "replicas": 3,
                    "selector": {
                        "matchLabels": {
                            "app": "test",
                        }
                    },
                    "template": {
                        "metadata": {
                            "labels": {
                                "app": "test",
                            }
                        },
                        "spec": {
                            "containers": [
                                {
                                    "name": "main",
                                    "image": "nginx:1.14.2",
                                }
                            ],
                        },
                    },
                },
                "status": {
                    "availableReplicas": 3,
                    "readyReplicas": 3,
                    "replicas": 3,
                },
            }
        ],
        "services": [
            {
                "metadata": {
                    "name": "test-service-1",
                    "namespace": "default",
                    "uid": "abc",
                },
                "spec": {
                    "selector": {
                        "app": "test",
                    },
                    "ports": [
                        {
                            "port": 80,
                            "targetPort": 8080,
                            "protocol": "TCP",
                        }
                    ],
                    "type": "ClusterIP",
                },
                "status": {
                    "loadBalancer": {},
                },
            }
        ],
    }
