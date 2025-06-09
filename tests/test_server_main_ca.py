"""
Tests for CA-related functionality in vibectl.server.main module.

This module tests CA certificate management, serve-ca command,
and all CA-related CLI commands.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from click.testing import CliRunner

from vibectl.server.ca_manager import CAManagerError
from vibectl.server.config import get_default_server_config
from vibectl.server.main import (
    _check_certificate_expiry,
    _check_certificate_status,
    _create_server_certificate,
    _initialize_ca,
    _show_ca_status,
    cli,
)
from vibectl.types import Error, Success


class TestCAInitialization:
    """Test CA initialization functionality."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("pathlib.Path.exists")
    @patch("vibectl.server.main.setup_private_ca")
    def test_initialize_ca_success(
        self, mock_setup_ca: Mock, mock_exists: Mock
    ) -> None:
        """Test successful CA initialization."""
        # Mock path doesn't exist so CA can be created
        mock_exists.return_value = False

        mock_ca_manager = Mock()
        mock_setup_ca.return_value = mock_ca_manager

        result = _initialize_ca(
            ca_dir="/test/config/ca",
            root_cn="Test Root CA",
            intermediate_cn="Test Intermediate CA",
            organization="Test Org",
            country="US",
            force=False,
        )

        assert isinstance(result, Success)
        assert "CA initialized successfully" in result.message
        mock_setup_ca.assert_called_once_with(
            Path("/test/config/ca"),
            "Test Root CA",
            "Test Intermediate CA",
            "Test Org",
            "US",
        )

    @patch("pathlib.Path.exists")
    @patch("vibectl.server.main.setup_private_ca")
    def test_initialize_ca_with_explicit_dir(
        self, mock_setup_ca: Mock, mock_exists: Mock
    ) -> None:
        """Test CA initialization with explicit directory."""
        # Mock path doesn't exist so CA can be created
        mock_exists.return_value = False

        mock_ca_manager = Mock()
        mock_setup_ca.return_value = mock_ca_manager

        result = _initialize_ca(
            ca_dir="/custom/ca/path",
            root_cn="Custom Root CA",
            intermediate_cn="Custom Intermediate CA",
            organization="Custom Org",
            country="CA",
            force=False,
        )

        assert isinstance(result, Success)
        assert "CA initialized successfully" in result.message
        # Verify setup_private_ca is called with all 5 parameters
        mock_setup_ca.assert_called_once_with(
            Path("/custom/ca/path"),
            "Custom Root CA",
            "Custom Intermediate CA",
            "Custom Org",
            "CA",
        )

    @patch("pathlib.Path.exists")
    def test_initialize_ca_already_exists_no_force(self, mock_exists: Mock) -> None:
        """Test CA initialization when CA already exists without force."""
        # Mock path exists and force is False
        mock_exists.return_value = True

        result = _initialize_ca(
            ca_dir="/test/config/ca",
            root_cn="Test Root CA",
            intermediate_cn="Test Intermediate CA",
            organization="Test Org",
            country="US",
            force=False,
        )

        assert isinstance(result, Error)
        assert "CA directory already exists" in result.error

    @patch("pathlib.Path.exists")
    @patch("vibectl.server.main.setup_private_ca")
    def test_initialize_ca_force_overwrite(
        self, mock_setup_ca: Mock, mock_exists: Mock
    ) -> None:
        """Test CA initialization with force overwrite."""
        # Mock path exists but force is True
        mock_exists.return_value = True

        mock_ca_manager = Mock()
        mock_setup_ca.return_value = mock_ca_manager

        result = _initialize_ca(
            ca_dir="/test/config/ca",
            root_cn="Test Root CA",
            intermediate_cn="Test Intermediate CA",
            organization="Test Org",
            country="US",
            force=True,
        )

        assert isinstance(result, Success)
        assert "CA initialized successfully" in result.message
        mock_setup_ca.assert_called_once_with(
            Path("/test/config/ca"),
            "Test Root CA",
            "Test Intermediate CA",
            "Test Org",
            "US",
        )

    @patch("pathlib.Path.exists")
    @patch("vibectl.server.main.setup_private_ca")
    def test_initialize_ca_setup_failure(
        self, mock_setup_ca: Mock, mock_exists: Mock
    ) -> None:
        """Test CA initialization when setup_private_ca fails."""
        # Mock path doesn't exist so CA can be created
        mock_exists.return_value = False

        mock_setup_ca.side_effect = CAManagerError("Setup failed")

        result = _initialize_ca(
            ca_dir="/test/config/ca",
            root_cn="Test Root CA",
            intermediate_cn="Test Intermediate CA",
            organization="Test Org",
            country="US",
            force=False,
        )

        assert isinstance(result, Error)
        assert "CA initialization failed" in result.error


