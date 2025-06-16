"""
Tests for CA-related coverage gaps in vibectl.server.main module.

This module focuses on Certificate Authority functionality that's missing coverage,
particularly around CA initialization, certificate creation, and status checking.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from click.testing import CliRunner

from vibectl.server.ca_manager import CAManagerError
from vibectl.server.main import (
    _check_certificate_expiry,
    _check_certificate_status,
    _create_server_certificate,
    _initialize_ca,
    _show_ca_status,
    cli,
)
from vibectl.types import Error


class TestCAInitialization:
    """Test CA initialization functionality coverage gaps."""

    def test_initialize_ca_country_code_validation(self) -> None:
        """Test _initialize_ca with invalid country code."""
        result = _initialize_ca(
            ca_dir="/test/ca",
            root_cn="Test Root CA",
            intermediate_cn="Test Intermediate CA",
            organization="Test Org",
            country="USA",  # Invalid - must be 2 chars
            force=False,
        )

        assert isinstance(result, Error)
        assert "Country code must be exactly 2 characters" in result.error

    def test_initialize_ca_directory_exists_no_force(self) -> None:
        """Test _initialize_ca when CA directory exists without force."""
        with tempfile.TemporaryDirectory() as temp_dir:
            ca_dir = Path(temp_dir) / "existing_ca"
            ca_dir.mkdir()  # Create the directory to simulate existing CA

            result = _initialize_ca(
                ca_dir=str(ca_dir),
                root_cn="Test Root CA",
                intermediate_cn="Test Intermediate CA",
                organization="Test Org",
                country="US",
                force=False,
            )

            assert isinstance(result, Error)
            assert result.error is not None
            assert f"CA directory already exists: {ca_dir}" in result.error
            assert result.recovery_suggestions is not None
            assert "Use --force to overwrite existing CA" in result.recovery_suggestions

    @patch("vibectl.server.main.setup_private_ca")
    def test_initialize_ca_ca_manager_error(self, mock_setup_ca: Mock) -> None:
        """Test _initialize_ca with CAManagerError."""
        mock_setup_ca.side_effect = CAManagerError("CA setup failed")

        result = _initialize_ca(
            ca_dir="/test/ca",
            root_cn="Test Root CA",
            intermediate_cn="Test Intermediate CA",
            organization="Test Org",
            country="US",
            force=True,
        )

        assert isinstance(result, Error)
        assert result.error is not None
        assert "CA initialization failed: CA setup failed" in result.error
        assert result.exception is not None

    @patch("vibectl.server.main.setup_private_ca")
    def test_initialize_ca_unexpected_error(self, mock_setup_ca: Mock) -> None:
        """Test _initialize_ca with unexpected exception."""
        mock_setup_ca.side_effect = RuntimeError("Unexpected error")

        result = _initialize_ca(
            ca_dir="/test/ca",
            root_cn="Test Root CA",
            intermediate_cn="Test Intermediate CA",
            organization="Test Org",
            country="US",
            force=True,
        )

        assert isinstance(result, Error)
        assert result.error is not None
        assert (
            "Unexpected error during CA initialization: Unexpected error"
            in result.error
        )
        assert result.exception is not None


class TestServerCertificateCreation:
    """Test server certificate creation coverage gaps."""

    def test_create_server_certificate_ca_directory_not_found(self) -> None:
        """Test _create_server_certificate with non-existent CA directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            non_existent_ca = Path(temp_dir) / "non_existent_ca"

            result = _create_server_certificate(
                hostname="test.example.com",
                ca_dir=str(non_existent_ca),
                san=(),
                validity_days=90,
                force=False,
            )

            assert isinstance(result, Error)
            assert result.error is not None
            assert f"CA directory not found: {non_existent_ca}" in result.error
            assert result.recovery_suggestions is not None
            assert (
                "Initialize CA first with: vibectl-server ca init"
                in result.recovery_suggestions
            )

    def test_create_server_certificate_invalid_validity_days(self) -> None:
        """Test _create_server_certificate with invalid validity days."""
        with tempfile.TemporaryDirectory() as temp_dir:
            result = _create_server_certificate(
                hostname="test.example.com",
                ca_dir=temp_dir,
                san=(),
                validity_days=0,  # Invalid
                force=False,
            )

            assert isinstance(result, Error)
            assert "Validity days must be greater than 0" in result.error

    def test_create_server_certificate_ca_manager_init_error(self) -> None:
        """Test _create_server_certificate with CA manager initialization error."""
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch("vibectl.server.main.CAManager") as mock_ca_manager_class,
        ):
            mock_ca_manager_class.side_effect = CAManagerError("Invalid CA structure")

            result = _create_server_certificate(
                hostname="test.example.com",
                ca_dir=temp_dir,
                san=(),
                validity_days=90,
                force=False,
            )

            assert isinstance(result, Error)
            assert "Certificate creation failed: Invalid CA structure" in result.error

    @patch("vibectl.server.main.CAManager")
    def test_create_server_certificate_unexpected_error(
        self, mock_ca_manager_class: Mock
    ) -> None:
        """Test _create_server_certificate with unexpected exception."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mock_ca_manager_class.side_effect = RuntimeError("Unexpected error")

            result = _create_server_certificate(
                hostname="test.example.com",
                ca_dir=temp_dir,
                san=(),
                validity_days=90,
                force=False,
            )

            assert isinstance(result, Error)
            assert result.error is not None
            assert (
                "Unexpected error during certificate creation: Unexpected error"
                in result.error
            )

    @patch("vibectl.server.main.CAManager")
    def test_create_server_certificate_already_exists_no_force(
        self, mock_ca_manager_class: Mock
    ) -> None:
        """Test _create_server_certificate when certificate exists without force."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create the expected certificate paths
            server_certs_dir = Path(temp_dir) / "server_certs" / "test.example.com"
            server_certs_dir.mkdir(parents=True)
            cert_file = server_certs_dir / "test.example.com.crt"
            cert_file.touch()  # Create the file to simulate existing cert

            result = _create_server_certificate(
                hostname="test.example.com",
                ca_dir=temp_dir,
                san=(),
                validity_days=90,
                force=False,
            )

            assert isinstance(result, Error)
            assert result.error is not None
            assert "Certificate for test.example.com already exists" in result.error
            assert result.recovery_suggestions is not None
            assert (
                "Use --force to overwrite existing certificate"
                in result.recovery_suggestions
            )


