"""
Tests for the Certificate Authority (CA) Manager.

This test suite covers all aspects of the CA management system including:
- CA initialization and certificate hierarchy creation
- Server certificate generation with SAN extensions
- Certificate lifecycle management and expiry checking
- CA bundle creation and trust chain validation
- Error handling and edge cases
"""

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from cryptography import x509
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from vibectl.server.ca_manager import (
    CAManager,
    CAManagerError,
    CertificateInfo,
    setup_private_ca,
)


@pytest.fixture
def temp_ca_dir() -> Any:
    """Create a temporary directory for CA testing."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def ca_manager(temp_ca_dir: Any) -> Any:
    """Create a CA manager instance for testing."""
    return CAManager(temp_ca_dir)


@pytest.fixture
def initialized_ca(ca_manager: Any) -> Any:
    """Create an initialized CA for testing."""
    ca_manager.create_root_ca()
    ca_manager.create_intermediate_ca()
    return ca_manager


class TestCAManagerInit:
    """Test CA manager initialization."""

    def test_ca_manager_init_creates_directories(self, temp_ca_dir: Any) -> None:
        """Test CA manager creates required directories."""
        ca_manager = CAManager(temp_ca_dir)

        assert ca_manager.ca_dir.exists()
        assert ca_manager.root_ca_dir.exists()
        assert ca_manager.intermediate_ca_dir.exists()
        assert ca_manager.server_certs_dir.exists()

    def test_ca_manager_sets_secure_permissions(self, temp_ca_dir: Any) -> None:
        """Test CA manager sets secure directory permissions."""
        ca_manager = CAManager(temp_ca_dir)

        # Check that directories have restrictive permissions (owner only)
        try:
            stat_info = os.stat(ca_manager.ca_dir)
            permissions = oct(stat_info.st_mode)[-3:]
            assert permissions == "700", (
                f"CA directory permissions should be 700, got {permissions}"
            )
        except OSError:
            # Skip permission test on systems that don't support it
            pass


class TestRootCACreation:
    """Test Root CA creation functionality."""

    def test_create_root_ca_default_params(self, ca_manager: Any) -> None:
        """Test creating Root CA with default parameters."""
        cert_path, key_path = ca_manager.create_root_ca()

        assert cert_path.exists()
        assert key_path.exists()
        assert cert_path.name == "ca.crt"
        assert key_path.name == "ca.key"

        # Verify certificate content
        with open(cert_path, "rb") as f:
            cert_data = f.read()
        cert = x509.load_pem_x509_certificate(cert_data)

        # Check subject
        subject_dict = {attr.oid: attr.value for attr in cert.subject}
        assert subject_dict[NameOID.COMMON_NAME] == "vibectl Root CA"
        assert subject_dict[NameOID.ORGANIZATION_NAME] == "vibectl"
        assert subject_dict[NameOID.COUNTRY_NAME] == "US"

        # Check it's a CA certificate
        basic_constraints_ext = cert.extensions.get_extension_for_oid(
            x509.ExtensionOID.BASIC_CONSTRAINTS
        )
        basic_constraints = basic_constraints_ext.value
        assert isinstance(basic_constraints, x509.BasicConstraints)
        assert basic_constraints.ca is True
        assert basic_constraints.path_length == 1

    def test_create_root_ca_custom_params(self, ca_manager: Any) -> None:
        """Test creating Root CA with custom parameters."""
        cert_path, key_path = ca_manager.create_root_ca(
            common_name="Custom Root CA",
            organization="Test Org",
            country="CA",
            validity_years=5,
        )

        assert cert_path.exists()
        assert key_path.exists()

        # Verify certificate content
        with open(cert_path, "rb") as f:
            cert_data = f.read()
        cert = x509.load_pem_x509_certificate(cert_data)

        # Check subject
        subject_dict = {attr.oid: attr.value for attr in cert.subject}
        assert subject_dict[NameOID.COMMON_NAME] == "Custom Root CA"
        assert subject_dict[NameOID.ORGANIZATION_NAME] == "Test Org"
        assert subject_dict[NameOID.COUNTRY_NAME] == "CA"

        # Check validity period (approximately 5 years)
        validity_period = cert.not_valid_after_utc - cert.not_valid_before_utc
        expected_days = 365 * 5
        assert abs(validity_period.days - expected_days) <= 1

    def test_create_root_ca_overwrites_existing(self, ca_manager: Any) -> None:
        """Test creating Root CA overwrites existing certificates."""
        # Create first CA
        cert_path1, key_path1 = ca_manager.create_root_ca()
        first_cert_content = cert_path1.read_bytes()

        # Create second CA
        cert_path2, key_path2 = ca_manager.create_root_ca()
        second_cert_content = cert_path2.read_bytes()

        # Paths should be the same but content should be different
        assert cert_path1 == cert_path2
        assert key_path1 == key_path2
        assert first_cert_content != second_cert_content


class TestIntermediateCACreation:
    """Test Intermediate CA creation functionality."""

    def test_create_intermediate_ca_without_root_ca(self, ca_manager: Any) -> None:
        """Test creating Intermediate CA fails without Root CA."""
        with pytest.raises(CAManagerError, match="Root CA not found"):
            ca_manager.create_intermediate_ca()

    def test_create_intermediate_ca_default_params(self, ca_manager: Any) -> None:
        """Test creating Intermediate CA with default parameters."""
        # First create Root CA
        ca_manager.create_root_ca()

        cert_path, key_path = ca_manager.create_intermediate_ca()

        assert cert_path.exists()
        assert key_path.exists()
        assert cert_path.name == "ca.crt"
        assert key_path.name == "ca.key"

        # Verify certificate content
        with open(cert_path, "rb") as f:
            cert_data = f.read()
        cert = x509.load_pem_x509_certificate(cert_data)

        # Check subject
        subject_dict = {attr.oid: attr.value for attr in cert.subject}
        assert subject_dict[NameOID.COMMON_NAME] == "vibectl Intermediate CA"

        # Check it's signed by Root CA
        assert cert.issuer != cert.subject  # Not self-signed

        # Check it's a CA certificate
        basic_constraints_ext = cert.extensions.get_extension_for_oid(
            x509.ExtensionOID.BASIC_CONSTRAINTS
        )
        basic_constraints = basic_constraints_ext.value
        assert isinstance(basic_constraints, x509.BasicConstraints)
        assert basic_constraints.ca is True
        assert basic_constraints.path_length == 0  # Can't sign other CAs

    def test_create_intermediate_ca_custom_params(self, ca_manager: Any) -> None:
        """Test creating Intermediate CA with custom parameters."""
        # First create Root CA
        ca_manager.create_root_ca()

        cert_path, key_path = ca_manager.create_intermediate_ca(
            common_name="Custom Intermediate CA",
            organization="Test Org",
            country="CA",
            validity_years=3,
        )

        assert cert_path.exists()
        assert key_path.exists()

        # Verify certificate content
        with open(cert_path, "rb") as f:
            cert_data = f.read()
        cert = x509.load_pem_x509_certificate(cert_data)

        # Check subject
        subject_dict = {attr.oid: attr.value for attr in cert.subject}
        assert subject_dict[NameOID.COMMON_NAME] == "Custom Intermediate CA"
        assert subject_dict[NameOID.ORGANIZATION_NAME] == "Test Org"
        assert subject_dict[NameOID.COUNTRY_NAME] == "CA"

        # Check validity period (approximately 3 years)
        validity_period = cert.not_valid_after_utc - cert.not_valid_before_utc
        expected_days = 365 * 3
        assert abs(validity_period.days - expected_days) <= 1


class TestServerCertificateCreation:
    """Test server certificate creation functionality."""

    def test_create_server_cert_without_intermediate_ca(self, ca_manager: Any) -> None:
        """Test creating server certificate fails without Intermediate CA."""
        # Create only Root CA
        ca_manager.create_root_ca()

        with pytest.raises(CAManagerError, match="Intermediate CA not found"):
            ca_manager.create_server_certificate("example.com")

    def test_create_server_cert_basic(self, initialized_ca: Any) -> None:
        """Test creating basic server certificate."""
        cert_path, key_path = initialized_ca.create_server_certificate("example.com")

        assert cert_path.exists()
        assert key_path.exists()
        assert cert_path.name == "example.com.crt"
        assert key_path.name == "example.com.key"

        # Verify certificate content
        with open(cert_path, "rb") as f:
            cert_data = f.read()
        cert = x509.load_pem_x509_certificate(cert_data)

        # Check subject
        subject_dict = {attr.oid: attr.value for attr in cert.subject}
        assert subject_dict[NameOID.COMMON_NAME] == "example.com"

        # Check it's NOT a CA certificate
        basic_constraints_ext = cert.extensions.get_extension_for_oid(
            x509.ExtensionOID.BASIC_CONSTRAINTS
        )
        basic_constraints = basic_constraints_ext.value
        assert isinstance(basic_constraints, x509.BasicConstraints)
        assert basic_constraints.ca is False

        # Check extended key usage for server authentication
        ext_key_usage_ext = cert.extensions.get_extension_for_oid(
            x509.ExtensionOID.EXTENDED_KEY_USAGE
        )
        ext_key_usage = ext_key_usage_ext.value
        assert isinstance(ext_key_usage, x509.ExtendedKeyUsage)
        assert ExtendedKeyUsageOID.SERVER_AUTH in ext_key_usage

        # Check SAN extension
        san_extension = cert.extensions.get_extension_for_oid(
            x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
        san_ext = san_extension.value
        assert isinstance(san_ext, x509.SubjectAlternativeName)
        san_names = [str(name.value) for name in san_ext]
        assert "example.com" in san_names

    def test_create_server_cert_with_san_list(self, initialized_ca: Any) -> None:
        """Test creating server certificate with SAN list."""
        san_list = ["example.com", "www.example.com", "api.example.com", "127.0.0.1"]
        cert_path, key_path = initialized_ca.create_server_certificate(
            "example.com", san_list=san_list
        )

        assert cert_path.exists()
        assert key_path.exists()

        # Verify certificate content
        with open(cert_path, "rb") as f:
            cert_data = f.read()
        cert = x509.load_pem_x509_certificate(cert_data)

        # Check SAN extension includes all names
        san_extension = cert.extensions.get_extension_for_oid(
            x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
        san_ext = san_extension.value
        assert isinstance(san_ext, x509.SubjectAlternativeName)
        # Convert all SAN values to strings for comparison
        # (IP addresses are IPv4Address objects)
        san_names = [str(name.value) for name in san_ext]

        for san_name in san_list:
            assert san_name in san_names

    def test_create_server_cert_custom_validity(self, initialized_ca: Any) -> None:
        """Test creating server certificate with custom validity period."""
        cert_path, key_path = initialized_ca.create_server_certificate(
            "example.com", validity_days=30
        )

        assert cert_path.exists()
        assert key_path.exists()

        # Verify certificate content
        with open(cert_path, "rb") as f:
            cert_data = f.read()
        cert = x509.load_pem_x509_certificate(cert_data)

        # Check validity period (approximately 30 days)
        validity_period = cert.not_valid_after_utc - cert.not_valid_before_utc
        assert abs(validity_period.days - 30) <= 1

    def test_create_server_cert_overwrites_existing(self, initialized_ca: Any) -> None:
        """Test creating server certificate overwrites existing certificate."""
        # Create first certificate
        cert_path1, key_path1 = initialized_ca.create_server_certificate("example.com")
        first_cert_content = cert_path1.read_bytes()

        # Create second certificate with same hostname
        cert_path2, key_path2 = initialized_ca.create_server_certificate("example.com")
        second_cert_content = cert_path2.read_bytes()

        # Paths should be the same but content should be different
        assert cert_path1 == cert_path2
        assert key_path1 == key_path2
        assert first_cert_content != second_cert_content


class TestCABundleCreation:
    """Test CA bundle creation functionality."""

    def test_create_ca_bundle_without_ca(self, ca_manager: Any) -> None:
        """Test creating CA bundle fails without CA certificates."""
        with pytest.raises(CAManagerError, match="CA certificates not found"):
            ca_manager.create_ca_bundle()

    def test_create_ca_bundle_with_root_only(self, ca_manager: Any) -> None:
        """Test creating CA bundle with only Root CA."""
        ca_manager.create_root_ca()

        bundle_path = ca_manager.create_ca_bundle()

        assert bundle_path.exists()
        assert bundle_path.name == "ca-bundle.crt"

        # Verify bundle content
        bundle_content = bundle_path.read_text()
        assert "BEGIN CERTIFICATE" in bundle_content
        assert "END CERTIFICATE" in bundle_content

        # Should contain only Root CA
        cert_count = bundle_content.count("BEGIN CERTIFICATE")
        assert cert_count == 1

    def test_create_ca_bundle_with_intermediate(self, initialized_ca: Any) -> None:
        """Test creating CA bundle with Root and Intermediate CA."""
        bundle_path = initialized_ca.create_ca_bundle()

        assert bundle_path.exists()
        assert bundle_path.name == "ca-bundle.crt"

        # Verify bundle content
        bundle_content = bundle_path.read_text()

        # Should contain both Root and Intermediate CA
        cert_count = bundle_content.count("BEGIN CERTIFICATE")
        assert cert_count == 2


class TestCertificateInfo:
    """Test certificate information functionality."""

    def test_get_certificate_info_nonexistent_file(self, ca_manager: Any) -> None:
        """Test getting certificate info for nonexistent file."""
        with pytest.raises(CAManagerError, match="Certificate file not found"):
            ca_manager.get_certificate_info(Path("/nonexistent/cert.crt"))

    def test_get_certificate_info_root_ca(self, ca_manager: Any) -> None:
        """Test getting certificate info for Root CA."""
        cert_path, _ = ca_manager.create_root_ca(
            common_name="Test Root CA", validity_years=1
        )

        cert_info = ca_manager.get_certificate_info(cert_path)

        assert isinstance(cert_info, CertificateInfo)
        assert cert_info.subject_cn == "Test Root CA"
        assert not cert_info.is_expired

        # Should expire in approximately 1 year
        expires_in_days = (cert_info.not_valid_after - datetime.now().astimezone()).days
        assert 360 <= expires_in_days <= 370  # Allow some tolerance

    def test_get_certificate_info_server_cert(self, initialized_ca: Any) -> None:
        """Test getting certificate info for server certificate."""
        cert_path, _ = initialized_ca.create_server_certificate(
            "test.example.com", validity_days=60
        )

        cert_info = initialized_ca.get_certificate_info(cert_path)

        assert isinstance(cert_info, CertificateInfo)
        assert cert_info.subject_cn == "test.example.com"
        assert not cert_info.is_expired

        # Should expire in approximately 60 days
        expires_in_days = (cert_info.not_valid_after - datetime.now().astimezone()).days
        assert 58 <= expires_in_days <= 62  # Allow some tolerance

    def test_certificate_info_expires_soon(self, initialized_ca: Any) -> None:
        """Test certificate expiry detection."""
        cert_path, _ = initialized_ca.create_server_certificate(
            "test.example.com",
            validity_days=10,  # Short validity for testing
        )

        cert_info = initialized_ca.get_certificate_info(cert_path)

        assert not cert_info.is_expired
        assert cert_info.expires_soon(days=30)  # Should expire within 30 days
        assert not cert_info.expires_soon(days=5)  # Should not expire within 5 days


class TestCertificateExpiryChecking:
    """Test certificate expiry checking functionality."""

    def test_check_certificate_expiry_no_certificates(self, ca_manager: Any) -> None:
        """Test checking expiry with no certificates."""
        expiring_certs = ca_manager.check_certificate_expiry()
        assert len(expiring_certs) == 0

    def test_check_certificate_expiry_with_valid_certs(
        self, initialized_ca: Any
    ) -> None:
        """Test checking expiry with valid certificates."""
        # Create some certificates with normal validity
        initialized_ca.create_server_certificate("example1.com", validity_days=90)
        initialized_ca.create_server_certificate("example2.com", validity_days=120)

        expiring_certs = initialized_ca.check_certificate_expiry(days_threshold=30)
        assert len(expiring_certs) == 0

    def test_check_certificate_expiry_with_expiring_certs(
        self, initialized_ca: Any
    ) -> None:
        """Test checking expiry with certificates expiring soon."""
        # Create certificates with short validity
        initialized_ca.create_server_certificate("expiring1.com", validity_days=10)
        initialized_ca.create_server_certificate("expiring2.com", validity_days=15)
        initialized_ca.create_server_certificate("valid.com", validity_days=90)

        expiring_certs = initialized_ca.check_certificate_expiry(days_threshold=30)
        assert len(expiring_certs) == 2

        # Check that the expiring certificates are identified
        expiring_names = {cert_info.subject_cn for _, cert_info in expiring_certs}
        assert "expiring1.com" in expiring_names
        assert "expiring2.com" in expiring_names
        assert "valid.com" not in expiring_names

    def test_check_certificate_expiry_custom_threshold(
        self, initialized_ca: Any
    ) -> None:
        """Test checking expiry with custom threshold."""
        # Create certificate with 20 days validity
        initialized_ca.create_server_certificate("test.com", validity_days=20)

        # Should not be expiring within 10 days
        expiring_certs = initialized_ca.check_certificate_expiry(days_threshold=10)
        assert len(expiring_certs) == 0

        # Should be expiring within 30 days
        expiring_certs = initialized_ca.check_certificate_expiry(days_threshold=30)
        assert len(expiring_certs) == 1


class TestPrivateCASetup:
    """Test the setup_private_ca helper function."""

    def test_setup_private_ca_default_params(self, temp_ca_dir: Any) -> None:
        """Test setting up private CA with default parameters."""
        ca_manager = setup_private_ca(temp_ca_dir)

        assert isinstance(ca_manager, CAManager)
        assert ca_manager.ca_dir == temp_ca_dir

        # Check that both CAs were created
        assert (ca_manager.root_ca_dir / "ca.crt").exists()
        assert (ca_manager.root_ca_dir / "ca.key").exists()
        assert (ca_manager.intermediate_ca_dir / "ca.crt").exists()
        assert (ca_manager.intermediate_ca_dir / "ca.key").exists()

    def test_setup_private_ca_custom_params(self, temp_ca_dir: Any) -> None:
        """Test setting up private CA with custom parameters."""
        ca_manager = setup_private_ca(
            temp_ca_dir, root_cn="Custom Root", intermediate_cn="Custom Intermediate"
        )

        assert isinstance(ca_manager, CAManager)

        # Verify custom names were used
        root_cert_info = ca_manager.get_certificate_info(
            ca_manager.root_ca_dir / "ca.crt"
        )
        assert root_cert_info.subject_cn == "Custom Root"

        intermediate_cert_info = ca_manager.get_certificate_info(
            ca_manager.intermediate_ca_dir / "ca.crt"
        )
        assert intermediate_cert_info.subject_cn == "Custom Intermediate"


class TestErrorHandling:
    """Test error handling in CA manager."""

    def test_load_root_ca_missing_cert(self, ca_manager: Any) -> None:
        """Test loading Root CA with missing certificate file."""
        # Create key file but not certificate
        (ca_manager.root_ca_dir / "ca.key").touch()

        with pytest.raises(CAManagerError, match="Root CA not found"):
            ca_manager._load_root_ca()

    def test_load_root_ca_missing_key(self, ca_manager: Any) -> None:
        """Test loading Root CA with missing key file."""
        # Create certificate file but not key
        (ca_manager.root_ca_dir / "ca.crt").touch()

        with pytest.raises(CAManagerError, match="Root CA private key not found"):
            ca_manager._load_root_ca()

    def test_load_intermediate_ca_missing_cert(self, ca_manager: Any) -> None:
        """Test loading Intermediate CA with missing certificate file."""
        # Create Root CA first
        ca_manager.create_root_ca()

        # Create key file but not certificate
        (ca_manager.intermediate_ca_dir / "ca.key").touch()

        with pytest.raises(CAManagerError, match="Intermediate CA not found"):
            ca_manager._load_intermediate_ca()

    def test_load_intermediate_ca_missing_key(self, ca_manager: Any) -> None:
        """Test loading Intermediate CA with missing key file."""
        # Create Root CA first
        ca_manager.create_root_ca()

        # Create certificate file but not key
        (ca_manager.intermediate_ca_dir / "ca.crt").touch()

        with pytest.raises(
            CAManagerError, match="Intermediate CA private key not found"
        ):
            ca_manager._load_intermediate_ca()

    def test_invalid_certificate_file(self, ca_manager: Any) -> None:
        """Test handling invalid certificate file."""
        # Create a file with invalid certificate content
        invalid_cert_path = ca_manager.ca_dir / "invalid.crt"
        invalid_cert_path.write_text("This is not a valid certificate")

        with pytest.raises(CAManagerError, match="Failed to load certificate"):
            ca_manager.get_certificate_info(invalid_cert_path)


class TestFilePermissions:
    """Test file permission handling."""

    def test_certificate_file_permissions(self, ca_manager: Any) -> None:
        """Test that certificate files have correct permissions."""
        cert_path, key_path = ca_manager.create_root_ca()

        try:
            # Certificate should be readable by all (644)
            cert_stat = os.stat(cert_path)
            cert_perms = oct(cert_stat.st_mode)[-3:]
            assert cert_perms == "644", (
                f"Certificate should have 644 permissions, got {cert_perms}"
            )

            # Private key should be readable only by owner (600)
            key_stat = os.stat(key_path)
            key_perms = oct(key_stat.st_mode)[-3:]
            assert key_perms == "600", (
                f"Private key should have 600 permissions, got {key_perms}"
            )
        except OSError:
            # Skip permission test on systems that don't support it
            pytest.skip("File permissions not supported on this system")

    def test_server_cert_file_permissions(self, initialized_ca: Any) -> None:
        """Test that server certificate files have correct permissions."""
        cert_path, key_path = initialized_ca.create_server_certificate("example.com")

        try:
            # Certificate should be readable by all (644)
            cert_stat = os.stat(cert_path)
            cert_perms = oct(cert_stat.st_mode)[-3:]
            assert cert_perms == "644", (
                f"Certificate should have 644 permissions, got {cert_perms}"
            )

            # Private key should be readable only by owner (600)
            key_stat = os.stat(key_path)
            key_perms = oct(key_stat.st_mode)[-3:]
            assert key_perms == "600", (
                f"Private key should have 600 permissions, got {key_perms}"
            )
        except OSError:
            # Skip permission test on systems that don't support it
            pytest.skip("File permissions not supported on this system")