class TestServerCertificateCreation:
    """Test server certificate creation functionality."""

    @patch("vibectl.server.main.CAManager")
    @patch("vibectl.server.main.Path")
    def test_create_server_certificate_success(
        self, mock_path_class: Mock, mock_ca_manager_class: Mock
    ) -> None:
        """Test successful server certificate creation."""
        mock_ca_manager = Mock()
        mock_ca_manager_class.return_value = mock_ca_manager

        mock_cert_path = Path(
            "/test/config/ca/server_certs/example.com/example.com.crt"
        )
        mock_key_path = Path("/test/config/ca/server_certs/example.com/example.com.key")
        mock_ca_manager.create_server_certificate.return_value = (
            mock_cert_path,
            mock_key_path,
        )

        # Create mock path instances with proper magic method support
        mock_ca_dir_path = Mock()
        mock_ca_dir_path.exists.return_value = True  # CA directory exists

        # Mock server_certs directory structure
        mock_server_certs_dir = Mock()
        mock_server_cert_dir = Mock()
        mock_cert_file = Mock()
        mock_key_file = Mock()

        # Set up the path hierarchy using side_effect for __truediv__
        def ca_dir_truediv(name: str) -> Mock:
            if name == "server_certs":
                return mock_server_certs_dir
            return Mock()

        def server_certs_truediv(name: str) -> Mock:
            return mock_server_cert_dir

        def server_cert_dir_truediv(name: str) -> Mock:
            if name == "example.com.crt":
                return mock_cert_file
            elif name == "example.com.key":
                return mock_key_file
            return Mock()

        mock_ca_dir_path.__truediv__ = Mock(side_effect=ca_dir_truediv)
        mock_server_certs_dir.__truediv__ = Mock(side_effect=server_certs_truediv)
        mock_server_cert_dir.__truediv__ = Mock(side_effect=server_cert_dir_truediv)

        # Certificate files don't exist
        mock_cert_file.exists.return_value = False
        mock_key_file.exists.return_value = False

        mock_path_class.return_value = mock_ca_dir_path

        result = _create_server_certificate(
            hostname="example.com",
            ca_dir="/test/config/ca",
            san=("api.example.com", "www.example.com"),
            validity_days=90,
            force=False,
        )

        assert isinstance(result, Success)
        assert "Server certificate created successfully" in result.message
        mock_ca_manager.create_server_certificate.assert_called_once_with(
            hostname="example.com",
            san_list=["api.example.com", "www.example.com"],
            validity_days=90,
        )

    @patch("vibectl.server.main.Path")
    def test_create_server_certificate_ca_not_found(
        self, mock_path_class: Mock
    ) -> None:
        """Test server certificate creation when CA directory doesn't exist."""
        mock_ca_dir_path = Mock()
        mock_ca_dir_path.exists.return_value = False  # CA directory doesn't exist
        mock_path_class.return_value = mock_ca_dir_path

        result = _create_server_certificate(
            hostname="example.com",
            ca_dir="/test/config/ca",
            san=(),
            validity_days=90,
            force=False,
        )

        assert isinstance(result, Error)
        assert "CA directory not found" in result.error

    @patch("vibectl.server.main.CAManager")
    @patch("vibectl.server.main.Path")
    def test_create_server_certificate_already_exists(
        self, mock_path_class: Mock, mock_ca_manager_class: Mock
    ) -> None:
        """Test server certificate creation when certificate already exists."""
        mock_ca_manager = Mock()
        mock_ca_manager_class.return_value = mock_ca_manager

        # Create mock path instances with proper magic method support
        mock_ca_dir_path = Mock()
        mock_ca_dir_path.exists.return_value = True  # CA directory exists

        # Mock server_certs directory structure
        mock_server_certs_dir = Mock()
        mock_server_cert_dir = Mock()
        mock_cert_file = Mock()
        mock_key_file = Mock()

        # Set up the path hierarchy using side_effect for __truediv__
        def ca_dir_truediv(name: str) -> Mock:
            if name == "server_certs":
                return mock_server_certs_dir
            return Mock()

        def server_certs_truediv(name: str) -> Mock:
            return mock_server_cert_dir

        def server_cert_dir_truediv(name: str) -> Mock:
            if name == "example.com.crt":
                return mock_cert_file
            elif name == "example.com.key":
                return mock_key_file
            return Mock()

        mock_ca_dir_path.__truediv__ = Mock(side_effect=ca_dir_truediv)
        mock_server_certs_dir.__truediv__ = Mock(side_effect=server_certs_truediv)
        mock_server_cert_dir.__truediv__ = Mock(side_effect=server_cert_dir_truediv)

        # Certificate files exist
        mock_cert_file.exists.return_value = True
        mock_key_file.exists.return_value = True

        mock_path_class.return_value = mock_ca_dir_path

        result = _create_server_certificate(
            hostname="example.com",
            ca_dir="/test/config/ca",
            san=(),
            validity_days=90,
            force=False,
        )

        assert isinstance(result, Error)
        assert "Certificate for example.com already exists" in result.error

    @patch("vibectl.server.main.CAManager")
    @patch("vibectl.server.main.Path")
    def test_create_server_certificate_force_overwrite(
        self, mock_path_class: Mock, mock_ca_manager_class: Mock
    ) -> None:
        """Test server certificate creation with force overwrite."""
        mock_ca_manager = Mock()
        mock_ca_manager_class.return_value = mock_ca_manager

        mock_cert_path = Path(
            "/test/config/ca/server_certs/example.com/example.com.crt"
        )
        mock_key_path = Path("/test/config/ca/server_certs/example.com/example.com.key")
        mock_ca_manager.create_server_certificate.return_value = (
            mock_cert_path,
            mock_key_path,
        )

        # Create mock path instances with proper magic method support
        mock_ca_dir_path = Mock()
        mock_ca_dir_path.exists.return_value = True  # CA directory exists

        # Mock server_certs directory structure - even with force=True, these
        # paths are still created
        mock_server_certs_dir = Mock()
        mock_server_cert_dir = Mock()  # server_certs/example.com/
        mock_cert_file = Mock()
        mock_key_file = Mock()

        # Set up the path hierarchy using side_effect for __truediv__
        def ca_dir_truediv(name: str) -> Mock:
            if name == "server_certs":
                return mock_server_certs_dir
            return Mock()

        def server_certs_truediv(name: str) -> Mock:
            if name == "example.com":
                return mock_server_cert_dir
            return Mock()

        def server_cert_dir_truediv(name: str) -> Mock:
            if name == "example.com.crt":
                return mock_cert_file
            elif name == "example.com.key":
                return mock_key_file
            return Mock()

        mock_ca_dir_path.__truediv__ = Mock(side_effect=ca_dir_truediv)
        mock_server_certs_dir.__truediv__ = Mock(side_effect=server_certs_truediv)
        mock_server_cert_dir.__truediv__ = Mock(side_effect=server_cert_dir_truediv)

        # With force=True, we skip existence checks but still need the path structure
        mock_cert_file.exists.return_value = True  # File exists but we force overwrite
        mock_key_file.exists.return_value = True  # File exists but we force overwrite

        mock_path_class.return_value = mock_ca_dir_path

        result = _create_server_certificate(
            hostname="example.com",
            ca_dir="/test/config/ca",
            san=("api.example.com",),
            validity_days=180,
            force=True,
        )

        assert isinstance(result, Success)
        assert "Server certificate created successfully" in result.message
        mock_ca_manager.create_server_certificate.assert_called_once_with(
            hostname="example.com",
            san_list=["api.example.com"],
            validity_days=180,
        )

    @patch("vibectl.server.main.CAManager")
    @patch("vibectl.server.main.Path")
    def test_create_server_certificate_exception(
        self, mock_path_class: Mock, mock_ca_manager_class: Mock
    ) -> None:
        """Test server certificate creation with unexpected exception."""
        mock_ca_manager = Mock()
        mock_ca_manager_class.return_value = mock_ca_manager
        mock_ca_manager.create_server_certificate.side_effect = Exception(
            "Unexpected error"
        )

        # Create mock path instances with proper magic method support
        mock_ca_dir_path = Mock()
        mock_ca_dir_path.exists.return_value = True  # CA directory exists

        # Mock server_certs directory structure
        mock_server_certs_dir = Mock()
        mock_server_cert_dir = Mock()
        mock_cert_file = Mock()
        mock_key_file = Mock()

        # Set up the path hierarchy using side_effect for __truediv__
        def ca_dir_truediv(name: str) -> Mock:
            if name == "server_certs":
                return mock_server_certs_dir
            return Mock()

        def server_certs_truediv(name: str) -> Mock:
            return mock_server_cert_dir

        def server_cert_dir_truediv(name: str) -> Mock:
            if name == "example.com.crt":
                return mock_cert_file
            elif name == "example.com.key":
                return mock_key_file
            return Mock()

        mock_ca_dir_path.__truediv__ = Mock(side_effect=ca_dir_truediv)
        mock_server_certs_dir.__truediv__ = Mock(side_effect=server_certs_truediv)
        mock_server_cert_dir.__truediv__ = Mock(side_effect=server_cert_dir_truediv)

        # Certificate files don't exist
        mock_cert_file.exists.return_value = False
        mock_key_file.exists.return_value = False

        mock_path_class.return_value = mock_ca_dir_path

        result = _create_server_certificate(
            hostname="example.com",
            ca_dir="/test/config/ca",
            san=(),
            validity_days=90,
            force=False,
        )

        assert isinstance(result, Error)
        assert "Unexpected error during certificate creation" in result.error


