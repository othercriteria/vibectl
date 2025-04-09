"""Common test fixtures for vibectl tests.

This module contains reusable fixtures to reduce duplication across test files.
"""

from collections.abc import Generator
from unittest.mock import Mock, patch

import pytest


@pytest.fixture
def mock_run_kubectl() -> Generator[Mock, None, None]:
    """Mock the run_kubectl function to prevent actual kubectl calls.

    Returns:
        Mock: Mocked run_kubectl function that returns "test output" by default.
    """
    with patch("vibectl.cli.run_kubectl") as mock:
        # Default to successful output
        mock.return_value = "test output"

        # Helper for setting up error responses when needed in tests
        def set_error_response(stderr: str = "test error") -> None:
            """Configure mock to return an error response."""
            mock.return_value = (
                f"Error: {stderr}" if stderr else "Error: Command failed"
            )

        # Add the helper method to the mock
        mock.set_error_response = set_error_response

        yield mock


@pytest.fixture
def mock_console() -> Generator[Mock, None, None]:
    """Mock the console_manager to prevent terminal output during tests.

    Returns:
        Mock: Mocked console_manager instance.
    """
    with patch("vibectl.cli.console_manager") as mock:
        yield mock


@pytest.fixture
def mock_handle_command_output() -> Generator[Mock, None, None]:
    """Mock the handle_command_output function to prevent actual output processing.

    Returns:
        Mock: Mocked handle_command_output function.
    """
    with patch("vibectl.cli.handle_command_output") as mock:
        yield mock


@pytest.fixture
def mock_handle_vibe_request() -> Generator[Mock, None, None]:
    """Mock the handle_vibe_request function to prevent actual LLM calls.

    Returns:
        Mock: Mocked handle_vibe_request function.
    """
    with patch("vibectl.cli.handle_vibe_request") as mock:
        yield mock


@pytest.fixture
def mock_configure_output_flags() -> Generator[Mock, None, None]:
    """Mock the configure_output_flags function for control over flags.

    Returns:
        Mock: Mocked configure_output_flags function that returns default values.
    """
    with patch("vibectl.cli.configure_output_flags") as mock:
        mock.return_value = (False, True, False, "claude-3.7-sonnet")
        yield mock


@pytest.fixture
def mock_handle_exception() -> Generator[Mock, None, None]:
    """Mock the handle_exception function to prevent sys.exit during tests.

    Returns:
        Mock: Mocked handle_exception function.
    """
    with patch("vibectl.cli.handle_exception") as mock:
        yield mock


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
def cli_test_mocks() -> Generator[tuple[Mock, Mock, Mock], None, None]:
    """Provide common mocks required for CLI tests to prevent unmocked calls."""
    with (
        patch("vibectl.cli.run_kubectl") as mock_run_kubectl,
        patch("vibectl.cli.handle_command_output") as mock_handle_output,
        patch("vibectl.cli.handle_vibe_request") as mock_handle_vibe,
    ):
        # Default to successful output
        mock_run_kubectl.return_value = "test output"

        # Helper for setting up error responses
        def set_error_response(stderr: str = "test error") -> None:
            """Configure mock to return an error response."""
            mock_run_kubectl.return_value = (
                f"Error: {stderr}" if stderr else "Error: Command failed"
            )

        # Add the helper method to the mock
        mock_run_kubectl.set_error_response = set_error_response

        yield mock_run_kubectl, mock_handle_output, mock_handle_vibe


@pytest.fixture
def mock_subprocess_run() -> Generator[Mock, None, None]:
    """Mock subprocess.run to prevent execution of actual commands.

    Returns:
        Mock: Mocked subprocess.run function.
    """
    mock_process = Mock()
    mock_process.stdout = "mocked stdout"
    mock_process.stderr = ""
    mock_process.returncode = 0

    with patch("subprocess.run", return_value=mock_process) as mock_run:
        yield mock_run


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
