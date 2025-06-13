"""
Certificate Authority (CA) Management for Production TLS.

This module provides production-grade certificate authority management including:
- Root CA generation and management
- Intermediate CA for server certificates
- Certificate lifecycle management
- Automatic renewal and rotation
- CA certificate distribution

Supports both private CA hierarchies and public CA integration (Let's Encrypt).
"""

import ipaddress
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from vibectl.types import CAManagerError

logger = logging.getLogger(__name__)


class CertificateInfo:
    """Information about a certificate."""

    def __init__(self, cert: "x509.Certificate"):
        self.certificate = cert
        self.subject = cert.subject
        self.issuer = cert.issuer
        self.serial_number = cert.serial_number
        self.not_valid_before = cert.not_valid_before_utc
        self.not_valid_after = cert.not_valid_after_utc

    @property
    def is_expired(self) -> bool:
        """Check if certificate is expired."""
        return datetime.now().astimezone() > self.not_valid_after

    def expires_soon(self, days: int = 30) -> bool:
        """Check if certificate expires within specified days."""
        threshold = datetime.now().astimezone() + timedelta(days=days)
        return threshold > self.not_valid_after

    @property
    def subject_cn(self) -> str:
        """Get the Common Name from subject."""
        for attribute in self.subject:
            if attribute.oid == NameOID.COMMON_NAME:
                value = attribute.value
                # Handle both str and bytes return types from cryptography
                if isinstance(value, bytes):
                    return value.decode("utf-8")
                return str(value)
        return ""


