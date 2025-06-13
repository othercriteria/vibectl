"""
Tests for certificate utilities.

Tests cover certificate validation, loading, generation, and utility functions
for TLS support in the vibectl LLM proxy server.
"""

import os
import tempfile
from pathlib import Path
from typing import cast
from unittest.mock import Mock, patch

import pytest
from cryptography import x509

from vibectl.server.cert_utils import (
    create_certificate_signing_request,
    ensure_certificate_exists,
    generate_self_signed_certificate,
    get_default_cert_paths,
    handle_certificate_generation_for_server,
    load_certificate_credentials,
    validate_certificate_files,
)
from vibectl.types import (
    CertificateError,
    CertificateGenerationError,
    CertificateLoadError,
)


class TestCertificateValidation:
    """Test certificate file validation functions."""

    def test_validate_certificate_files_success(self) -> None:
        """Test successful validation of certificate files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "test.crt"
            key_file = Path(temp_dir) / "test.key"

            # Create test files
            cert_file.write_text("test certificate")
            key_file.write_text("test key")

            # Should not raise an exception
            validate_certificate_files(str(cert_file), str(key_file))

    def test_validate_certificate_files_missing_cert(self) -> None:
        """Test validation failure when certificate file is missing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "missing.crt"
            key_file = Path(temp_dir) / "test.key"

            # Create only key file
            key_file.write_text("test key")

            with pytest.raises(
                CertificateLoadError, match="Certificate file not found"
            ):
                validate_certificate_files(str(cert_file), str(key_file))

    def test_validate_certificate_files_missing_key(self) -> None:
        """Test validation failure when key file is missing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "test.crt"
            key_file = Path(temp_dir) / "missing.key"

            # Create only cert file
            cert_file.write_text("test certificate")

            with pytest.raises(
                CertificateLoadError, match="Private key file not found"
            ):
                validate_certificate_files(str(cert_file), str(key_file))

    def test_validate_certificate_files_cert_is_directory(self) -> None:
        """Test validation failure when certificate path is a directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "cert_dir"
            key_file = Path(temp_dir) / "test.key"

            # Create directory instead of file
            cert_file.mkdir()
            key_file.write_text("test key")

            with pytest.raises(
                CertificateLoadError, match="Certificate path is not a file"
            ):
                validate_certificate_files(str(cert_file), str(key_file))

    def test_validate_certificate_files_key_is_directory(self) -> None:
        """Test validation failure when key path is a directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "test.crt"
            key_file = Path(temp_dir) / "key_dir"

            # Create directory instead of file
            cert_file.write_text("test certificate")
            key_file.mkdir()

            with pytest.raises(
                CertificateLoadError, match="Private key path is not a file"
            ):
                validate_certificate_files(str(cert_file), str(key_file))

    @pytest.mark.skipif(os.geteuid() == 0, reason="Root can read unreadable files")
    def test_validate_certificate_files_permission_error_cert(self) -> None:
        """Test validation failure when certificate file is not readable."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "unreadable.crt"
            key_file = Path(temp_dir) / "test.key"

            # Create files
            cert_file.write_text("test certificate")
            key_file.write_text("test key")

            # Make certificate file unreadable
            cert_file.chmod(0o000)

            try:
                with pytest.raises(
                    CertificateLoadError, match="Cannot read certificate file"
                ):
                    validate_certificate_files(str(cert_file), str(key_file))
            finally:
                # Restore permissions for cleanup
                cert_file.chmod(0o644)

    @pytest.mark.skipif(os.geteuid() == 0, reason="Root can read unreadable files")
    def test_validate_certificate_files_permission_error_key(self) -> None:
        """Test validation failure when key file is not readable."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "test.crt"
            key_file = Path(temp_dir) / "unreadable.key"

            # Create files
            cert_file.write_text("test certificate")
            key_file.write_text("test key")

            # Make key file unreadable
            key_file.chmod(0o000)

            try:
                with pytest.raises(
                    CertificateLoadError, match="Cannot read private key file"
                ):
                    validate_certificate_files(str(cert_file), str(key_file))
            finally:
                # Restore permissions for cleanup
                key_file.chmod(0o644)


class TestCertificateLoading:
    """Test certificate loading functions."""

    def test_load_certificate_credentials_success(self) -> None:
        """Test successful loading of certificate credentials."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "test.crt"
            key_file = Path(temp_dir) / "test.key"

            # Create test files with known content
            cert_content = b"test certificate data"
            key_content = b"test key data"
            cert_file.write_bytes(cert_content)
            key_file.write_bytes(key_content)

            cert_bytes, key_bytes = load_certificate_credentials(
                str(cert_file), str(key_file)
            )

            assert cert_bytes == cert_content
            assert key_bytes == key_content

    def test_load_certificate_credentials_missing_files(self) -> None:
        """Test loading failure when files are missing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "missing.crt"
            key_file = Path(temp_dir) / "missing.key"

            with pytest.raises(
                CertificateLoadError, match="Certificate file not found"
            ):
                load_certificate_credentials(str(cert_file), str(key_file))

    def test_load_certificate_credentials_read_error(self) -> None:
        """Test loading failure when files cannot be read."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "test.crt"
            key_file = Path(temp_dir) / "test.key"

            # Create files
            cert_file.write_text("test certificate")
            key_file.write_text("test key")

            # Mock open to raise an exception
            with (
                patch("builtins.open", side_effect=OSError("Mock read error")),
                pytest.raises(
                    CertificateLoadError, match="Failed to load certificate files"
                ),
            ):
                load_certificate_credentials(str(cert_file), str(key_file))


