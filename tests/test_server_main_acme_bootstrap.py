"""
Tests for ACME bootstrap certificate functionality in vibectl.server.main.

This module specifically tests the enhanced certificate generation logic
that includes ACME domains in bootstrap certificates for TLS-ALPN-01 challenges.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from typing import cast

import pytest
from cryptography import x509

from vibectl.server.main import _create_grpc_server_with_temp_certs
from vibectl.types import CertificateGenerationError


class TestACMEBootstrapCertificates:
    """Test ACME-aware bootstrap certificate generation."""

    @patch("vibectl.server.grpc_server.GRPCServer")
    @patch("vibectl.server.cert_utils.generate_self_signed_certificate")
    @patch("vibectl.server.cert_utils.get_default_cert_paths")
    @patch("vibectl.config_utils.get_config_dir")
    def test_create_grpc_server_with_acme_domains_tls_alpn(
        self,
        mock_get_config_dir: Mock,
        mock_get_default_paths: Mock,
        mock_generate_cert: Mock,
        mock_grpc_server: Mock,
    ) -> None:
        """Test server creation with ACME domains for TLS-ALPN-01."""
        # Setup mocks
        mock_config_dir = Path("/test/config")
        mock_get_config_dir.return_value = mock_config_dir
        
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = str(Path(temp_dir) / "server.crt")
            key_file = str(Path(temp_dir) / "server.key")
            mock_get_default_paths.return_value = (cert_file, key_file)
            
            mock_generate_cert.return_value = (b"cert_data", b"key_data")
            mock_server_instance = Mock()
            mock_grpc_server.return_value = mock_server_instance
            
            # Server config with ACME enabled for TLS-ALPN-01
            server_config = {
                "server": {"host": "0.0.0.0", "port": 443, "max_workers": 10, "default_model": "test-model"},
                "jwt": {"enabled": False},
                "tls": {"enabled": True},
                "acme": {
                    "enabled": True,
                    "challenge_type": "tls-alpn-01",
                    "domains": ["api.example.com", "www.example.com", "example.com"]
                }
            }
            
            # Call the function
            result = _create_grpc_server_with_temp_certs(server_config)
            
            # Verify generate_self_signed_certificate was called with additional_sans
            mock_generate_cert.assert_called_once_with(
                hostname="api.example.com",  # First domain becomes primary hostname
                cert_file=cert_file,
                key_file=key_file,
                days_valid=365,
                additional_sans=["api.example.com", "www.example.com", "example.com", "localhost", "localhost"]
            )
            
            # Verify GRPCServer was created correctly
            mock_grpc_server.assert_called_once_with(
                host="0.0.0.0",
                port=443,
                default_model="test-model",
                max_workers=10,
                require_auth=False,
                use_tls=True,
                cert_file=cert_file,
                key_file=key_file,
            )
            
            assert result == mock_server_instance

    @patch("vibectl.server.grpc_server.GRPCServer")
    @patch("vibectl.server.cert_utils.ensure_certificate_exists")
    @patch("vibectl.server.cert_utils.get_default_cert_paths")
    @patch("vibectl.config_utils.get_config_dir")
    def test_create_grpc_server_without_acme_uses_ensure_certificate(
        self,
        mock_get_config_dir: Mock,
        mock_get_default_paths: Mock,
        mock_ensure_cert: Mock,
        mock_grpc_server: Mock,
    ) -> None:
        """Test server creation without ACME uses ensure_certificate_exists."""
        # Setup mocks
        mock_config_dir = Path("/test/config")
        mock_get_config_dir.return_value = mock_config_dir
        
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = str(Path(temp_dir) / "server.crt")
            key_file = str(Path(temp_dir) / "server.key")
            mock_get_default_paths.return_value = (cert_file, key_file)
            
            mock_server_instance = Mock()
            mock_grpc_server.return_value = mock_server_instance
            
            # Server config without ACME
            server_config = {
                "server": {"host": "localhost", "port": 50051, "max_workers": 10, "default_model": "test-model"},
                "jwt": {"enabled": False},
                "tls": {"enabled": True},
                "acme": {"enabled": False}
            }
            
            # Call the function
            result = _create_grpc_server_with_temp_certs(server_config)
            
            # Verify ensure_certificate_exists was called instead of generate_self_signed_certificate
            mock_ensure_cert.assert_called_once_with(cert_file, key_file, hostname="localhost")
            
            # Verify GRPCServer was created correctly
            mock_grpc_server.assert_called_once_with(
                host="localhost",
                port=50051,
                default_model="test-model",
                max_workers=10,
                require_auth=False,
                use_tls=True,
                cert_file=cert_file,
                key_file=key_file,
            )
            
            assert result == mock_server_instance

    @patch("vibectl.server.grpc_server.GRPCServer")
    @patch("vibectl.server.cert_utils.ensure_certificate_exists")
    @patch("vibectl.server.cert_utils.get_default_cert_paths")
    @patch("vibectl.config_utils.get_config_dir")
    def test_create_grpc_server_acme_http01_uses_ensure_certificate(
        self,
        mock_get_config_dir: Mock,
        mock_get_default_paths: Mock,
        mock_ensure_cert: Mock,
        mock_grpc_server: Mock,
    ) -> None:
        """Test server creation with ACME HTTP-01 uses standard certificate generation."""
        # Setup mocks
        mock_config_dir = Path("/test/config")
        mock_get_config_dir.return_value = mock_config_dir
        
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = str(Path(temp_dir) / "server.crt")
            key_file = str(Path(temp_dir) / "server.key")
            mock_get_default_paths.return_value = (cert_file, key_file)
            
            mock_server_instance = Mock()
            mock_grpc_server.return_value = mock_server_instance
            
            # Server config with ACME HTTP-01 (not TLS-ALPN-01)
            server_config = {
                "server": {"host": "0.0.0.0", "port": 50051, "max_workers": 10, "default_model": "test-model"},
                "jwt": {"enabled": False},
                "tls": {"enabled": True},
                "acme": {
                    "enabled": True,
                    "challenge_type": "http-01",
                    "domains": ["api.example.com", "www.example.com"]
                }
            }
            
            # Call the function
            result = _create_grpc_server_with_temp_certs(server_config)
            
            # Verify ensure_certificate_exists was called (not the special ACME logic)
            mock_ensure_cert.assert_called_once_with(cert_file, key_file, hostname="localhost")
            
            assert result == mock_server_instance

    @patch("vibectl.server.grpc_server.GRPCServer")
    @patch("vibectl.server.cert_utils.generate_self_signed_certificate")
    @patch("vibectl.server.cert_utils.get_default_cert_paths")
    @patch("vibectl.config_utils.get_config_dir")
    def test_create_grpc_server_acme_tls_alpn_without_domains(
        self,
        mock_get_config_dir: Mock,
        mock_get_default_paths: Mock,
        mock_generate_cert: Mock,
        mock_grpc_server: Mock,
    ) -> None:
        """Test server creation with TLS-ALPN-01 but no domains falls back to standard generation."""
        # Setup mocks
        mock_config_dir = Path("/test/config")
        mock_get_config_dir.return_value = mock_config_dir
        
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = str(Path(temp_dir) / "server.crt")
            key_file = str(Path(temp_dir) / "server.key")
            mock_get_default_paths.return_value = (cert_file, key_file)
            
            mock_generate_cert.return_value = (b"cert_data", b"key_data")
            mock_server_instance = Mock()
            mock_grpc_server.return_value = mock_server_instance
            
            # Server config with ACME TLS-ALPN-01 but no domains
            server_config = {
                "server": {"host": "example.com", "port": 443, "max_workers": 10, "default_model": "test-model"},
                "jwt": {"enabled": False},
                "tls": {"enabled": True},
                "acme": {
                    "enabled": True,
                    "challenge_type": "tls-alpn-01",
                    "domains": []  # Empty domains list
                }
            }
            
            # Call the function - should not hit the ACME domain logic
            with patch("vibectl.server.cert_utils.ensure_certificate_exists") as mock_ensure_cert:
                result = _create_grpc_server_with_temp_certs(server_config)
                
                # Should use ensure_certificate_exists since domains is empty
                mock_ensure_cert.assert_called_once_with(cert_file, key_file, hostname="example.com")
                mock_generate_cert.assert_not_called()

    @patch("vibectl.server.grpc_server.GRPCServer")
    @patch("vibectl.server.cert_utils.generate_self_signed_certificate")
    @patch("vibectl.server.cert_utils.get_default_cert_paths")
    @patch("vibectl.config_utils.get_config_dir")
    def test_create_grpc_server_acme_with_wildcard_bind(
        self,
        mock_get_config_dir: Mock,
        mock_get_default_paths: Mock,
        mock_generate_cert: Mock,
        mock_grpc_server: Mock,
    ) -> None:
        """Test server creation with wildcard bind address converts to localhost for certificate."""
        # Setup mocks
        mock_config_dir = Path("/test/config")
        mock_get_config_dir.return_value = mock_config_dir
        
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = str(Path(temp_dir) / "server.crt")
            key_file = str(Path(temp_dir) / "server.key")
            mock_get_default_paths.return_value = (cert_file, key_file)
            
            mock_generate_cert.return_value = (b"cert_data", b"key_data")
            mock_server_instance = Mock()
            mock_grpc_server.return_value = mock_server_instance
            
            # Server config with wildcard bind (0.0.0.0 or ::)
            for wildcard_host in ["0.0.0.0", "::"]:
                server_config = {
                    "server": {"host": wildcard_host, "port": 443, "max_workers": 10, "default_model": "test-model"},
                    "jwt": {"enabled": False},
                    "tls": {"enabled": True},
                    "acme": {
                        "enabled": True,
                        "challenge_type": "tls-alpn-01",
                        "domains": ["api.example.com"]
                    }
                }
                
                mock_generate_cert.reset_mock()
                
                # Call the function
                result = _create_grpc_server_with_temp_certs(server_config)
                
                # Verify the wildcard host is converted to localhost in additional_sans
                mock_generate_cert.assert_called_once_with(
                    hostname="api.example.com",
                    cert_file=cert_file,
                    key_file=key_file,
                    days_valid=365,
                    additional_sans=["api.example.com", "localhost", "localhost"]  # Original hostname becomes localhost
                )

    @patch("vibectl.server.grpc_server.GRPCServer")
    @patch("vibectl.server.cert_utils.generate_self_signed_certificate")
    @patch("vibectl.server.cert_utils.get_default_cert_paths")
    @patch("vibectl.config_utils.get_config_dir")
    def test_create_grpc_server_acme_single_domain(
        self,
        mock_get_config_dir: Mock,
        mock_get_default_paths: Mock,
        mock_generate_cert: Mock,
        mock_grpc_server: Mock,
    ) -> None:
        """Test server creation with single ACME domain."""
        # Setup mocks
        mock_config_dir = Path("/test/config")
        mock_get_config_dir.return_value = mock_config_dir
        
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = str(Path(temp_dir) / "server.crt")
            key_file = str(Path(temp_dir) / "server.key")
            mock_get_default_paths.return_value = (cert_file, key_file)
            
            mock_generate_cert.return_value = (b"cert_data", b"key_data")
            mock_server_instance = Mock()
            mock_grpc_server.return_value = mock_server_instance
            
            # Server config with single ACME domain
            server_config = {
                "server": {"host": "api.example.com", "port": 443, "max_workers": 10, "default_model": "test-model"},
                "jwt": {"enabled": False},
                "tls": {"enabled": True},
                "acme": {
                    "enabled": True,
                    "challenge_type": "tls-alpn-01",
                    "domains": ["api.example.com"]
                }
            }
            
            # Call the function
            result = _create_grpc_server_with_temp_certs(server_config)
            
            # Verify certificate generation with single domain
            mock_generate_cert.assert_called_once_with(
                hostname="api.example.com",
                cert_file=cert_file,
                key_file=key_file,
                days_valid=365,
                additional_sans=["api.example.com", "api.example.com", "localhost"]  # Includes original hostname
            )

    @patch("vibectl.server.grpc_server.GRPCServer")
    @patch("vibectl.server.cert_utils.generate_self_signed_certificate")
    @patch("vibectl.server.cert_utils.get_default_cert_paths")
    @patch("vibectl.config_utils.get_config_dir")
    def test_create_grpc_server_certificate_generation_error(
        self,
        mock_get_config_dir: Mock,
        mock_get_default_paths: Mock,
        mock_generate_cert: Mock,
        mock_grpc_server: Mock,
    ) -> None:
        """Test server creation handles certificate generation errors."""
        # Setup mocks
        mock_config_dir = Path("/test/config")
        mock_get_config_dir.return_value = mock_config_dir
        
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = str(Path(temp_dir) / "server.crt")
            key_file = str(Path(temp_dir) / "server.key")
            mock_get_default_paths.return_value = (cert_file, key_file)
            
            # Make certificate generation fail
            mock_generate_cert.side_effect = CertificateGenerationError("Certificate generation failed")
            
            # Server config with ACME TLS-ALPN-01
            server_config = {
                "server": {"host": "0.0.0.0", "port": 443, "max_workers": 10, "default_model": "test-model"},
                "jwt": {"enabled": False},
                "tls": {"enabled": True},
                "acme": {
                    "enabled": True,
                    "challenge_type": "tls-alpn-01",
                    "domains": ["api.example.com"]
                }
            }
            
            # Call the function - should propagate the exception
            with pytest.raises(CertificateGenerationError, match="Certificate generation failed"):
                _create_grpc_server_with_temp_certs(server_config)

    @patch("vibectl.server.grpc_server.GRPCServer")
    @patch("vibectl.server.cert_utils.generate_self_signed_certificate")
    @patch("vibectl.server.cert_utils.get_default_cert_paths")
    @patch("vibectl.config_utils.get_config_dir")
    def test_create_grpc_server_acme_preserves_original_hostname(
        self,
        mock_get_config_dir: Mock,
        mock_get_default_paths: Mock,
        mock_generate_cert: Mock,
        mock_grpc_server: Mock,
    ) -> None:
        """Test that original hostname is preserved in additional_sans."""
        # Setup mocks
        mock_config_dir = Path("/test/config")
        mock_get_config_dir.return_value = mock_config_dir
        
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = str(Path(temp_dir) / "server.crt")
            key_file = str(Path(temp_dir) / "server.key")
            mock_get_default_paths.return_value = (cert_file, key_file)
            
            mock_generate_cert.return_value = (b"cert_data", b"key_data")
            mock_server_instance = Mock()
            mock_grpc_server.return_value = mock_server_instance
            
            # Server config with specific hostname different from ACME domains
            server_config = {
                "server": {"host": "internal.service.local", "port": 443, "max_workers": 10, "default_model": "test-model"},
                "jwt": {"enabled": False},
                "tls": {"enabled": True},
                "acme": {
                    "enabled": True,
                    "challenge_type": "tls-alpn-01",
                    "domains": ["public.example.com", "api.example.com"]
                }
            }
            
            # Call the function
            result = _create_grpc_server_with_temp_certs(server_config)
            
            # Verify that original hostname is included in additional_sans
            mock_generate_cert.assert_called_once_with(
                hostname="public.example.com",  # First ACME domain becomes primary
                cert_file=cert_file,
                key_file=key_file,
                days_valid=365,
                additional_sans=["public.example.com", "api.example.com", "internal.service.local", "localhost"]
            )

    @patch("vibectl.server.grpc_server.GRPCServer")
    @patch("vibectl.server.cert_utils.generate_self_signed_certificate")
    @patch("vibectl.server.cert_utils.get_default_cert_paths")
    @patch("vibectl.config_utils.get_config_dir")
    def test_create_grpc_server_acme_missing_config_sections(
        self,
        mock_get_config_dir: Mock,
        mock_get_default_paths: Mock,
        mock_generate_cert: Mock,
        mock_grpc_server: Mock,
    ) -> None:
        """Test server creation handles missing config sections gracefully."""
        # Setup mocks
        mock_config_dir = Path("/test/config")
        mock_get_config_dir.return_value = mock_config_dir
        
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = str(Path(temp_dir) / "server.crt")
            key_file = str(Path(temp_dir) / "server.key")
            mock_get_default_paths.return_value = (cert_file, key_file)
            
            mock_server_instance = Mock()
            mock_grpc_server.return_value = mock_server_instance
            
            # Server config with missing acme section
            server_config = {
                "server": {"host": "localhost", "port": 50051, "max_workers": 10, "default_model": "test-model"},
                "jwt": {"enabled": False},
                "tls": {"enabled": True},
                # No acme section
            }
            
            with patch("vibectl.server.cert_utils.ensure_certificate_exists") as mock_ensure_cert:
                # Call the function
                result = _create_grpc_server_with_temp_certs(server_config)
                
                # Should fall back to ensure_certificate_exists
                mock_ensure_cert.assert_called_once_with(cert_file, key_file, hostname="localhost")
                mock_generate_cert.assert_not_called()


class TestACMEBootstrapCertificateIntegration:
    """Integration tests for ACME bootstrap certificate functionality."""

    @patch("vibectl.server.grpc_server.GRPCServer")
    @patch("vibectl.config_utils.get_config_dir")
    def test_acme_bootstrap_creates_valid_certificate_with_domains(
        self,
        mock_get_config_dir: Mock,
        mock_grpc_server: Mock,
    ) -> None:
        """Integration test: verify ACME bootstrap creates valid certificate with all domains."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mock_config_dir = Path(temp_dir)
            mock_get_config_dir.return_value = mock_config_dir
            
            mock_server_instance = Mock()
            mock_grpc_server.return_value = mock_server_instance
            
            # Server config with ACME TLS-ALPN-01 and multiple domains
            acme_domains = ["api.example.com", "www.example.com", "example.com"]
            server_config = {
                "server": {"host": "0.0.0.0", "port": 443, "max_workers": 10, "default_model": "test-model"},
                "jwt": {"enabled": False},
                "tls": {"enabled": True},
                "acme": {
                    "enabled": True,
                    "challenge_type": "tls-alpn-01",
                    "domains": acme_domains
                }
            }
            
            # Call the function (will actually generate certificate)
            result = _create_grpc_server_with_temp_certs(server_config)
            
            # Verify certificate was created
            cert_dir = mock_config_dir / "certs"
            cert_file = cert_dir / "server.crt"
            key_file = cert_dir / "server.key"
            
            assert cert_file.exists()
            assert key_file.exists()
            
            # Parse the generated certificate and verify SANs
            cert_bytes = cert_file.read_bytes()
            cert = x509.load_pem_x509_certificate(cert_bytes)
            
            # Get Subject Alternative Names
            san_extension = cert.extensions.get_extension_for_oid(x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
            san_values = san_extension.value
            
            # Extract DNS names from SANs
            dns_names = [str(dns) for dns in cast(x509.SubjectAlternativeName, san_values).get_values_for_type(x509.DNSName)]
            
            # Verify all ACME domains are present
            for domain in acme_domains:
                assert domain in dns_names, f"Domain {domain} not found in certificate SANs: {dns_names}"
            
            # Verify localhost is also present (from additional_sans)
            assert "localhost" in dns_names
            
            # Verify the subject CN is the first ACME domain
            subject_cn = None
            for attribute in cert.subject:
                if attribute.oid == x509.NameOID.COMMON_NAME:
                    subject_cn = attribute.value
                    break
            
            assert subject_cn == acme_domains[0]
            
            # Verify GRPCServer was called with correct paths
            mock_grpc_server.assert_called_once_with(
                host="0.0.0.0",
                port=443,
                default_model="test-model",
                max_workers=10,
                require_auth=False,
                use_tls=True,
                cert_file=str(cert_file),
                key_file=str(key_file),
            )

    @patch("vibectl.server.grpc_server.GRPCServer")
    @patch("vibectl.config_utils.get_config_dir")
    def test_non_acme_bootstrap_creates_standard_certificate(
        self,
        mock_get_config_dir: Mock,
        mock_grpc_server: Mock,
    ) -> None:
        """Integration test: verify non-ACME bootstrap creates standard certificate."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mock_config_dir = Path(temp_dir)
            mock_get_config_dir.return_value = mock_config_dir
            
            mock_server_instance = Mock()
            mock_grpc_server.return_value = mock_server_instance
            
            # Server config without ACME
            server_config = {
                "server": {"host": "test.local", "port": 50051, "max_workers": 10, "default_model": "test-model"},
                "jwt": {"enabled": False},
                "tls": {"enabled": True},
                "acme": {"enabled": False}
            }
            
            # Call the function
            result = _create_grpc_server_with_temp_certs(server_config)
            
            # Verify certificate was created
            cert_dir = mock_config_dir / "certs"
            cert_file = cert_dir / "server.crt"
            key_file = cert_dir / "server.key"
            
            assert cert_file.exists()
            assert key_file.exists()
            
            # Parse the generated certificate and verify standard SANs
            cert_bytes = cert_file.read_bytes()
            cert = x509.load_pem_x509_certificate(cert_bytes)
            
            # Get Subject Alternative Names
            san_extension = cert.extensions.get_extension_for_oid(x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
            san_values = san_extension.value
            
            # Extract DNS names from SANs
            dns_names = [str(dns) for dns in cast(x509.SubjectAlternativeName, san_values).get_values_for_type(x509.DNSName)]
            
            # Should only have standard DNS names (hostname + localhost)
            assert "test.local" in dns_names
            assert "localhost" in dns_names
            
            # Should not have any additional domains
            assert len(dns_names) == 2
            
            # Verify the subject CN matches hostname
            subject_cn = None
            for attribute in cert.subject:
                if attribute.oid == x509.NameOID.COMMON_NAME:
                    subject_cn = attribute.value
                    break
            
            assert subject_cn == "test.local" 