"""
Tests for certificate utilities.

Tests cover certificate validation, loading, generation, and utility functions
for TLS support in the vibectl LLM proxy server.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from vibectl.server.cert_utils import (
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
        cert_bytes, key_bytes = generate_self_signed_certificate(hostname="test.local")

        assert isinstance(cert_bytes, bytes)
        assert isinstance(key_bytes, bytes)
        assert b"BEGIN CERTIFICATE" in cert_bytes
        assert b"BEGIN PRIVATE KEY" in key_bytes

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

    def test_generate_self_signed_certificate_custom_validity(self) -> None:
        """Test certificate generation with custom validity period."""
        cert_bytes, key_bytes = generate_self_signed_certificate(
            hostname="test.local", days_valid=90
        )

        assert isinstance(cert_bytes, bytes)
        assert isinstance(key_bytes, bytes)

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

    def test_ensure_certificate_exists_creates_directory(self) -> None:
        """Test that ensure_certificate_exists creates parent directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_dir = Path(temp_dir) / "certs"
            cert_file = cert_dir / "test.crt"
            key_file = cert_dir / "test.key"

            # Directory should not exist initially
            assert not cert_dir.exists()

            ensure_certificate_exists(
                str(cert_file),
                str(key_file),
                hostname="test.local",
            )

            # Directory and files should be created
            assert cert_dir.exists()
            assert cert_file.exists()
            assert key_file.exists()

    def test_ensure_certificate_exists_custom_validity(self) -> None:
        """Test certificate generation with custom validity period."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "test.crt"
            key_file = Path(temp_dir) / "test.key"

            ensure_certificate_exists(
                str(cert_file),
                str(key_file),
                hostname="test.local",
                days_valid=180,
            )

            assert cert_file.exists()
            assert key_file.exists()


class TestCertificateExceptions:
    """Test certificate-related exception classes."""

    def test_certificate_error_inheritance(self) -> None:
        """Test that CertificateError inherits from Exception."""
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
    """Test integration scenarios with certificate utilities."""

    def test_full_certificate_workflow(self) -> None:
        """Test complete workflow: generate, save, and load certificates."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = Path(temp_dir) / "workflow.crt"
            key_file = Path(temp_dir) / "workflow.key"

            # Step 1: Generate and save certificate
            original_cert, original_key = generate_self_signed_certificate(
                hostname="workflow.local",
                cert_file=str(cert_file),
                key_file=str(key_file),
            )

            # Step 2: Verify files exist
            assert cert_file.exists()
            assert key_file.exists()

            # Step 3: Load certificates back
            loaded_cert, loaded_key = load_certificate_credentials(
                str(cert_file), str(key_file)
            )

            # Step 4: Verify loaded data matches generated data
            assert loaded_cert == original_cert
            assert loaded_key == original_key

            # Step 5: Verify certificate structure
            assert b"BEGIN CERTIFICATE" in loaded_cert
            assert b"BEGIN PRIVATE KEY" in loaded_key


class TestHandleCertificateGenerationForServer:
    """Test certificate generation handling for server configurations."""

    def test_handle_certificate_generation_with_files(self) -> None:
        """Test certificate generation when files are specified in config."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = str(Path(temp_dir) / "server.crt")
            key_file = str(Path(temp_dir) / "server.key")

            server_config: dict[str, dict[str, str]] = {
                "tls": {
                    "cert_file": cert_file,
                    "key_file": key_file,
                }
            }

            result_cert, result_key = handle_certificate_generation_for_server(
                server_config, hostname_override="test.local"
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
        """Test certificate generation using default paths."""
        # Mock dependencies
        mock_config_dir = Path("/mock/config")
        mock_get_config_dir.return_value = mock_config_dir

        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = str(Path(temp_dir) / "default.crt")
            key_file = str(Path(temp_dir) / "default.key")
            mock_get_default_paths.return_value = (cert_file, key_file)

            server_config: dict[str, str] = {}  # No cert/key files specified

            result_cert, result_key = handle_certificate_generation_for_server(
                server_config
            )

            assert result_cert == cert_file
            assert result_key == key_file
            mock_get_config_dir.assert_called_once()
            mock_get_default_paths.assert_called_once_with(mock_config_dir)
