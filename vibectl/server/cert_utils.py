"""
Certificate utilities for TLS support in the vibectl LLM proxy server.

This module provides functionality for generating, loading, and managing
TLS certificates for secure gRPC communication.
"""

import ipaddress
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from vibectl.types import CertificateGenerationError, CertificateLoadError

logger = logging.getLogger(__name__)


def validate_certificate_files(cert_file: str, key_file: str) -> None:
    """Validate that certificate files exist and are readable.

    Args:
        cert_file: Path to the certificate file
        key_file: Path to the private key file

    Raises:
        CertificateLoadError: If files don't exist or aren't readable
    """
    cert_path = Path(cert_file)
    key_path = Path(key_file)

    if not cert_path.exists():
        raise CertificateLoadError(f"Certificate file not found: {cert_file}")

    if not key_path.exists():
        raise CertificateLoadError(f"Private key file not found: {key_file}")

    if not cert_path.is_file():
        raise CertificateLoadError(f"Certificate path is not a file: {cert_file}")

    if not key_path.is_file():
        raise CertificateLoadError(f"Private key path is not a file: {key_file}")

    # Check read permissions
    try:
        with cert_path.open("rb"):
            pass
    except PermissionError as e:
        raise CertificateLoadError(f"Cannot read certificate file: {cert_file}") from e

    try:
        with key_path.open("rb"):
            pass
    except PermissionError as e:
        raise CertificateLoadError(f"Cannot read private key file: {key_file}") from e


def load_certificate_credentials(cert_file: str, key_file: str) -> tuple[bytes, bytes]:
    """Load certificate and private key from files.

    Args:
        cert_file: Path to the certificate file
        key_file: Path to the private key file

    Returns:
        Tuple of (cert_bytes, key_bytes)

    Raises:
        CertificateLoadError: If files cannot be loaded
    """
    validate_certificate_files(cert_file, key_file)

    try:
        with open(cert_file, "rb") as f:
            cert_data = f.read()

        with open(key_file, "rb") as f:
            key_data = f.read()

        return cert_data, key_data

    except Exception as e:
        raise CertificateLoadError(f"Failed to load certificate files: {e}") from e


def generate_self_signed_certificate(
    hostname: str = "localhost",
    cert_file: str | None = None,
    key_file: str | None = None,
    days_valid: int = 365,
    additional_sans: list[str] | None = None,
) -> tuple[bytes, bytes]:
    """Generate a self-signed certificate for development use.

    Args:
        hostname: Hostname to generate certificate for
        cert_file: Optional path to save certificate file
        key_file: Optional path to save private key file
        days_valid: Number of days the certificate should be valid
        additional_sans: Additional Subject Alternative Names to include

    Returns:
        Tuple of (cert_bytes, key_bytes)

    Raises:
        CertificateGenerationError: If certificate generation fails
    """
    try:
        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        # Generate certificate
        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Development"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "Local"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Vibectl Development"),
                x509.NameAttribute(NameOID.COMMON_NAME, hostname),
            ]
        )

        # Build Subject Alternative Names list
        san_names = [
            x509.DNSName(hostname),
            x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            x509.IPAddress(ipaddress.IPv6Address("::1")),
        ]

        # Add localhost if it's not already the hostname
        if hostname != "localhost":
            san_names.append(x509.DNSName("localhost"))

        # Add additional SANs if provided
        if additional_sans:
            # Keep track of existing values to avoid duplicates
            existing_dns_names = {hostname}
            if hostname != "localhost":
                existing_dns_names.add("localhost")
            existing_ip_addresses = {"127.0.0.1", "::1"}

            for san in additional_sans:
                try:
                    # Try to parse as IP address first
                    ip = ipaddress.ip_address(san)
                    ip_str = str(ip)
                    if ip_str not in existing_ip_addresses:
                        san_names.append(x509.IPAddress(ip))
                        existing_ip_addresses.add(ip_str)
                except ValueError:
                    # Not an IP address, treat as DNS name
                    if san not in existing_dns_names:
                        san_names.append(x509.DNSName(san))
                        existing_dns_names.add(san)

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.utcnow())
            .not_valid_after(datetime.utcnow() + timedelta(days=days_valid))
            .add_extension(
                x509.SubjectAlternativeName(san_names),
                critical=False,
            )
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    key_encipherment=True,
                    digital_signature=True,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    content_commitment=False,
                    data_encipherment=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(private_key, hashes.SHA256())
        )

        # Serialize to PEM format
        cert_bytes = cert.public_bytes(serialization.Encoding.PEM)
        key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        # Save to files if paths provided
        if cert_file:
            cert_path = Path(cert_file)
            cert_path.parent.mkdir(parents=True, exist_ok=True)
            with cert_path.open("wb") as f:
                f.write(cert_bytes)
            # Set secure permissions
            os.chmod(cert_file, 0o644)
            logger.info("Generated certificate saved to: %s", cert_file)

        if key_file:
            key_path = Path(key_file)
            key_path.parent.mkdir(parents=True, exist_ok=True)
            with key_path.open("wb") as f:
                f.write(key_bytes)
            # Set secure permissions for private key
            os.chmod(key_file, 0o600)
            logger.info("Generated private key saved to: %s", key_file)

        logger.info(
            "Generated self-signed certificate for hostname: %s (valid for %d days)",
            hostname,
            days_valid,
        )
        return cert_bytes, key_bytes

    except Exception as e:
        raise CertificateGenerationError(
            f"Failed to generate self-signed certificate: {e}"
        ) from e


