"""
Tests for the certificate utilities module.

Tests cover certificate generation, validation, loading, and error handling
for the TLS support in the vibectl LLM proxy server.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from vibectl.server.cert_utils import (
    CertificateError,
    CertificateGenerationError,
    CertificateLoadError,
    ensure_certificate_exists,
    generate_self_signed_certificate,
    get_default_cert_paths,
    is_cryptography_available,
    load_certificate_credentials,
    validate_certificate_files,
)


class TestCryptographyAvailability:
    """Test cryptography library availability detection."""

    def test_is_cryptography_available_returns_bool(self) -> None:
        """Test that is_cryptography_available returns a boolean."""
        result = is_cryptography_available()
        assert isinstance(result, bool)

    @patch("vibectl.server.cert_utils.CRYPTOGRAPHY_AVAILABLE", True)
    def test_is_cryptography_available_true(self) -> None:
        """Test when cryptography is available."""
        result = is_cryptography_available()
        assert result is True

    @patch("vibectl.server.cert_utils.CRYPTOGRAPHY_AVAILABLE", False)
    def test_is_cryptography_available_false(self) -> None:
        """Test when cryptography is not available."""
        result = is_cryptography_available()
        assert result is False


class TestCertificateValidation:
    """Test certificate file validation."""

    def test_validate_certificate_files_success(self) -> None:
        """Test successful validation of existing certificate files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "test.crt"
            key_file = Path(temp_dir) / "test.key"

            # Create test files
            cert_file.write_text("test certificate")
            key_file.write_text("test key")

            # Should not raise any exception
            validate_certificate_files(str(cert_file), str(key_file))

    def test_validate_certificate_files_missing_cert(self) -> None:
        """Test validation fails when certificate file is missing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "missing.crt"
            key_file = Path(temp_dir) / "test.key"
            key_file.write_text("test key")

            with pytest.raises(
                CertificateLoadError,
                match="Certificate file not found",
            ):
                validate_certificate_files(str(cert_file), str(key_file))

    def test_validate_certificate_files_missing_key(self) -> None:
        """Test validation fails when key file is missing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "test.crt"
            key_file = Path(temp_dir) / "missing.key"
            cert_file.write_text("test certificate")

            with pytest.raises(
                CertificateLoadError,
                match="Private key file not found",
            ):
                validate_certificate_files(str(cert_file), str(key_file))

    def test_validate_certificate_files_cert_is_directory(self) -> None:
        """Test validation fails when certificate path is a directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_dir = Path(temp_dir) / "cert_dir"
            key_file = Path(temp_dir) / "test.key"
            cert_dir.mkdir()
            key_file.write_text("test key")

            with pytest.raises(
                CertificateLoadError,
                match="Certificate path is not a file",
            ):
                validate_certificate_files(str(cert_dir), str(key_file))

    def test_validate_certificate_files_key_is_directory(self) -> None:
        """Test validation fails when key path is a directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "test.crt"
            key_dir = Path(temp_dir) / "key_dir"
            cert_file.write_text("test certificate")
            key_dir.mkdir()

            with pytest.raises(
                CertificateLoadError,
                match="Private key path is not a file",
            ):
                validate_certificate_files(str(cert_file), str(key_dir))

    @pytest.mark.skipif(os.geteuid() == 0, reason="Root can read unreadable files")
    def test_validate_certificate_files_permission_error_cert(self) -> None:
        """Test validation fails when certificate file is not readable."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "test.crt"
            key_file = Path(temp_dir) / "test.key"
            cert_file.write_text("test certificate")
            key_file.write_text("test key")

            # Make certificate file unreadable
            cert_file.chmod(0o000)

            try:
                with pytest.raises(
                    CertificateLoadError,
                    match="Cannot read certificate file",
                ):
                    validate_certificate_files(str(cert_file), str(key_file))
            finally:
                # Restore permissions for cleanup
                cert_file.chmod(0o644)

    @pytest.mark.skipif(os.geteuid() == 0, reason="Root can read unreadable files")
    def test_validate_certificate_files_permission_error_key(self) -> None:
        """Test validation fails when key file is not readable."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "test.crt"
            key_file = Path(temp_dir) / "test.key"
            cert_file.write_text("test certificate")
            key_file.write_text("test key")

            # Make key file unreadable
            key_file.chmod(0o000)

            try:
                with pytest.raises(
                    CertificateLoadError,
                    match="Cannot read private key file",
                ):
                    validate_certificate_files(str(cert_file), str(key_file))
            finally:
                # Restore permissions for cleanup
                key_file.chmod(0o644)