class TestCAStatusChecking:
    """Test CA status checking coverage gaps."""

    def test_show_ca_status_ca_directory_not_found(self) -> None:
        """Test _show_ca_status with non-existent CA directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            non_existent_ca = Path(temp_dir) / "non_existent_ca"

            result = _show_ca_status(str(non_existent_ca), 30)

            assert isinstance(result, Error)
            assert result.error is not None
            assert f"CA directory not found: {non_existent_ca}" in result.error
            assert result.recovery_suggestions is not None
            assert (
                "Initialize CA first with: vibectl-server ca init"
                in result.recovery_suggestions
            )

    def test_show_ca_status_ca_manager_init_error(self) -> None:
        """Test _show_ca_status with CA manager initialization error."""
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch("vibectl.server.main.CAManager") as mock_ca_manager_class,
        ):
            mock_ca_manager_class.side_effect = CAManagerError("Invalid CA structure")

            result = _show_ca_status(temp_dir, 30)

            assert isinstance(result, Error)
            assert (
                "CA manager initialization failed: Invalid CA structure" in result.error
            )

    def test_show_ca_status_unexpected_error(self) -> None:
        """Test _show_ca_status with unexpected exception."""
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch("vibectl.server.main.CAManager") as mock_ca_manager_class,
        ):
            mock_ca_manager_class.side_effect = RuntimeError("Unexpected error")

            result = _show_ca_status(temp_dir, 30)

            assert isinstance(result, Error)
            assert (
                "Unexpected error initializing CA manager: Unexpected error"
                in result.error
            )

    def test_check_certificate_expiry_ca_directory_not_found(self) -> None:
        """Test _check_certificate_expiry with non-existent CA directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            non_existent_ca = Path(temp_dir) / "non_existent_ca"

            result = _check_certificate_expiry(str(non_existent_ca), 30)

            assert isinstance(result, Error)
            assert result.error is not None
            assert f"CA directory not found: {non_existent_ca}" in result.error
            assert result.recovery_suggestions is not None
            assert (
                "Initialize CA first with: vibectl-server ca init"
                in result.recovery_suggestions
            )

    def test_check_certificate_expiry_ca_manager_init_error(self) -> None:
        """Test _check_certificate_expiry with CA manager initialization error."""
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch("vibectl.server.main.CAManager") as mock_ca_manager_class,
        ):
            mock_ca_manager_class.side_effect = CAManagerError("Invalid CA structure")

            result = _check_certificate_expiry(temp_dir, 30)

            assert isinstance(result, Error)
            assert (
                "CA manager initialization failed: Invalid CA structure" in result.error
            )

    def test_check_certificate_expiry_unexpected_error(self) -> None:
        """Test _check_certificate_expiry with unexpected exception."""
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch("vibectl.server.main.CAManager") as mock_ca_manager_class,
        ):
            mock_ca_manager_class.side_effect = RuntimeError("Unexpected error")

            result = _check_certificate_expiry(temp_dir, 30)

            assert isinstance(result, Error)
            assert (
                "Unexpected error initializing CA manager: Unexpected error"
                in result.error
            )