class TestCertificateStatusChecking:
    """Test certificate status checking functionality."""

    @patch("pathlib.Path.exists")
    def test_check_certificate_status_valid(self, mock_exists: Mock) -> None:
        """Test checking status of valid certificate."""
        from datetime import datetime, timedelta

        from vibectl.server.ca_manager import CertificateInfo

        mock_exists.return_value = True

        # Mock a valid certificate that doesn't expire soon
        mock_cert_info = Mock(spec=CertificateInfo)
        mock_cert_info.is_expired = False
        mock_cert_info.expires_soon.return_value = False
        mock_cert_info.not_valid_after = datetime.now().astimezone() + timedelta(
            days=60
        )

        mock_ca_manager = Mock()
        mock_ca_manager.get_certificate_info.return_value = mock_cert_info

        # Mock table for status display
        mock_table = Mock()

        cert_path = Path("/test/cert.pem")
        warnings_found = _check_certificate_status(
            cert_path=cert_path,
            cert_type="Server",
            ca_manager=mock_ca_manager,
            days=30,
            status_table=mock_table,
        )

        assert warnings_found is False  # No warnings for valid certificate
        mock_ca_manager.get_certificate_info.assert_called_once_with(cert_path)
        mock_table.add_row.assert_called_once()

    @patch("pathlib.Path.exists")
    def test_check_certificate_status_expiring_soon(self, mock_exists: Mock) -> None:
        """Test checking status of certificate expiring soon."""
        from datetime import datetime, timedelta

        from vibectl.server.ca_manager import CertificateInfo

        mock_exists.return_value = True

        # Mock a certificate that expires soon
        mock_cert_info = Mock(spec=CertificateInfo)
        mock_cert_info.is_expired = False
        mock_cert_info.expires_soon.return_value = True
        mock_cert_info.not_valid_after = datetime.now().astimezone() + timedelta(
            days=15
        )

        mock_ca_manager = Mock()
        mock_ca_manager.get_certificate_info.return_value = mock_cert_info

        mock_table = Mock()
        cert_path = Path("/test/cert.pem")

        warnings_found = _check_certificate_status(
            cert_path=cert_path,
            cert_type="Root CA",
            ca_manager=mock_ca_manager,
            days=30,
            status_table=mock_table,
        )

        assert warnings_found is True  # Warnings for expiring certificate
        mock_cert_info.expires_soon.assert_called_with(30)

    @patch("pathlib.Path.exists")
    def test_check_certificate_status_expired(self, mock_exists: Mock) -> None:
        """Test checking status of expired certificate."""
        from datetime import datetime, timedelta

        from vibectl.server.ca_manager import CertificateInfo

        mock_exists.return_value = True

        # Mock an expired certificate
        mock_cert_info = Mock(spec=CertificateInfo)
        mock_cert_info.is_expired = True
        mock_cert_info.expires_soon.return_value = True
        mock_cert_info.not_valid_after = datetime.now().astimezone() - timedelta(days=5)

        mock_ca_manager = Mock()
        mock_ca_manager.get_certificate_info.return_value = mock_cert_info

        mock_table = Mock()
        cert_path = Path("/test/cert.pem")

        warnings_found = _check_certificate_status(
            cert_path=cert_path,
            cert_type="Server",
            ca_manager=mock_ca_manager,
            days=30,
            status_table=mock_table,
        )

        assert warnings_found is True  # Warnings for expired certificate

    @patch("pathlib.Path.exists")
    def test_check_certificate_status_missing_file(self, mock_exists: Mock) -> None:
        """Test checking status when certificate file doesn't exist."""
        mock_exists.return_value = False

        mock_ca_manager = Mock()
        mock_table = Mock()
        cert_path = Path("/test/nonexistent.pem")

        warnings_found = _check_certificate_status(
            cert_path=cert_path,
            cert_type="Server",
            ca_manager=mock_ca_manager,
            days=30,
            status_table=mock_table,
        )

        assert warnings_found is True  # Warnings for missing certificate
        # get_certificate_info should not be called for missing files
        mock_ca_manager.get_certificate_info.assert_not_called()

    @patch("pathlib.Path.exists")
    def test_check_certificate_status_error(self, mock_exists: Mock) -> None:
        """Test checking status when certificate info retrieval fails."""
        mock_exists.return_value = True

        mock_ca_manager = Mock()
        mock_ca_manager.get_certificate_info.side_effect = CAManagerError(
            "Certificate parsing failed"
        )

        mock_table = Mock()
        cert_path = Path("/test/corrupt.pem")

        warnings_found = _check_certificate_status(
            cert_path=cert_path,
            cert_type="Server",
            ca_manager=mock_ca_manager,
            days=30,
            status_table=mock_table,
        )

        assert warnings_found is True  # Warnings for error reading certificate