class TestCertificateLoading:
    """Test certificate loading functionality."""

    def test_load_certificate_credentials_success(self) -> None:
        """Test successful loading of certificate credentials."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "test.crt"
            key_file = Path(temp_dir) / "test.key"

            cert_content = b"test certificate content"
            key_content = b"test key content"

            cert_file.write_bytes(cert_content)
            key_file.write_bytes(key_content)

            cert_data, key_data = load_certificate_credentials(
                str(cert_file),
                str(key_file),
            )

            assert cert_data == cert_content
            assert key_data == key_content

    def test_load_certificate_credentials_missing_files(self) -> None:
        """Test loading fails when files are missing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "missing.crt"
            key_file = Path(temp_dir) / "missing.key"

            with pytest.raises(
                CertificateLoadError,
                match="Certificate file not found",
            ):
                load_certificate_credentials(str(cert_file), str(key_file))

    def test_load_certificate_credentials_read_error(self) -> None:
        """Test loading handles file read errors."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "test.crt"
            key_file = Path(temp_dir) / "test.key"

            cert_file.write_text("test certificate")
            key_file.write_text("test key")

            # Mock file reading to raise an exception
            with (
                patch("builtins.open", side_effect=OSError("Read error")),
                pytest.raises(
                    CertificateLoadError,
                    match="Failed to load certificate files",
                ),
            ):
                load_certificate_credentials(str(cert_file), str(key_file))


class TestSelfSignedCertificateGeneration:
    """Test self-signed certificate generation."""

    @pytest.mark.skipif(
        not is_cryptography_available(),
        reason="cryptography not available",
    )
    def test_generate_self_signed_certificate_success(self) -> None:
        """Test successful generation of self-signed certificate."""
        cert_bytes, key_bytes = generate_self_signed_certificate(hostname="test.local")

        assert isinstance(cert_bytes, bytes)
        assert isinstance(key_bytes, bytes)
        assert b"BEGIN CERTIFICATE" in cert_bytes
        assert b"BEGIN PRIVATE KEY" in key_bytes

    @pytest.mark.skipif(
        not is_cryptography_available(),
        reason="cryptography not available",
    )
    def test_generate_self_signed_certificate_with_files(self) -> None:
        """Test certificate generation with file output."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "test.crt"
            key_file = Path(temp_dir) / "test.key"

            cert_bytes, key_bytes = generate_self_signed_certificate(
                hostname="test.local",
                cert_file=str(cert_file),
                key_file=str(key_file),
                days_valid=30,
            )

            # Check return values
            assert isinstance(cert_bytes, bytes)
            assert isinstance(key_bytes, bytes)

            # Check files were created
            assert cert_file.exists()
            assert key_file.exists()

            # Check file contents match return values
            assert cert_file.read_bytes() == cert_bytes
            assert key_file.read_bytes() == key_bytes

    @pytest.mark.skipif(
        not is_cryptography_available(),
        reason="cryptography not available",
    )
    def test_generate_self_signed_certificate_custom_validity(self) -> None:
        """Test certificate generation with custom validity period."""
        cert_bytes, key_bytes = generate_self_signed_certificate(
            hostname="test.local", days_valid=90
        )

        assert isinstance(cert_bytes, bytes)
        assert isinstance(key_bytes, bytes)

    @patch("vibectl.server.cert_utils.CRYPTOGRAPHY_AVAILABLE", False)
    def test_generate_self_signed_certificate_no_cryptography(self) -> None:
        """Test certificate generation fails when cryptography is not available."""
        with pytest.raises(
            CertificateGenerationError,
            match="requires the 'cryptography' package",
        ):
            generate_self_signed_certificate()

    @pytest.mark.skipif(
        not is_cryptography_available(),
        reason="cryptography not available",
    )
    def test_generate_self_signed_certificate_file_write_error(self) -> None:
        """Test certificate generation handles file write errors."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a directory where we expect a file
            cert_file = Path(temp_dir) / "subdir"
            cert_file.mkdir()
            key_file = Path(temp_dir) / "test.key"

            with pytest.raises(
                CertificateGenerationError,
                match="Failed to generate self-signed certificate",
            ):
                generate_self_signed_certificate(
                    hostname="test.local",
                    cert_file=str(cert_file),
                    key_file=str(key_file),
                )


class TestDefaultCertPaths:
    """Test default certificate path generation."""

    def test_get_default_cert_paths(self) -> None:
        """Test generation of default certificate paths."""
        config_dir = Path("/test/config")
        cert_file, key_file = get_default_cert_paths(config_dir)

        assert cert_file == str(config_dir / "certs" / "server.crt")
        assert key_file == str(config_dir / "certs" / "server.key")

    def test_get_default_cert_paths_with_pathlib(self) -> None:
        """Test default paths work with Path objects."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            cert_file, key_file = get_default_cert_paths(config_dir)

            expected_cert = config_dir / "certs" / "server.crt"
            expected_key = config_dir / "certs" / "server.key"

            assert cert_file == str(expected_cert)
            assert key_file == str(expected_key)