class CAManager:
    """Production-grade Certificate Authority Manager."""

    def __init__(self, ca_dir: Path):
        """Initialize CA Manager.

        Args:
            ca_dir: Directory to store CA certificates and keys
        """
        self.ca_dir = Path(ca_dir)
        self.root_ca_dir = self.ca_dir / "root"
        self.intermediate_ca_dir = self.ca_dir / "intermediate"
        self.server_certs_dir = self.ca_dir / "server_certs"

        # Create directory structure
        for directory in [
            self.root_ca_dir,
            self.intermediate_ca_dir,
            self.server_certs_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

        # Secure directory permissions (readable only by owner)
        try:
            os.chmod(self.ca_dir, 0o700)
            os.chmod(self.root_ca_dir, 0o700)
            os.chmod(self.intermediate_ca_dir, 0o700)
        except OSError as e:
            logger.warning(f"Could not set secure permissions: {e}")

    def create_root_ca(
        self,
        common_name: str = "vibectl Root CA",
        organization: str = "vibectl",
        country: str = "US",
        validity_years: int = 10,
    ) -> tuple[Path, Path]:
        """Create a new Root CA certificate and private key.

        Args:
            common_name: Common name for the Root CA
            organization: Organization name
            country: Country code (2 letters)
            validity_years: Validity period in years

        Returns:
            Tuple of (cert_path, key_path)
        """
        logger.info(f"Creating Root CA: {common_name}")

        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=4096,
        )

        # Create certificate
        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, country),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
                x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            ]
        )

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now().astimezone())
            .not_valid_after(
                datetime.now().astimezone() + timedelta(days=365 * validity_years)
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()),
                critical=False,
            )
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(
                    private_key.public_key()
                ),
                critical=False,
            )
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=1),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    key_cert_sign=True,
                    crl_sign=True,
                    digital_signature=False,
                    key_encipherment=False,
                    content_commitment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(private_key, hashes.SHA256())
        )

        # Save certificate and key
        cert_path = self.root_ca_dir / "ca.crt"
        key_path = self.root_ca_dir / "ca.key"

        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        with open(key_path, "wb") as f:
            f.write(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )

        # Secure file permissions
        try:
            os.chmod(cert_path, 0o644)
            os.chmod(key_path, 0o600)
        except OSError as e:
            logger.warning(f"Could not set file permissions: {e}")

        logger.info(f"Root CA created: {cert_path}")
        return cert_path, key_path

    def create_intermediate_ca(
        self,
        common_name: str = "vibectl Intermediate CA",
        organization: str = "vibectl",
        country: str = "US",
        validity_years: int = 5,
    ) -> tuple[Path, Path]:
        """Create an Intermediate CA signed by the Root CA.

        Args:
            common_name: Common name for the Intermediate CA
            organization: Organization name
            country: Country code (2 letters)
            validity_years: Validity period in years

        Returns:
            Tuple of (cert_path, key_path)
        """
        logger.info(f"Creating Intermediate CA: {common_name}")

        # Load root CA
        root_cert, root_key = self._load_root_ca()

        # Generate private key for intermediate CA
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        # Create certificate
        subject = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, country),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
                x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            ]
        )

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(root_cert.subject)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now().astimezone())
            .not_valid_after(
                datetime.now().astimezone() + timedelta(days=365 * validity_years)
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()),
                critical=False,
            )
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(
                    root_key.public_key()
                ),
                critical=False,
            )
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=0),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    key_cert_sign=True,
                    crl_sign=True,
                    digital_signature=False,
                    key_encipherment=False,
                    content_commitment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(root_key, hashes.SHA256())
        )

        # Save certificate and key
        cert_path = self.intermediate_ca_dir / "ca.crt"
        key_path = self.intermediate_ca_dir / "ca.key"

        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        with open(key_path, "wb") as f:
            f.write(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )

        # Secure file permissions
        try:
            os.chmod(cert_path, 0o644)
            os.chmod(key_path, 0o600)
        except OSError as e:
            logger.warning(f"Could not set file permissions: {e}")

        logger.info(f"Intermediate CA created: {cert_path}")
        return cert_path, key_path

    def create_server_certificate(
        self,
        hostname: str,
        san_list: list[str] | None = None,
        validity_days: int = 90,
    ) -> tuple[Path, Path]:
        """Create a server certificate signed by the Intermediate CA.

        Args:
            hostname: Primary hostname for the certificate
            san_list: List of Subject Alternative Names
            validity_days: Validity period in days

        Returns:
            Tuple of (cert_path, key_path)
        """
        logger.info(f"Creating server certificate for: {hostname}")

        # Load intermediate CA
        intermediate_cert, intermediate_key = self._load_intermediate_ca()

        # Generate private key for server
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        # Prepare SAN list
        if san_list is None:
            san_list = []
        if hostname not in san_list:
            san_list.insert(0, hostname)

        # Create certificate
        subject = x509.Name(
            [
                x509.NameAttribute(NameOID.COMMON_NAME, hostname),
            ]
        )

        cert_builder = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(intermediate_cert.subject)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now().astimezone())
            .not_valid_after(
                datetime.now().astimezone() + timedelta(days=validity_days)
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()),
                critical=False,
            )
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(
                    intermediate_key.public_key()
                ),
                critical=False,
            )
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    key_cert_sign=False,
                    crl_sign=False,
                    digital_signature=True,
                    key_encipherment=True,
                    content_commitment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage(
                    [
                        ExtendedKeyUsageOID.SERVER_AUTH,
                    ]
                ),
                critical=True,
            )
        )

        # Add Subject Alternative Names
        san_names: list[x509.DNSName | x509.IPAddress] = []
        for name in san_list:
            try:
                # Try to parse as IP address first
                ip = ipaddress.ip_address(name)
                san_names.append(x509.IPAddress(ip))
            except ValueError:
                # Not an IP address, treat as DNS name
                san_names.append(x509.DNSName(name))

        if san_names:
            cert_builder = cert_builder.add_extension(
                x509.SubjectAlternativeName(san_names),
                critical=False,
            )

        cert = cert_builder.sign(intermediate_key, hashes.SHA256())

        # Create certificate-specific directory
        cert_dir = self.server_certs_dir / hostname
        cert_dir.mkdir(exist_ok=True)

        # Save certificate and key
        cert_path = cert_dir / f"{hostname}.crt"
        key_path = cert_dir / f"{hostname}.key"

        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        with open(key_path, "wb") as f:
            f.write(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )

        # Secure file permissions
        try:
            os.chmod(cert_path, 0o644)
            os.chmod(key_path, 0o600)
        except OSError as e:
            logger.warning(f"Could not set file permissions: {e}")

        logger.info(f"Server certificate created: {cert_path}")
        return cert_path, key_path

    def create_ca_bundle(self) -> Path:
        """Create a CA bundle file containing the complete certificate chain.

        Returns:
            Path to the CA bundle file
        """
        bundle_path = self.ca_dir / "ca-bundle.crt"

        root_cert_path = self.root_ca_dir / "ca.crt"
        intermediate_cert_path = self.intermediate_ca_dir / "ca.crt"

        if not root_cert_path.exists():
            raise CAManagerError("CA certificates not found")

        # Read root certificate
        with open(root_cert_path) as f:
            root_cert_data = f.read()

        # Read intermediate certificate if it exists
        intermediate_cert_data = ""
        if intermediate_cert_path.exists():
            with open(intermediate_cert_path) as f:
                intermediate_cert_data = f.read()

        # Create bundle with root and optionally intermediate
        with open(bundle_path, "w") as f:
            f.write(root_cert_data)
            if intermediate_cert_data:
                if not root_cert_data.endswith("\n"):
                    f.write("\n")
                f.write(intermediate_cert_data)

        logger.info(f"CA bundle created: {bundle_path}")
        return bundle_path

    def get_certificate_info(self, cert_path: Path) -> CertificateInfo:
        """Get information about a certificate file.

        Args:
            cert_path: Path to certificate file

        Returns:
            CertificateInfo object
        """
        try:
            with open(cert_path, "rb") as f:
                cert_data = f.read()
        except FileNotFoundError:
            raise CAManagerError("Certificate file not found") from None

        try:
            cert = x509.load_pem_x509_certificate(cert_data)
        except ValueError:
            raise CAManagerError("Failed to load certificate") from None

        return CertificateInfo(cert)

    def check_certificate_expiry(
        self, days_threshold: int = 30
    ) -> list[tuple[Path, CertificateInfo]]:
        """Check for certificates that are expired or expiring soon.

        Args:
            days_threshold: Days before expiry to consider "expiring soon"

        Returns:
            List of (cert_path, cert_info) tuples for problematic certificates
        """
        problematic_certs = []

        # Check all certificates in the CA directory structure
        for cert_path in self.ca_dir.rglob("*.crt"):
            try:
                cert_info = self.get_certificate_info(cert_path)
                if cert_info.is_expired or cert_info.expires_soon(days_threshold):
                    problematic_certs.append((cert_path, cert_info))
            except Exception as e:
                logger.warning(f"Could not check certificate {cert_path}: {e}")

        return problematic_certs

    def _load_root_ca(self) -> tuple["x509.Certificate", Any]:
        """Load Root CA certificate and private key."""
        cert_path = self.root_ca_dir / "ca.crt"
        key_path = self.root_ca_dir / "ca.key"

        if not cert_path.exists():
            raise CAManagerError("Root CA not found")
        if not key_path.exists():
            raise CAManagerError("Root CA private key not found")

        with open(cert_path, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())

        with open(key_path, "rb") as f:
            key = serialization.load_pem_private_key(f.read(), password=None)

        return cert, key

    def _load_intermediate_ca(self) -> tuple["x509.Certificate", Any]:
        """Load Intermediate CA certificate and private key."""
        cert_path = self.intermediate_ca_dir / "ca.crt"
        key_path = self.intermediate_ca_dir / "ca.key"

        if not cert_path.exists():
            raise CAManagerError("Intermediate CA not found")
        if not key_path.exists():
            raise CAManagerError("Intermediate CA private key not found")

        with open(cert_path, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())

        with open(key_path, "rb") as f:
            key = serialization.load_pem_private_key(f.read(), password=None)

        return cert, key