class TestCAStatusDisplay:
    """Test CA status display functionality."""

    @patch("vibectl.server.main.ensure_config_dir")
    @patch("vibectl.server.main.CAManager")
    @patch("vibectl.server.main._check_certificate_status")
    @patch("vibectl.server.main.console_manager")
    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.glob")
    def test_show_ca_status_success(
        self,
        mock_glob: Mock,
        mock_exists: Mock,
        mock_console: Mock,
        mock_check_status: Mock,
        mock_ca_manager_class: Mock,
        mock_ensure_config_dir: Mock,
    ) -> None:
        """Test successful CA status display."""
        mock_config_dir = Path("/test/config")
        mock_ensure_config_dir.return_value = mock_config_dir
        mock_ca_manager = Mock()
        mock_ca_manager_class.return_value = mock_ca_manager

        ca_dir = mock_config_dir / "ca"

        # Mock paths exist
        mock_exists.return_value = True
        # Mock cert files found
        mock_glob.return_value = [Path("/test/config/ca/certs/server1.crt")]
        mock_check_status.return_value = False  # No warnings

        result = _show_ca_status(ca_dir=None, days=30)

        assert isinstance(result, Success)
        mock_ca_manager_class.assert_called_once_with(ca_dir)

    @patch("vibectl.server.main.ensure_config_dir")
    @patch("pathlib.Path.exists")
    def test_show_ca_status_ca_not_found(
        self, mock_exists: Mock, mock_ensure_config_dir: Mock
    ) -> None:
        """Test CA status when CA directory doesn't exist."""
        mock_config_dir = Path("/test/config")
        mock_ensure_config_dir.return_value = mock_config_dir
        ca_dir = mock_config_dir / "ca"

        # Mock CA directory doesn't exist
        mock_exists.return_value = False

        result = _show_ca_status(ca_dir=None, days=30)

        assert isinstance(result, Error)
        assert f"CA directory not found: {ca_dir}" in result.error

    @patch("vibectl.server.main.CAManager")
    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.glob")
    def test_show_ca_status_with_explicit_dir(
        self, mock_glob: Mock, mock_exists: Mock, mock_ca_manager_class: Mock
    ) -> None:
        """Test CA status with explicit CA directory."""
        mock_ca_manager = Mock()
        mock_ca_manager_class.return_value = mock_ca_manager

        ca_dir = Path("/custom/ca")

        # Mock paths exist and certificate files
        mock_exists.return_value = True
        mock_glob.return_value = []

        with (
            patch("vibectl.server.main._check_certificate_status") as mock_check,
        ):
            mock_check.return_value = False

            result = _show_ca_status(ca_dir="/custom/ca", days=30)

        assert isinstance(result, Success)
        mock_ca_manager_class.assert_called_once_with(ca_dir)

    @patch("vibectl.server.main.CAManager")
    @patch("pathlib.Path.exists")
    def test_show_ca_status_exception(
        self, mock_exists: Mock, mock_ca_manager_class: Mock
    ) -> None:
        """Test CA status with exception during processing."""
        mock_exists.return_value = True
        mock_ca_manager_class.side_effect = Exception("Unexpected error")

        result = _show_ca_status(ca_dir="/custom/ca", days=30)

        assert isinstance(result, Error)
        assert (
            "Unexpected error initializing CA manager: Unexpected error" in result.error
        )