def get_default_cert_paths(config_dir: Path) -> tuple[str, str]:
    """Get default paths for certificate and key files.

    Args:
        config_dir: Configuration directory path

    Returns:
        Tuple of (cert_file_path, key_file_path)
    """
    cert_dir = config_dir / "certs"
    cert_file = str(cert_dir / "server.crt")
    key_file = str(cert_dir / "server.key")
    return cert_file, key_file


def ensure_certificate_exists(
    cert_file: str,
    key_file: str,
    hostname: str = "localhost",
    days_valid: int = 365,
    regenerate: bool = False,
) -> None:
    """Ensure a certificate exists, generating it if necessary.

    Args:
        cert_file: Path to certificate file
        key_file: Path to private key file
        hostname: Hostname for certificate generation
        days_valid: Days the certificate should be valid
        regenerate: Force regeneration even if files exist

    Raises:
        CertificateGenerationError: If certificate generation fails
    """
    cert_path = Path(cert_file)
    key_path = Path(key_file)

    # Check if we need to generate certificates
    if regenerate or not cert_path.exists() or not key_path.exists():
        logger.info("Generating self-signed certificate for development use")
        generate_self_signed_certificate(
            hostname=hostname,
            cert_file=cert_file,
            key_file=key_file,
            days_valid=days_valid,
        )
    else:
        logger.debug("Using existing certificate files: %s, %s", cert_file, key_file)


def handle_certificate_generation_for_server(
    server_config: dict,
    hostname_override: str | None = None,
    regenerate: bool = False,
) -> tuple[str, str]:
    """Handle certificate generation for a server configuration.

    This function encapsulates the logic for determining certificate paths,
    handling hostname resolution, and generating certificates if needed.

    Args:
        server_config: Server configuration dictionary
        hostname_override: Optional hostname override
        regenerate: Whether to force regeneration of certificates

    Returns:
        Tuple of (cert_file_path, key_file_path)

    Raises:
        CertificateGenerationError: If certificate generation fails
    """
    try:
        from vibectl.config_utils import get_config_dir

        # Get certificate paths from config or use defaults
        cert_file = server_config.get("tls", {}).get("cert_file")
        key_file = server_config.get("tls", {}).get("key_file")

        # Use default paths if not specified
        if cert_file is None or key_file is None:
            config_dir = get_config_dir("server")
            default_cert_file, default_key_file = get_default_cert_paths(config_dir)
            cert_file = cert_file or default_cert_file
            key_file = key_file or default_key_file

        # Determine hostname
        if hostname_override:
            hostname = hostname_override
        else:
            hostname = server_config.get("server", {}).get("host", "localhost")
            # Convert bind-all addresses to localhost for certificate generation
            if hostname in ("0.0.0.0", "::"):
                hostname = "localhost"

        # Generate certificates if needed
        ensure_certificate_exists(
            str(cert_file), str(key_file), hostname=hostname, regenerate=regenerate
        )

        return str(cert_file), str(key_file)

    except Exception as e:
        raise CertificateGenerationError(
            f"Certificate generation for server failed: {e}"
        ) from e


def create_certificate_signing_request(
    domains: list[str],
    private_key: rsa.RSAPrivateKey,
    organization: str | None = None,
    country: str | None = None,
) -> x509.CertificateSigningRequest:
    """Create a Certificate Signing Request for the given domains.

    Args:
        domains: List of domain names (first will be used as Common Name)
        private_key: Private key for the certificate
        organization: Optional organization name
        country: Optional country code

    Returns:
        Cryptography CSR object

    Raises:
        CertificateGenerationError: If CSR generation fails
    """
    try:
        # Build subject with required Common Name
        subject_components = [
            x509.NameAttribute(NameOID.COMMON_NAME, domains[0]),
        ]

        # Add optional organization and country
        if organization:
            subject_components.append(
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization)
            )
        if country:
            subject_components.append(x509.NameAttribute(NameOID.COUNTRY_NAME, country))

        subject = x509.Name(subject_components)

        # Create CSR builder
        builder = x509.CertificateSigningRequestBuilder()
        builder = builder.subject_name(subject)

        # Add SAN extension for multiple domains or single domain
        if len(domains) > 1 or domains[0]:
            san_list = [x509.DNSName(domain) for domain in domains]
            builder = builder.add_extension(
                x509.SubjectAlternativeName(san_list),
                critical=False,
            )

        # Sign the CSR with SHA256
        csr = builder.sign(private_key, hashes.SHA256())
        return csr

    except Exception as e:
        raise CertificateGenerationError(f"Failed to create CSR: {e}") from e