def setup_private_ca(
    ca_dir: Path,
    root_cn: str = "vibectl Root CA",
    intermediate_cn: str = "vibectl Intermediate CA",
    organization: str = "vibectl",
    country: str = "US",
) -> CAManager:
    """Set up a complete private CA infrastructure.

    Args:
        ca_dir: Directory to create CA in
        root_cn: Common name for root CA
        intermediate_cn: Common name for intermediate CA
        organization: Organization name for certificates
        country: Country code for certificates (2 letters)

    Returns:
        Configured CAManager instance
    """
    ca_manager = CAManager(ca_dir)

    # Create Root CA if it doesn't exist
    root_cert_path = ca_manager.root_ca_dir / "ca.crt"
    if not root_cert_path.exists():
        logger.info("Creating private CA infrastructure...")
        ca_manager.create_root_ca(
            common_name=root_cn, organization=organization, country=country
        )

    # Create Intermediate CA if it doesn't exist
    intermediate_cert_path = ca_manager.intermediate_ca_dir / "ca.crt"
    if not intermediate_cert_path.exists():
        ca_manager.create_intermediate_ca(
            common_name=intermediate_cn, organization=organization, country=country
        )

    # Create CA bundle
    ca_manager.create_ca_bundle()

    logger.info(f"Private CA ready at: {ca_dir}")
    return ca_manager