class TestCertificateExpiryChecking:
    """Test certificate expiry checking functionality."""

    @patch("vibectl.server.main.ensure_config_dir")
    @patch("vibectl.server.main.CAManager")
    @patch("pathlib.Path.exists")
    @patch("vibectl.server.main._check_certificate_status")
    @patch("vibectl.server.main.console_manager")
    @patch("pathlib.Path.glob")
    def test_check_certificate_expiry_success(
        self,
        mock_glob: Mock,
        mock_console: Mock,
        mock_check_status: Mock,
        mock_exists: Mock,
        mock_ca_manager_class: Mock,
        mock_ensure_config_dir: Mock,
    ) -> None:
        """Test successful certificate expiry checking."""
        mock_config_dir = Path("/test/config")
        mock_ensure_config_dir.return_value = mock_config_dir
        mock_ca_manager = Mock()
        mock_ca_manager_class.return_value = mock_ca_manager

        # Mock CA directory exists
        mock_exists.return_value = True
        # Mock certificate files
        mock_glob.return_value = [Path("/test/config/ca/certs/server1.crt")]
        # Mock some certificates have warnings (expiring)
        mock_check_status.side_effect = [
            False,
            False,
            True,
        ]  # First two OK, third has warning

        result = _check_certificate_expiry(ca_dir=None, days=30)

        assert isinstance(result, Success)
        assert (
            mock_check_status.call_count == 3
        )  # Root CA, Intermediate CA, Server cert

    @patch("pathlib.Path.exists")
    def test_check_certificate_expiry_ca_not_found(self, mock_exists: Mock) -> None:
        """Test certificate expiry check when CA not found."""
        mock_exists.return_value = False

        result = _check_certificate_expiry(ca_dir="/nonexistent", days=30)

        assert isinstance(result, Error)
        assert "CA directory not found: /nonexistent" in result.error

    @patch("vibectl.server.main.ensure_config_dir")
    @patch("vibectl.server.main.CAManager")
    @patch("pathlib.Path.exists")
    @patch("vibectl.server.main._check_certificate_status")
    @patch("vibectl.server.main.console_manager")
    @patch("pathlib.Path.glob")
    def test_check_certificate_expiry_no_expiring_certs(
        self,
        mock_glob: Mock,
        mock_console: Mock,
        mock_check_status: Mock,
        mock_exists: Mock,
        mock_ca_manager_class: Mock,
        mock_ensure_config_dir: Mock,
    ) -> None:
        """Test certificate expiry check when no certificates are expiring."""
        mock_config_dir = Path("/test/config")
        mock_ensure_config_dir.return_value = mock_config_dir
        mock_ca_manager = Mock()
        mock_ca_manager_class.return_value = mock_ca_manager

        # Mock CA directory exists
        mock_exists.return_value = True
        # Mock certificate files
        mock_glob.return_value = [Path("/test/config/ca/certs/server1.crt")]
        # All certificates are valid - no warnings
        mock_check_status.return_value = False

        result = _check_certificate_expiry(ca_dir=None, days=30)

        assert isinstance(result, Success)
        # No warnings should be printed
        mock_console.print_warning.assert_not_called()