class TestSelfSignedCertificateGeneration:
    """Test self-signed certificate generation."""

    def test_generate_self_signed_certificate_success(self) -> None:
        """Test successful generation of self-signed certificate."""
        cert_bytes, key_bytes = generate_self_signed_certificate()

        # Should return PEM-encoded bytes
        assert cert_bytes.startswith(b"-----BEGIN CERTIFICATE-----")
        assert cert_bytes.endswith(b"-----END CERTIFICATE-----\n")
        assert key_bytes.startswith(b"-----BEGIN PRIVATE KEY-----")
        assert key_bytes.endswith(b"-----END PRIVATE KEY-----\n")

    def test_generate_self_signed_certificate_with_files(self) -> None:
        """Test generation with file output."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "test.crt"
            key_file = Path(temp_dir) / "test.key"

            cert_bytes, key_bytes = generate_self_signed_certificate(
                cert_file=str(cert_file), key_file=str(key_file)
            )

            # Files should be created
            assert cert_file.exists()
            assert key_file.exists()

            # File contents should match returned bytes
            assert cert_file.read_bytes() == cert_bytes
            assert key_file.read_bytes() == key_bytes

            # Check file permissions
            cert_stat = cert_file.stat()
            key_stat = key_file.stat()
            assert oct(cert_stat.st_mode)[-3:] == "644"
            assert oct(key_stat.st_mode)[-3:] == "600"

    def test_generate_self_signed_certificate_custom_validity(self) -> None:
        """Test generation with custom validity period."""
        cert_bytes, _ = generate_self_signed_certificate(days_valid=30)

        # Parse certificate to check validity
        cert = x509.load_pem_x509_certificate(cert_bytes)
        validity_period = cert.not_valid_after_utc - cert.not_valid_before_utc
        assert validity_period.days == 30

    def test_generate_self_signed_certificate_file_write_error(self) -> None:
        """Test handling of file write errors."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a read-only directory
            readonly_dir = Path(temp_dir) / "readonly"
            readonly_dir.mkdir()
            readonly_dir.chmod(0o444)

            cert_file = readonly_dir / "test.crt"

            try:
                with pytest.raises(
                    CertificateGenerationError,
                    match="Failed to generate self-signed certificate",
                ):
                    generate_self_signed_certificate(cert_file=str(cert_file))
            finally:
                # Restore permissions for cleanup
                readonly_dir.chmod(0o755)

    def test_generate_self_signed_certificate_with_additional_sans_dns(self) -> None:
        """Test certificate generation with additional DNS SANs."""
        additional_sans = ["api.example.com", "www.example.com", "example.com"]

        cert_bytes, _ = generate_self_signed_certificate(
            hostname="localhost", additional_sans=additional_sans
        )

        # Parse certificate to verify SANs
        cert = x509.load_pem_x509_certificate(cert_bytes)
        san_extension = cert.extensions.get_extension_for_oid(
            x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
        san_values = cast(x509.SubjectAlternativeName, san_extension.value)

        # Extract DNS names from SANs
        dns_names = [str(dns) for dns in san_values.get_values_for_type(x509.DNSName)]

        # Should include default values plus additional SANs
        expected_dns_names = ["localhost", *additional_sans]
        for expected_dns in expected_dns_names:
            assert expected_dns in dns_names

    def test_generate_self_signed_certificate_with_additional_sans_ip(self) -> None:
        """Test certificate generation with additional IP SANs."""
        additional_sans = ["192.168.1.100", "10.0.0.50"]

        cert_bytes, _ = generate_self_signed_certificate(
            hostname="localhost", additional_sans=additional_sans
        )

        # Parse certificate to verify IP SANs
        cert = x509.load_pem_x509_certificate(cert_bytes)
        san_extension = cert.extensions.get_extension_for_oid(
            x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
        san_values = cast(x509.SubjectAlternativeName, san_extension.value)

        # Extract IP addresses from SANs
        ip_addresses = [
            str(ip) for ip in san_values.get_values_for_type(x509.IPAddress)
        ]

        # Should include default IPs plus additional IPs
        expected_ips = ["127.0.0.1", "::1", *additional_sans]
        for expected_ip in expected_ips:
            assert expected_ip in ip_addresses

    def test_generate_self_signed_certificate_with_mixed_sans(self) -> None:
        """Test certificate generation with mixed DNS and IP SANs."""
        additional_sans = [
            "example.com",
            "192.168.1.100",
            "api.example.com",
            "10.0.0.50",
        ]

        cert_bytes, _ = generate_self_signed_certificate(
            hostname="localhost", additional_sans=additional_sans
        )

        # Parse certificate to verify mixed SANs
        cert = x509.load_pem_x509_certificate(cert_bytes)
        san_extension = cert.extensions.get_extension_for_oid(
            x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
        san_values = cast(x509.SubjectAlternativeName, san_extension.value)

        # Extract DNS names and IP addresses from SANs
        dns_names = [str(dns) for dns in san_values.get_values_for_type(x509.DNSName)]
        ip_addresses = [
            str(ip) for ip in san_values.get_values_for_type(x509.IPAddress)
        ]

        # Verify DNS names
        assert "localhost" in dns_names
        assert "example.com" in dns_names
        assert "api.example.com" in dns_names

        # Verify IP addresses
        assert "127.0.0.1" in ip_addresses
        assert "::1" in ip_addresses
        assert "192.168.1.100" in ip_addresses
        assert "10.0.0.50" in ip_addresses

    def test_generate_self_signed_certificate_duplicate_sans_handling(self) -> None:
        """Test that duplicate SANs are properly handled."""
        # Include duplicates of default values and additional duplicates
        additional_sans = ["localhost", "127.0.0.1", "example.com", "example.com"]

        cert_bytes, _ = generate_self_signed_certificate(
            hostname="localhost", additional_sans=additional_sans
        )

        # Parse certificate to verify no duplicates
        cert = x509.load_pem_x509_certificate(cert_bytes)
        san_extension = cert.extensions.get_extension_for_oid(
            x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
        san_values = cast(x509.SubjectAlternativeName, san_extension.value)

        # Extract all SANs
        dns_names = [str(dns) for dns in san_values.get_values_for_type(x509.DNSName)]
        ip_addresses = [
            str(ip) for ip in san_values.get_values_for_type(x509.IPAddress)
        ]

        # Check that localhost appears only once
        assert dns_names.count("localhost") == 1

        # Check that 127.0.0.1 appears only once
        assert ip_addresses.count("127.0.0.1") == 1

        # Check that example.com appears only once
        assert dns_names.count("example.com") == 1

    def test_generate_self_signed_certificate_empty_additional_sans(self) -> None:
        """Test certificate generation with empty additional SANs list."""
        cert_bytes, _ = generate_self_signed_certificate(
            hostname="test.example.com", additional_sans=[]
        )

        # Parse certificate to verify only default SANs
        cert = x509.load_pem_x509_certificate(cert_bytes)
        san_extension = cert.extensions.get_extension_for_oid(
            x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
        san_values = cast(x509.SubjectAlternativeName, san_extension.value)

        # Extract DNS names and IP addresses from SANs
        dns_names = [str(dns) for dns in san_values.get_values_for_type(x509.DNSName)]
        ip_addresses = [
            str(ip) for ip in san_values.get_values_for_type(x509.IPAddress)
        ]

        # Should only have default values
        assert "test.example.com" in dns_names
        assert "localhost" in dns_names
        assert "127.0.0.1" in ip_addresses
        assert "::1" in ip_addresses

        # Should not have any additional SANs
        assert len(dns_names) == 2  # hostname + localhost
        assert len(ip_addresses) == 2  # 127.0.0.1 + ::1

    def test_generate_self_signed_certificate_none_additional_sans(self) -> None:
        """Test certificate generation with None additional SANs."""
        cert_bytes, _ = generate_self_signed_certificate(
            hostname="test.example.com", additional_sans=None
        )

        # Parse certificate to verify only default SANs
        cert = x509.load_pem_x509_certificate(cert_bytes)
        san_extension = cert.extensions.get_extension_for_oid(
            x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
        san_values = cast(x509.SubjectAlternativeName, san_extension.value)

        # Extract DNS names and IP addresses from SANs
        dns_names = [str(dns) for dns in san_values.get_values_for_type(x509.DNSName)]
        ip_addresses = [
            str(ip) for ip in san_values.get_values_for_type(x509.IPAddress)
        ]

        # Should only have default values
        assert "test.example.com" in dns_names
        assert "localhost" in dns_names
        assert "127.0.0.1" in ip_addresses
        assert "::1" in ip_addresses

        # Should not have any additional SANs
        assert len(dns_names) == 2  # hostname + localhost
        assert len(ip_addresses) == 2  # 127.0.0.1 + ::1

    def test_generate_self_signed_certificate_ipv6_additional_sans(self) -> None:
        """Test certificate generation with IPv6 additional SANs."""
        additional_sans = ["2001:db8::1", "::1"]  # Include a duplicate IPv6

        cert_bytes, _ = generate_self_signed_certificate(
            hostname="localhost", additional_sans=additional_sans
        )

        # Parse certificate to verify IPv6 SANs
        cert = x509.load_pem_x509_certificate(cert_bytes)
        san_extension = cert.extensions.get_extension_for_oid(
            x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
        san_values = cast(x509.SubjectAlternativeName, san_extension.value)

        # Extract IP addresses from SANs
        ip_addresses = [
            str(ip) for ip in san_values.get_values_for_type(x509.IPAddress)
        ]

        # Should include default IPs plus new IPv6
        assert "127.0.0.1" in ip_addresses
        assert "::1" in ip_addresses
        assert "2001:db8::1" in ip_addresses

        # Check that ::1 appears only once (duplicate handling)
        assert ip_addresses.count("::1") == 1

    def test_generate_self_signed_certificate_invalid_ip_as_dns(self) -> None:
        """Test that invalid IP addresses are treated as DNS names."""
        # This is actually a valid behavior - treat malformed IPs as DNS names
        additional_sans = ["256.256.256.256", "not.an.ip.address"]

        cert_bytes, _ = generate_self_signed_certificate(
            hostname="localhost", additional_sans=additional_sans
        )

        # Parse certificate to verify they're treated as DNS names
        cert = x509.load_pem_x509_certificate(cert_bytes)
        san_extension = cert.extensions.get_extension_for_oid(
            x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
        san_values = cast(x509.SubjectAlternativeName, san_extension.value)

        # Extract DNS names from SANs
        dns_names = [str(dns) for dns in san_values.get_values_for_type(x509.DNSName)]

        # Invalid IP should be treated as DNS name
        assert "256.256.256.256" in dns_names
        assert "not.an.ip.address" in dns_names


class TestDefaultCertPaths:
    """Test default certificate path utilities."""

    def test_get_default_cert_paths(self) -> None:
        """Test getting default certificate paths."""
        config_dir = Path("/test/config")
        cert_file, key_file = get_default_cert_paths(config_dir)

        assert cert_file == "/test/config/certs/server.crt"
        assert key_file == "/test/config/certs/server.key"

    def test_get_default_cert_paths_with_pathlib(self) -> None:
        """Test default paths work with Path objects."""
        config_dir = Path("/test/config")
        cert_file, key_file = get_default_cert_paths(config_dir)

        cert_path = Path(cert_file)
        key_path = Path(key_file)

        assert cert_path.parent.name == "certs"
        assert cert_path.name == "server.crt"
        assert key_path.parent.name == "certs"
        assert key_path.name == "server.key"


class TestEnsureCertificateExists:
    """Test certificate existence ensuring functionality."""

    def test_ensure_certificate_exists_creates_new(self) -> None:
        """Test creating new certificates when they don't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "server.crt"
            key_file = Path(temp_dir) / "server.key"

            # Certificates don't exist yet
            assert not cert_file.exists()
            assert not key_file.exists()

            ensure_certificate_exists(str(cert_file), str(key_file))

            # Certificates should now exist
            assert cert_file.exists()
            assert key_file.exists()

            # Should contain valid PEM data
            cert_content = cert_file.read_text()
            key_content = key_file.read_text()
            assert "-----BEGIN CERTIFICATE-----" in cert_content
            assert "-----BEGIN PRIVATE KEY-----" in key_content

    def test_ensure_certificate_exists_preserves_existing(self) -> None:
        """Test preserving existing certificates."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "server.crt"
            key_file = Path(temp_dir) / "server.key"

            # Create existing certificates with known content
            original_cert = "existing certificate"
            original_key = "existing key"
            cert_file.write_text(original_cert)
            key_file.write_text(original_key)

            ensure_certificate_exists(str(cert_file), str(key_file))

            # Content should be unchanged
            assert cert_file.read_text() == original_cert
            assert key_file.read_text() == original_key

    def test_ensure_certificate_exists_regenerate_flag(self) -> None:
        """Test regenerating certificates with force flag."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "server.crt"
            key_file = Path(temp_dir) / "server.key"

            # Create existing certificates
            original_cert = "existing certificate"
            original_key = "existing key"
            cert_file.write_text(original_cert)
            key_file.write_text(original_key)

            # Force regeneration
            ensure_certificate_exists(str(cert_file), str(key_file), regenerate=True)

            # Content should be changed to valid PEM
            new_cert_content = cert_file.read_text()
            new_key_content = key_file.read_text()

            assert new_cert_content != original_cert
            assert new_key_content != original_key
            assert "-----BEGIN CERTIFICATE-----" in new_cert_content
            assert "-----BEGIN PRIVATE KEY-----" in new_key_content

    def test_ensure_certificate_exists_creates_directory(self) -> None:
        """Test creating certificate directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Use a nested directory that doesn't exist
            cert_dir = Path(temp_dir) / "certs" / "nested"
            cert_file = cert_dir / "server.crt"
            key_file = cert_dir / "server.key"

            # Directory doesn't exist yet
            assert not cert_dir.exists()

            ensure_certificate_exists(str(cert_file), str(key_file))

            # Directory and certificates should be created
            assert cert_dir.exists()
            assert cert_file.exists()
            assert key_file.exists()

    def test_ensure_certificate_exists_custom_validity(self) -> None:
        """Test certificate generation with custom validity period."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "server.crt"
            key_file = Path(temp_dir) / "server.key"

            ensure_certificate_exists(str(cert_file), str(key_file), days_valid=30)

            # Parse certificate to check validity
            cert_content = cert_file.read_bytes()
            cert = x509.load_pem_x509_certificate(cert_content)
            validity_period = cert.not_valid_after_utc - cert.not_valid_before_utc
            assert validity_period.days == 30


class TestCertificateExceptions:
    """Test certificate-related exceptions."""

    def test_certificate_error_inheritance(self) -> None:
        """Test CertificateError inheritance."""
        error = CertificateError("test error")
        assert isinstance(error, Exception)
        assert str(error) == "test error"

    def test_certificate_generation_error_inheritance(self) -> None:
        """Test CertificateGenerationError inheritance."""
        error = CertificateGenerationError("generation failed")
        assert isinstance(error, CertificateError)
        assert isinstance(error, Exception)
        assert str(error) == "generation failed"

    def test_certificate_load_error_inheritance(self) -> None:
        """Test CertificateLoadError inheritance."""
        error = CertificateLoadError("load failed")
        assert isinstance(error, CertificateError)
        assert isinstance(error, Exception)
        assert str(error) == "load failed"


class TestIntegration:
    """Test integration scenarios."""

    def test_full_certificate_workflow(self) -> None:
        """Test complete certificate workflow."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            cert_file, key_file = get_default_cert_paths(config_dir)

            # Initially no certificates
            cert_path = Path(cert_file)
            key_path = Path(key_file)
            assert not cert_path.exists()
            assert not key_path.exists()

            # Generate certificates
            ensure_certificate_exists(cert_file, key_file, hostname="test.local")

            # Certificates should exist
            assert cert_path.exists()
            assert key_path.exists()

            # Should be able to load them
            cert_bytes, key_bytes = load_certificate_credentials(cert_file, key_file)
            assert len(cert_bytes) > 0
            assert len(key_bytes) > 0

            # Should be valid PEM format
            assert cert_bytes.startswith(b"-----BEGIN CERTIFICATE-----")
            assert key_bytes.startswith(b"-----BEGIN PRIVATE KEY-----")


class TestHandleCertificateGenerationForServer:
    """Test server certificate generation handler."""

    def test_handle_certificate_generation_with_files(self) -> None:
        """Test handling certificate generation with explicit file paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = str(Path(temp_dir) / "test.crt")
            key_file = str(Path(temp_dir) / "test.key")

            server_config = {
                "tls": {"cert_file": cert_file, "key_file": key_file},
                "server": {"host": "example.com"},
            }

            result_cert, result_key = handle_certificate_generation_for_server(
                server_config
            )

            assert result_cert == cert_file
            assert result_key == key_file
            assert Path(cert_file).exists()
            assert Path(key_file).exists()

    @patch("vibectl.server.cert_utils.get_default_cert_paths")
    @patch("vibectl.config_utils.get_config_dir")
    def test_handle_certificate_generation_default_paths(
        self, mock_get_config_dir: Mock, mock_get_default_paths: Mock
    ) -> None:
        """Test handling certificate generation with default paths."""
        # Setup mocks
        mock_config_dir = Path("/test/config")
        mock_get_config_dir.return_value = mock_config_dir

        with tempfile.TemporaryDirectory() as temp_dir:
            default_cert = str(Path(temp_dir) / "default.crt")
            default_key = str(Path(temp_dir) / "default.key")
            mock_get_default_paths.return_value = (default_cert, default_key)

            server_config = {"server": {"host": "0.0.0.0"}}

            result_cert, result_key = handle_certificate_generation_for_server(
                server_config
            )

            assert result_cert == default_cert
            assert result_key == default_key
            mock_get_config_dir.assert_called_once_with("server")
            mock_get_default_paths.assert_called_once_with(mock_config_dir)


class TestCreateCertificateSigningRequest:
    """Test Certificate Signing Request creation."""

    def test_create_csr_single_domain(self) -> None:
        """Test creating CSR for a single domain."""
        from cryptography.hazmat.primitives.asymmetric import rsa

        # Generate a test key
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        domains = ["example.com"]
        csr = create_certificate_signing_request(domains, private_key)

        # Check that CSR was created
        assert isinstance(csr, x509.CertificateSigningRequest)

        # Verify the subject
        subject_cn = None
        for attribute in csr.subject:
            if attribute.oid == x509.NameOID.COMMON_NAME:
                subject_cn = attribute.value
                break

        assert subject_cn == "example.com"

        # Verify SAN extension
        san_extension = None
        for ext in csr.extensions:
            if ext.oid == x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME:
                san_extension = ext
                break

        assert san_extension is not None
        san_dns_names = [
            str(dns) for dns in san_extension.value.get_values_for_type(x509.DNSName)
        ]
        assert "example.com" in san_dns_names

    def test_create_csr_multiple_domains(self) -> None:
        """Test creating CSR for multiple domains."""
        from cryptography.hazmat.primitives.asymmetric import rsa

        # Generate a test key
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        domains = ["example.com", "www.example.com", "api.example.com"]
        csr = create_certificate_signing_request(domains, private_key)

        # Verify the subject (should use first domain)
        subject_cn = None
        for attribute in csr.subject:
            if attribute.oid == x509.NameOID.COMMON_NAME:
                subject_cn = attribute.value
                break

        assert subject_cn == "example.com"

        # Verify all domains are in SAN
        san_extension = None
        for ext in csr.extensions:
            if ext.oid == x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME:
                san_extension = ext
                break

        assert san_extension is not None
        san_dns_names = [
            str(dns) for dns in san_extension.value.get_values_for_type(x509.DNSName)
        ]

        for domain in domains:
            assert domain in san_dns_names

    def test_create_csr_with_organization(self) -> None:
        """Test creating CSR with organization information."""
        from cryptography.hazmat.primitives.asymmetric import rsa

        # Generate a test key
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        domains = ["example.com"]
        organization = "Test Organization"
        country = "US"

        csr = create_certificate_signing_request(
            domains, private_key, organization=organization, country=country
        )

        # Verify organization and country in subject
        subject_org = None
        subject_country = None
        for attribute in csr.subject:
            if attribute.oid == x509.NameOID.ORGANIZATION_NAME:
                subject_org = attribute.value
            elif attribute.oid == x509.NameOID.COUNTRY_NAME:
                subject_country = attribute.value

        assert subject_org == organization
        assert subject_country == country

    def test_create_csr_invalid_key(self) -> None:
        """Test creating CSR with invalid key type."""
        # Mock an invalid key type
        invalid_key = Mock()

        domains = ["example.com"]

        with pytest.raises(CertificateGenerationError, match="Failed to create CSR"):
            create_certificate_signing_request(domains, invalid_key)
