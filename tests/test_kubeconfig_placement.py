"""Test kubeconfig placement in kubectl commands.

Specifically tests that --kubeconfig is placed correctly and doesn't interfere
with commands that have trailing arguments after '--' separators.
"""

from unittest.mock import Mock, patch

from vibectl.k8s_utils import run_kubectl, run_kubectl_with_yaml
from vibectl.types import Success


class TestKubeconfigPlacement:
    """Test that kubeconfig arguments are placed correctly in kubectl commands."""

    @patch("vibectl.k8s_utils.subprocess.run")
    @patch("vibectl.k8s_utils.Config")
    def test_kubeconfig_placement_with_double_dash_command(
        self, mock_config_class: Mock, mock_run: Mock
    ) -> None:
        """Test that kubeconfig doesn't interfere with commands using '--' separator."""
        # Setup
        mock_config_instance = mock_config_class.return_value
        mock_config_instance.get.return_value = "/path/to/kubeconfig"

        mock_run.return_value = Mock(returncode=0, stdout="success", stderr="")

        # This is the type of command that was failing before the fix
        cmd_args = [
            "exec",
            "deployment/nginx-demo",
            "-n",
            "sandbox",
            "--",
            "curl",
            "-s",
            "http://localhost/api/random-joke",
        ]

        # Execute
        result = run_kubectl(cmd_args, config=mock_config_instance)

        # Verify result
        assert isinstance(result, Success)

        # Verify the command was called with correct argument order
        mock_run.assert_called_once()
        called_cmd = mock_run.call_args[0][0]

        # The kubeconfig should come right after kubectl, before any other args
        assert called_cmd[0] == "kubectl"
        assert called_cmd[1] == "--kubeconfig"
        assert called_cmd[2] == "/path/to/kubeconfig"

        # The rest should be the original command args
        assert called_cmd[3:] == cmd_args

        # Specifically verify that kubeconfig is NOT after the '--'
        double_dash_index = called_cmd.index("--")
        kubeconfig_index = called_cmd.index("--kubeconfig")
        assert kubeconfig_index < double_dash_index, (
            "kubeconfig should come before '--' separator"
        )

    @patch("vibectl.k8s_utils.subprocess.Popen")
    @patch("vibectl.k8s_utils.Config")
    def test_kubeconfig_placement_in_yaml_command_with_double_dash(
        self, mock_config_class: Mock, mock_popen: Mock
    ) -> None:
        """Test that run_kubectl_with_yaml also places kubeconfig correctly."""
        # Setup
        mock_config_instance = mock_config_class.return_value
        mock_config_instance.get.return_value = "/path/to/kubeconfig"
        mock_config_instance.get_typed.return_value = "kubectl"

        mock_process = Mock()
        mock_process.communicate.return_value = (b"success", b"")
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        yaml_content = "apiVersion: v1\nkind: Pod\nmetadata:\n  name: test"
        args = ["apply", "-f", "-"]

        # Execute
        result = run_kubectl_with_yaml(args, yaml_content, config=mock_config_instance)

        # Verify result
        assert isinstance(result, Success)

        # Verify the command was called with correct argument order
        mock_popen.assert_called_once()
        called_cmd = mock_popen.call_args[0][0]

        # The kubeconfig should come right after kubectl, before any other args
        assert called_cmd[0] == "kubectl"
        assert called_cmd[1] == "--kubeconfig"
        assert called_cmd[2] == "/path/to/kubeconfig"
        assert called_cmd[3:] == args

    @patch("vibectl.k8s_utils.subprocess.run")
    @patch("vibectl.k8s_utils.Config")
    def test_command_order_with_various_separators(
        self, mock_config_class: Mock, mock_run: Mock
    ) -> None:
        """Test various command patterns that should not be affected by kubeconfig."""
        mock_config_instance = mock_config_class.return_value
        mock_config_instance.get.return_value = "/test/kubeconfig"

        mock_run.return_value = Mock(returncode=0, stdout="ok", stderr="")

        test_cases = [
            # Standard command
            ["get", "pods", "-n", "default"],
            # Command with exec and double dash
            ["exec", "pod-name", "--", "sh", "-c", "echo hello"],
            # Command with port-forward
            ["port-forward", "svc/my-service", "8080:80"],
            # Command with logs and follow
            ["logs", "-f", "deployment/app", "--", "grep", "ERROR"],
        ]

        for cmd_args in test_cases:
            mock_run.reset_mock()
            result = run_kubectl(cmd_args, config=mock_config_instance)

            assert isinstance(result, Success)

            called_cmd = mock_run.call_args[0][0]

            # Verify structure: kubectl --kubeconfig <path> <original_args>
            assert called_cmd[0] == "kubectl"
            assert called_cmd[1] == "--kubeconfig"
            assert called_cmd[2] == "/test/kubeconfig"
            assert called_cmd[3:] == cmd_args

            # If there's a '--' in the command, kubeconfig must come before it
            if "--" in called_cmd:
                double_dash_index = called_cmd.index("--")
                kubeconfig_index = called_cmd.index("--kubeconfig")
                assert kubeconfig_index < double_dash_index

    @patch("vibectl.k8s_utils.subprocess.run")
    @patch("vibectl.k8s_utils.Config")
    def test_no_kubeconfig_edge_cases(
        self, mock_config_class: Mock, mock_run: Mock
    ) -> None:
        """Test edge cases where kubeconfig is None or empty."""
        mock_config_instance = mock_config_class.return_value
        mock_run.return_value = Mock(returncode=0, stdout="ok", stderr="")

        # Test case 1: kubeconfig is None
        mock_config_instance.get.return_value = None
        result = run_kubectl(["get", "pods"], config=mock_config_instance)

        assert isinstance(result, Success)
        called_cmd = mock_run.call_args[0][0]
        assert called_cmd == ["kubectl", "get", "pods"]  # No kubeconfig args
        assert "--kubeconfig" not in called_cmd

        # Test case 2: kubeconfig is empty string
        mock_run.reset_mock()
        mock_config_instance.get.return_value = ""
        result = run_kubectl(["get", "pods"], config=mock_config_instance)

        assert isinstance(result, Success)
        called_cmd = mock_run.call_args[0][0]
        # Empty string is falsy, so no kubeconfig args should be added
        assert called_cmd == ["kubectl", "get", "pods"]
        assert "--kubeconfig" not in called_cmd

    @patch("vibectl.k8s_utils.subprocess.run")
    @patch("vibectl.k8s_utils.Config")
    def test_kubeconfig_with_special_characters(
        self, mock_config_class: Mock, mock_run: Mock
    ) -> None:
        """Test kubeconfig paths with special characters are handled correctly."""
        mock_config_instance = mock_config_class.return_value
        mock_run.return_value = Mock(returncode=0, stdout="ok", stderr="")

        # Test with path containing spaces and special characters
        special_path = "/path with spaces/kube-config.yaml"
        mock_config_instance.get.return_value = special_path

        result = run_kubectl(
            ["get", "pods", "--", "echo", "test"], config=mock_config_instance
        )

        assert isinstance(result, Success)
        called_cmd = mock_run.call_args[0][0]

        # Verify the special path is properly included
        assert called_cmd[0] == "kubectl"
        assert called_cmd[1] == "--kubeconfig"
        assert called_cmd[2] == special_path
        assert called_cmd[3:] == ["get", "pods", "--", "echo", "test"]

        # Kubeconfig should still come before '--'
        double_dash_index = called_cmd.index("--")
        kubeconfig_index = called_cmd.index("--kubeconfig")
        assert kubeconfig_index < double_dash_index

    @patch("vibectl.k8s_utils.subprocess.Popen")
    @patch("vibectl.k8s_utils.Config")
    def test_yaml_command_no_kubeconfig(
        self, mock_config_class: Mock, mock_popen: Mock
    ) -> None:
        """Test run_kubectl_with_yaml when no kubeconfig is set."""
        mock_config_instance = mock_config_class.return_value
        mock_config_instance.get.return_value = None  # No kubeconfig
        mock_config_instance.get_typed.return_value = "kubectl"

        mock_process = Mock()
        mock_process.communicate.return_value = (b"success", b"")
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        yaml_content = "apiVersion: v1\nkind: Pod\nmetadata:\n  name: test"
        args = ["apply", "-f", "-"]

        result = run_kubectl_with_yaml(args, yaml_content, config=mock_config_instance)

        assert isinstance(result, Success)
        called_cmd = mock_popen.call_args[0][0]

        # Should be just kubectl + args, no kubeconfig
        assert called_cmd == ["kubectl", "apply", "-f", "-"]
        assert "--kubeconfig" not in called_cmd