class TestServeCACommand:
    """Test the serve-ca CLI command."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("vibectl.server.main.ensure_config_dir")
    @patch("pathlib.Path.exists")
    @patch("vibectl.server.main.CAManager")
    @patch("vibectl.server.main._load_and_validate_config")
    @patch("vibectl.server.main._create_and_start_server_common")
    @patch("vibectl.server.main.handle_result")
    @patch("vibectl.server.main.console_manager")
    def test_serve_ca_command_success(
        self,
        mock_console: Mock,
        mock_handle_result: Mock,
        mock_create_server: Mock,
        mock_load_config: Mock,
        mock_ca_manager_class: Mock,
        mock_exists: Mock,
        mock_ensure_config_dir: Mock,
    ) -> None:
        """Test successful serve-ca command execution."""
        # Mock CA directory exists
        mock_ensure_config_dir.return_value = Path("/test/config")
        mock_exists.return_value = True

        # Mock CA manager and certificate creation
        mock_ca_manager = Mock()
        mock_ca_manager_class.return_value = mock_ca_manager
        cert_path = Path("/test/config/ca/certs/localhost/localhost.crt")
        key_path = Path("/test/config/ca/certs/localhost/localhost.key")
        mock_ca_manager.create_server_certificate.return_value = (cert_path, key_path)

        # Mock configuration and server creation
        mock_config = get_default_server_config()
        mock_load_config.return_value = Success(data=mock_config)
        mock_create_server.return_value = Success()

        result = self.runner.invoke(cli, ["serve-ca", "--hostname", "test.example.com"])

        assert result.exit_code == 0
        mock_ca_manager.create_server_certificate.assert_called_once()
        mock_load_config.assert_called_once()
        mock_create_server.assert_called_once()

    @patch("vibectl.server.main.ensure_config_dir")
    @patch("pathlib.Path.exists")
    @patch("vibectl.server.main.handle_result")
    def test_serve_ca_command_ca_not_found(
        self, mock_handle_result: Mock, mock_exists: Mock, mock_ensure_config_dir: Mock
    ) -> None:
        """Test serve-ca command when CA directory doesn't exist."""
        mock_ensure_config_dir.return_value = Path("/test/config")
        mock_exists.return_value = False

        result = self.runner.invoke(cli, ["serve-ca", "--hostname", "test.example.com"])

        assert result.exit_code == 0
        mock_handle_result.assert_called_once()
        # Should handle error about CA not found

    @patch("pathlib.Path.exists")
    @patch("vibectl.server.main.CAManager")
    @patch("vibectl.server.main._load_and_validate_config")
    @patch("vibectl.server.main._create_and_start_server_common")
    @patch("vibectl.server.main.handle_result")
    @patch("vibectl.server.main.console_manager")
    def test_serve_ca_command_with_explicit_ca_dir(
        self,
        mock_console: Mock,
        mock_handle_result: Mock,
        mock_create_server: Mock,
        mock_load_config: Mock,
        mock_ca_manager_class: Mock,
        mock_exists: Mock,
    ) -> None:
        """Test serve-ca command with explicit CA directory."""
        mock_exists.return_value = True

        # Mock CA manager and certificate creation
        mock_ca_manager = Mock()
        mock_ca_manager_class.return_value = mock_ca_manager
        cert_path = Path("/custom/ca/certs/example.com/example.com.crt")
        key_path = Path("/custom/ca/certs/example.com/example.com.key")
        mock_ca_manager.create_server_certificate.return_value = (cert_path, key_path)

        mock_config = get_default_server_config()
        mock_load_config.return_value = Success(data=mock_config)
        mock_create_server.return_value = Success()

        result = self.runner.invoke(
            cli,
            [
                "serve-ca",
                "--ca-dir",
                "/custom/ca",
                "--hostname",
                "example.com",
                "--san",
                "www.example.com",
                "--san",
                "api.example.com",
                "--validity-days",
                "30",
            ],
        )

        assert result.exit_code == 0
        # Verify certificate creation was called with correct parameters
        mock_ca_manager.create_server_certificate.assert_called_once_with(
            hostname="example.com",
            san_list=["www.example.com", "api.example.com"],
            validity_days=30,
        )