class TestEnsureCertificateExists:
    """Test certificate existence and auto-generation."""

    @pytest.mark.skipif(
        not is_cryptography_available(),
        reason="cryptography not available",
    )
    def test_ensure_certificate_exists_creates_new(self) -> None:
        """Test that ensure_certificate_exists creates new certificates when missing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "test.crt"
            key_file = Path(temp_dir) / "test.key"

            ensure_certificate_exists(
                str(cert_file),
                str(key_file),
                hostname="test.local",
            )

            assert cert_file.exists()
            assert key_file.exists()
            assert b"BEGIN CERTIFICATE" in cert_file.read_bytes()
            assert b"BEGIN PRIVATE KEY" in key_file.read_bytes()

    @pytest.mark.skipif(
        not is_cryptography_available(),
        reason="cryptography not available",
    )
    def test_ensure_certificate_exists_preserves_existing(self) -> None:
        """Test that existing certificates are preserved."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "test.crt"
            key_file = Path(temp_dir) / "test.key"

            # Create existing files
            original_cert = b"existing certificate"
            original_key = b"existing key"
            cert_file.write_bytes(original_cert)
            key_file.write_bytes(original_key)

            ensure_certificate_exists(
                str(cert_file),
                str(key_file),
                hostname="test.local",
            )

            # Files should be unchanged
            assert cert_file.read_bytes() == original_cert
            assert key_file.read_bytes() == original_key

    @pytest.mark.skipif(
        not is_cryptography_available(),
        reason="cryptography not available",
    )
    def test_ensure_certificate_exists_regenerate_flag(self) -> None:
        """Test that regenerate flag forces new certificate creation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "test.crt"
            key_file = Path(temp_dir) / "test.key"

            # Create existing files
            original_cert = b"existing certificate"
            original_key = b"existing key"
            cert_file.write_bytes(original_cert)
            key_file.write_bytes(original_key)

            ensure_certificate_exists(
                str(cert_file), str(key_file), hostname="test.local", regenerate=True
            )

            # Files should be replaced with new certificates
            new_cert = cert_file.read_bytes()
            new_key = key_file.read_bytes()

            assert new_cert != original_cert
            assert new_key != original_key
            assert b"BEGIN CERTIFICATE" in new_cert
            assert b"BEGIN PRIVATE KEY" in new_key

    @pytest.mark.skipif(
        not is_cryptography_available(),
        reason="cryptography not available",
    )
    def test_ensure_certificate_exists_creates_directory(self) -> None:
        """Test that ensure_certificate_exists creates parent directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_dir = Path(temp_dir) / "certs" / "subdir"
            cert_file = cert_dir / "test.crt"
            key_file = cert_dir / "test.key"

            ensure_certificate_exists(
                str(cert_file),
                str(key_file),
                hostname="test.local",
            )

            assert cert_dir.exists()
            assert cert_file.exists()
            assert key_file.exists()

    @pytest.mark.skipif(
        not is_cryptography_available(),
        reason="cryptography not available",
    )
    def test_ensure_certificate_exists_custom_validity(self) -> None:
        """Test certificate generation with custom validity period."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "test.crt"
            key_file = Path(temp_dir) / "test.key"

            ensure_certificate_exists(
                str(cert_file), str(key_file), hostname="test.local", days_valid=180
            )

            assert cert_file.exists()
            assert key_file.exists()

    @patch("vibectl.server.cert_utils.CRYPTOGRAPHY_AVAILABLE", False)
    def test_ensure_certificate_exists_no_cryptography(self) -> None:
        """Test ensure_certificate_exists fails gracefully without cryptography."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "test.crt"
            key_file = Path(temp_dir) / "test.key"

            with pytest.raises(
                CertificateGenerationError,
                match="requires the 'cryptography' package",
            ):
                ensure_certificate_exists(str(cert_file), str(key_file))


class TestCertificateExceptions:
    """Test certificate-related exceptions."""

    def test_certificate_error_inheritance(self) -> None:
        """Test that CertificateError is a proper exception."""
        error = CertificateError("test error")
        assert isinstance(error, Exception)
        assert str(error) == "test error"

    def test_certificate_generation_error_inheritance(self) -> None:
        """Test that CertificateGenerationError inherits from CertificateError."""
        error = CertificateGenerationError("generation failed")
        assert isinstance(error, CertificateError)
        assert isinstance(error, Exception)
        assert str(error) == "generation failed"

    def test_certificate_load_error_inheritance(self) -> None:
        """Test that CertificateLoadError inherits from CertificateError."""
        error = CertificateLoadError("load failed")
        assert isinstance(error, CertificateError)
        assert isinstance(error, Exception)
        assert str(error) == "load failed"


class TestIntegration:
    """Integration tests for certificate utilities."""

    @pytest.mark.skipif(
        not is_cryptography_available(),
        reason="cryptography not available",
    )
    def test_full_certificate_workflow(self) -> None:
        """Test complete certificate generation and loading workflow."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "server.crt"
            key_file = Path(temp_dir) / "server.key"

            # Generate certificates
            ensure_certificate_exists(
                str(cert_file),
                str(key_file),
                hostname="localhost",
            )

            # Validate they exist and are readable
            validate_certificate_files(str(cert_file), str(key_file))

            # Load the credentials
            cert_data, key_data = load_certificate_credentials(
                str(cert_file),
                str(key_file),
            )

            # Verify content
            assert isinstance(cert_data, bytes)
            assert isinstance(key_data, bytes)
            assert b"BEGIN CERTIFICATE" in cert_data
            assert b"BEGIN PRIVATE KEY" in key_data

            # Verify files match loaded data
            assert cert_file.read_bytes() == cert_data
            assert key_file.read_bytes() == key_data