class TestCertificateStatusHelper:
    """Test _check_certificate_status helper function coverage gaps."""

    @patch("vibectl.server.main.CAManager")
    def test_check_certificate_status_missing_file(
        self, mock_ca_manager_class: Mock
    ) -> None:
        """Test _check_certificate_status with missing certificate file."""
        mock_ca_manager = Mock()
        mock_ca_manager_class.return_value = mock_ca_manager

        from rich.table import Table

        status_table = Table()
        status_table.add_column("Certificate")
        status_table.add_column("Type")
        status_table.add_column("Status")
        status_table.add_column("Days Until Expiry")

        # Mock a non-existent certificate path
        cert_path = Path("/non/existent/cert.pem")

        warnings_found = _check_certificate_status(
            cert_path, "Test Cert", mock_ca_manager, 30, status_table
        )

        assert warnings_found is True  # Missing file should trigger warning

    @patch("vibectl.server.main.CAManager")
    def test_check_certificate_status_certificate_info_error(
        self, mock_ca_manager_class: Mock
    ) -> None:
        """Test _check_certificate_status with certificate info retrieval error."""
        mock_ca_manager = Mock()
        mock_ca_manager.get_certificate_info.side_effect = Exception("Cert info error")
        mock_ca_manager_class.return_value = mock_ca_manager

        from rich.table import Table

        status_table = Table()
        status_table.add_column("Certificate")
        status_table.add_column("Type")
        status_table.add_column("Status")
        status_table.add_column("Days Until Expiry")

        with tempfile.NamedTemporaryFile() as cert_file:
            cert_path = Path(cert_file.name)

            warnings_found = _check_certificate_status(
                cert_path, "Test Cert", mock_ca_manager, 30, status_table
            )

            assert warnings_found is True  # Error should trigger warning


class TestCACLICommands:
    """Test CA CLI commands error handling paths."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_ca_group_no_subcommand(self) -> None:
        """Test ca group shows help when no subcommand is provided."""
        result = self.runner.invoke(cli, ["ca"])

        assert result.exit_code == 0
        assert "Certificate Authority management commands" in result.output

    @patch("vibectl.server.main._initialize_ca")
    def test_ca_init_command_error(self, mock_initialize_ca: Mock) -> None:
        """Test ca init command with error."""
        mock_initialize_ca.return_value = Error(error="CA initialization failed")

        result = self.runner.invoke(cli, ["ca", "init"])

        assert result.exit_code == 1
        assert "Error: CA initialization failed" in result.output

    @patch("vibectl.server.main._create_server_certificate")
    def test_ca_create_server_cert_command_error(self, mock_create_cert: Mock) -> None:
        """Test ca create-server-cert command with error."""
        mock_create_cert.return_value = Error(error="Certificate creation failed")

        result = self.runner.invoke(
            cli, ["ca", "create-server-cert", "test.example.com"]
        )

        assert result.exit_code == 1
        assert "Error: Certificate creation failed" in result.output

    @patch("vibectl.server.main._show_ca_status")
    def test_ca_status_command_error(self, mock_show_status: Mock) -> None:
        """Test ca status command with error."""
        mock_show_status.return_value = Error(error="Status check failed")

        result = self.runner.invoke(cli, ["ca", "status"])

        assert result.exit_code == 1
        assert "Error: Status check failed" in result.output

    @patch("vibectl.server.main._check_certificate_expiry")
    def test_ca_check_expiry_command_error(self, mock_check_expiry: Mock) -> None:
        """Test ca check-expiry command with error."""
        mock_check_expiry.return_value = Error(error="Expiry check failed")

        result = self.runner.invoke(cli, ["ca", "check-expiry"])

        assert result.exit_code == 1
        assert "Error: Expiry check failed" in result.output