class TestCACommands:
    """Test CA-related CLI commands."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("vibectl.server.main._initialize_ca")
    @patch("vibectl.server.main.handle_result")
    def test_ca_init_command(
        self, mock_handle_result: Mock, mock_initialize: Mock
    ) -> None:
        """Test ca init command."""
        mock_initialize.return_value = Success(message="CA initialized")

        result = self.runner.invoke(
            cli,
            [
                "ca",
                "init",
                "--root-cn",
                "Test Root CA",
                "--intermediate-cn",
                "Test Intermediate CA",
                "--organization",
                "Test Org",
                "--country",
                "CA",
                "--force",
            ],
        )

        assert result.exit_code == 0
        mock_initialize.assert_called_once_with(
            None, "Test Root CA", "Test Intermediate CA", "Test Org", "CA", True
        )

    @patch("vibectl.server.main._create_server_certificate")
    @patch("vibectl.server.main.handle_result")
    def test_ca_create_server_cert_command(
        self, mock_handle_result: Mock, mock_create_cert: Mock
    ) -> None:
        """Test ca create-server-cert command."""
        mock_create_cert.return_value = Success(message="Certificate created")

        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.runner.invoke(
                cli,
                [
                    "ca",
                    "create-server-cert",
                    "example.com",
                    "--ca-dir",
                    temp_dir,
                    "--san",
                    "www.example.com",
                    "--validity-days",
                    "60",
                    "--force",
                ],
            )

        assert result.exit_code == 0
        mock_create_cert.assert_called_once_with(
            "example.com", temp_dir, ("www.example.com",), 60, True
        )

    @patch("vibectl.server.main._show_ca_status")
    @patch("vibectl.server.main.handle_result")
    def test_ca_status_command(
        self, mock_handle_result: Mock, mock_show_status: Mock
    ) -> None:
        """Test ca status command."""
        mock_show_status.return_value = Success(message="Status displayed")

        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.runner.invoke(
                cli, ["ca", "status", "--ca-dir", temp_dir, "--days", "60"]
            )

        assert result.exit_code == 0
        mock_show_status.assert_called_once_with(temp_dir, 60)

    @patch("vibectl.server.main._check_certificate_expiry")
    @patch("vibectl.server.main.handle_result")
    def test_ca_check_expiry_command(
        self, mock_handle_result: Mock, mock_check_expiry: Mock
    ) -> None:
        """Test ca check-expiry command."""
        mock_check_expiry.return_value = Success(message="Expiry checked")

        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.runner.invoke(
                cli, ["ca", "check-expiry", "--ca-dir", temp_dir, "--days", "45"]
            )

        assert result.exit_code == 0
        mock_check_expiry.assert_called_once_with(temp_dir, 45)

    def test_ca_group_help(self) -> None:
        """Test ca group shows help when no subcommand is provided."""
        result = self.runner.invoke(cli, ["ca"])

        assert result.exit_code == 0
        assert "Certificate Authority management commands" in result.output
