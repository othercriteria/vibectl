#!/usr/bin/env python3
"""
Main entry point for the vibectl gRPC LLM proxy server.

This script provides a standalone server that can be run independently
of the main vibectl CLI, reducing complexity and enabling dedicated
server deployment scenarios.
"""

import asyncio
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import click
from rich.table import Table

from vibectl.config_utils import (
    ensure_config_dir,
    get_config_dir,
    parse_duration_to_days,
)
from vibectl.console import console_manager
from vibectl.logutil import init_logging, logger, update_logging_level
from vibectl.types import Error, Result, ServeMode, Success
from vibectl.utils import handle_exception

from . import cert_utils
from .acme_client import LETSENCRYPT_PRODUCTION
from .ca_manager import CAManager, CAManagerError, setup_private_ca
from .config import (
    ServerConfig,
    create_default_server_config,
    load_server_config,
)
from .grpc_server import create_server
from .jwt_auth import JWTAuthManager, load_config_with_generation

# Graceful shutdown handling
shutdown_event = False


# --- Common Server Option Decorator ---
def common_server_options() -> Callable:
    """Decorator to DRY out common server CLI options."""

    def decorator(f: Callable) -> Callable:
        options = [
            click.option("--config", type=click.Path(), help="Configuration file path"),
            click.option(
                "--require-auth", is_flag=True, help="Enable JWT authentication"
            ),
            click.option(
                "--log-level",
                type=click.Choice(
                    ["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False
                ),
                help="Logging level",
            ),
            click.option(
                "--max-workers", type=int, default=None, help="Maximum worker threads"
            ),
            click.option("--model", default=None, help="Default LLM model"),
            click.option("--port", type=int, default=None, help="Port to bind to"),
            click.option("--host", default=None, help="Host to bind to"),
        ]
        for option in reversed(options):
            f = option(f)
        return f

    return decorator


def signal_handler(signum: int, frame: object) -> None:
    """Handle shutdown signals gracefully."""
    global shutdown_event
    logger.info("Received shutdown signal %s, shutting down gracefully...", signum)
    shutdown_event = True


def parse_duration(duration_str: str) -> Result:
    """Parse a duration string into days."""
    try:
        days = parse_duration_to_days(duration_str)
        return Success(data=days)
    except ValueError as e:
        return Error(error=str(e))
    except Exception as e:
        return Error(error=f"Failed to parse duration: {e}", exception=e)


def handle_result(result: Result, exit_on_error: bool = True) -> None:
    """Handle command results using console manager."""
    exit_code: int = 0
    if isinstance(result, Success):
        if result.message:
            console_manager.print_success(result.message)
        # Check for original_exit_code similar to main CLI
        if hasattr(result, "original_exit_code") and isinstance(
            result.original_exit_code, int
        ):
            exit_code = result.original_exit_code
        else:
            exit_code = 0  # Default for Success
        logger.debug(f"Success result, final exit_code: {exit_code}")
    elif isinstance(result, Error):
        console_manager.print_error(result.error)
        # Handle recovery suggestions if they exist
        if hasattr(result, "recovery_suggestions") and result.recovery_suggestions:
            console_manager.print_note(result.recovery_suggestions)
        if result.exception and result.exception is not None:
            handle_exception(result.exception)
        # Check for original_exit_code similar to main CLI
        if hasattr(result, "original_exit_code") and isinstance(
            result.original_exit_code, int
        ):
            exit_code = result.original_exit_code
        else:
            exit_code = 1  # Default for Error
        logger.debug(f"Error result, final exit_code: {exit_code}")

    if exit_on_error:
        sys.exit(exit_code)


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Main CLI group for vibectl-server commands."""
    if ctx.invoked_subcommand is None:
        console_manager.print("vibectl-server: gRPC LLM proxy server")
        console_manager.print("Use --help to see available commands")


@cli.command()
@click.argument("subject")
@click.option(
    "--expires-in", default="1y", help="Token expiration time (e.g., '30d', '1y', '6m')"
)
@click.option(
    "--output", help="Output file for the token (prints to stdout if not specified)"
)
def generate_token(
    subject: str,
    expires_in: str,
    output: str | None,
) -> None:
    """Generate a JWT token for client authentication"""
    # Parse the expiration duration
    duration_result = parse_duration(expires_in)
    if isinstance(duration_result, Error):
        handle_result(duration_result)
        return

    # Cast from Any to int since we know parse_duration returns int on success
    expiration_days = duration_result.data if duration_result.data is not None else 30

    # Generate token
    token_result = _generate_jwt_token(subject, expiration_days, output)
    handle_result(token_result)


def _generate_jwt_token(
    subject: str, expiration_days: int, output: str | None
) -> Result:
    """Generate a JWT token."""
    try:
        # Load JWT configuration
        config = load_config_with_generation(persist_generated_key=True)
        jwt_manager = JWTAuthManager(config)

        # Generate the token
        token = jwt_manager.generate_token(
            subject=subject, expiration_days=expiration_days
        )

        # Output the token
        if output:
            with open(output, "w") as f:
                f.write(token)
            logger.info(f"Token written to {output}")
            return Success(message=f"Token generated and saved to {output}")
        else:
            console_manager.print(token)
            logger.info(
                f"Successfully generated token for subject '{subject}' "
                f"(expires in {expiration_days} days)"
            )
            return Success()

    except Exception as e:
        return Error(error=f"Token generation failed: {e}", exception=e)


@cli.command()
@click.option("--force", is_flag=True, help="Overwrite existing configuration files")
def init_config(force: bool) -> None:
    """Initialize server configuration with default values."""
    try:
        config_dir = ensure_config_dir("server")
        config_file = config_dir / "config.yaml"

        if config_file.exists() and not force:
            console_manager.print_error(
                f"Configuration file already exists: {config_file}"
            )
            console_manager.print_note("Use --force to overwrite")
            sys.exit(1)

        result = create_default_server_config(config_file, force=force)
        if isinstance(result, Error):
            handle_result(result)
            return

        console_manager.print_success(
            f"Server configuration initialized at: {config_dir}"
        )
        console_manager.print(f"Configuration file: {config_file}")
        console_manager.print(
            "\nEdit the configuration file to customize server settings."
        )

    except Exception as e:
        handle_result(
            Error(error=f"Configuration initialization failed: {e}", exception=e)
        )


@cli.command(name="generate-certs")
@click.option(
    "--hostname",
    default="localhost",
    help="Hostname to include in certificate (default: localhost)",
)
@click.option(
    "--cert-file",
    type=click.Path(),
    default=None,
    help="Output path for certificate file "
    "(default: ~/.config/vibectl/server/certs/server.crt)",
)
@click.option(
    "--key-file",
    type=click.Path(),
    default=None,
    help="Output path for private key file "
    "(default: ~/.config/vibectl/server/certs/server.key)",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing certificate files",
)
def generate_certs(
    hostname: str,
    cert_file: str | None,
    key_file: str | None,
    force: bool,
) -> None:
    """Generate self-signed certificates for TLS."""
    # Generate certificates
    cert_result = _perform_certificate_generation(hostname, cert_file, key_file, force)
    handle_result(cert_result)


def _perform_certificate_generation(
    hostname: str, cert_file: str | None, key_file: str | None, force: bool
) -> Result:
    """Perform the actual certificate generation."""
    try:
        config_dir = get_config_dir("server")

        # Use default paths if not specified
        if cert_file is None or key_file is None:
            default_cert_file, default_key_file = cert_utils.get_default_cert_paths(
                config_dir
            )
            cert_file = cert_file or default_cert_file
            key_file = key_file or default_key_file

        # Convert to Path objects
        cert_path = Path(cert_file)
        key_path = Path(key_file)

        # Check if files exist and force is not specified
        if not force and (cert_path.exists() or key_path.exists()):
            return Error(
                error="Certificate files already exist. Use --force to overwrite.",
                recovery_suggestions="Use --force to overwrite existing certificates",
            )

        # Create certificates directory
        cert_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Generating certificate for hostname: {hostname}")
        logger.info(f"Certificate file: {cert_path}")
        logger.info(f"Key file: {key_path}")

        # Generate the certificate
        cert_utils.ensure_certificate_exists(
            str(cert_path), str(key_path), hostname=hostname, regenerate=force
        )

        return Success(message=f"Certificates generated successfully for {hostname}")

    except Exception as e:
        return Error(error=f"Certificate generation failed: {e}", exception=e)


@cli.group(name="ca", invoke_without_command=True)
@click.pass_context
def ca_group(ctx: click.Context) -> None:
    """Certificate Authority management commands.

    Manage a private CA for issuing server certificates. This provides
    better security than self-signed certificates by establishing a
    proper certificate chain.

    Commands:
        init: Initialize a new Certificate Authority
        create-server-cert: Create a server certificate signed by the CA
        status: Show CA and certificate status
        check-expiry: Check for expired or expiring certificates

    The CA consists of:
        - Root CA: Self-signed root certificate authority
        - Intermediate CA: Intermediate certificate authority (signed by root)
        - Server certificates: End-entity certificates (signed by intermediate)

    This structure follows PKI best practices by using an intermediate CA
    for daily operations while keeping the root CA offline/secure.
    """
    if ctx.invoked_subcommand is None:
        console_manager.print(ctx.get_help())


@ca_group.command("init")
@click.option(
    "--ca-dir",
    type=click.Path(),
    default=None,
    help="Directory to create CA in (default: ~/.config/vibectl/server/ca)",
)
@click.option(
    "--root-cn",
    default="vibectl Root CA",
    help="Common name for Root CA",
)
@click.option(
    "--intermediate-cn",
    default="vibectl Intermediate CA",
    help="Common name for Intermediate CA",
)
@click.option(
    "--organization",
    default="vibectl",
    help="Organization name for certificates",
)
@click.option(
    "--country",
    default="US",
    help="Country code for certificates (2 letters)",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing CA if it exists",
)
def ca_init(
    ca_dir: str | None,
    root_cn: str,
    intermediate_cn: str,
    organization: str,
    country: str,
    force: bool,
) -> None:
    """Initialize a new Certificate Authority."""
    # Initialize CA
    ca_result = _initialize_ca(
        ca_dir, root_cn, intermediate_cn, organization, country, force
    )
    handle_result(ca_result)


def _initialize_ca(
    ca_dir: str | None,
    root_cn: str,
    intermediate_cn: str,
    organization: str,
    country: str,
    force: bool,
) -> Result:
    """Initialize the Certificate Authority."""
    try:
        # Determine CA directory
        if ca_dir is None:
            config_dir = ensure_config_dir("server")
            ca_dir_path = config_dir / "ca"
        else:
            ca_dir_path = Path(ca_dir)

        # Check if CA already exists
        if ca_dir_path.exists() and not force:
            return Error(
                error=f"CA directory already exists: {ca_dir_path}",
                recovery_suggestions="Use --force to overwrite existing CA",
            )

        # Validate country code
        if len(country) != 2:
            return Error(error="Country code must be exactly 2 characters")

        console_manager.print_processing(f"Initializing CA in {ca_dir_path}")

        # Initialize the CA with all parameters
        setup_private_ca(ca_dir_path, root_cn, intermediate_cn, organization, country)

        return Success(message=f"CA initialized successfully in {ca_dir_path}")

    except CAManagerError as e:
        return Error(error=f"CA initialization failed: {e}", exception=e)
    except Exception as e:
        return Error(
            error=f"Unexpected error during CA initialization: {e}", exception=e
        )


@ca_group.command("create-server-cert")
@click.argument("hostname")
@click.option(
    "--ca-dir",
    type=click.Path(exists=True),
    default=None,
    help="CA directory (default: ~/.config/vibectl/server/ca)",
)
@click.option(
    "--san",
    multiple=True,
    help="Subject Alternative Name (can be used multiple times)",
)
@click.option(
    "--validity-days",
    type=int,
    default=90,
    help="Certificate validity in days (default: 90)",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing certificate",
)
def ca_create_server_cert(
    hostname: str,
    ca_dir: str | None,
    san: tuple[str, ...],
    validity_days: int,
    force: bool,
) -> None:
    """Create a server certificate signed by the CA."""
    # Create server certificate
    cert_result = _create_server_certificate(
        hostname, ca_dir, san, validity_days, force
    )
    handle_result(cert_result)


def _create_server_certificate(
    hostname: str,
    ca_dir: str | None,
    san: tuple[str, ...],
    validity_days: int,
    force: bool,
) -> Result:
    """Create a server certificate using the CA."""
    try:
        # Determine CA directory
        if ca_dir is None:
            config_dir = ensure_config_dir("server")
            ca_dir_path = config_dir / "ca"
        else:
            ca_dir_path = Path(ca_dir)

        if not ca_dir_path.exists():
            return Error(
                error=f"CA directory not found: {ca_dir_path}",
                recovery_suggestions="Initialize CA first with: vibectl-server ca init",
            )

        # Validate inputs
        if validity_days < 1:
            return Error(error="Validity days must be greater than 0")

        ca_manager = CAManager(ca_dir_path)

        # Check if certificate already exists
        # CAManager creates certificates in server_certs/hostname/ directory
        server_certs_dir = ca_dir_path / "server_certs" / hostname
        expected_cert_path = server_certs_dir / f"{hostname}.crt"
        expected_key_path = server_certs_dir / f"{hostname}.key"

        if not force and (expected_cert_path.exists() or expected_key_path.exists()):
            return Error(
                error=f"Certificate for {hostname} already exists",
                recovery_suggestions="Use --force to overwrite existing certificate",
            )

        console_manager.print_processing(f"Creating server certificate for {hostname}")

        # Log detailed information
        logger.info(f"Hostname: {hostname}")
        logger.info(f"Validity: {validity_days} days")
        if san:
            logger.info(f"Subject Alternative Names: {', '.join(san)}")
            console_manager.print(f"Subject Alternative Names: {', '.join(san)}")

        # Prepare SAN list (hostname is automatically included)
        san_list = list(san) if san else []

        # Create the certificate
        cert_path, key_path = ca_manager.create_server_certificate(
            hostname=hostname,
            san_list=san_list,
            validity_days=validity_days,
        )

        # Display detailed results
        table = Table(title=f"Server Certificate Created for {hostname}")
        table.add_column("File Type", style="cyan")
        table.add_column("Path", style="green")

        table.add_row("Certificate", str(cert_path))
        table.add_row("Private Key", str(key_path))

        console_manager.safe_print(console_manager.console, table)

        message = f"Server certificate created successfully for {hostname}"
        if san:
            message += f" with SANs: {', '.join(san)}"
        message += f"\nValid for {validity_days} days"

        return Success(
            message=message, data={"cert_path": cert_path, "key_path": key_path}
        )

    except CAManagerError as e:
        return Error(error=f"Certificate creation failed: {e}", exception=e)
    except Exception as e:
        return Error(
            error=f"Unexpected error during certificate creation: {e}", exception=e
        )


def _check_certificate_status(
    cert_path: Path,
    cert_type: str,
    ca_manager: CAManager,
    days: int,
    status_table: Table,
) -> bool:
    """Check certificate status and add row to status table.

    Returns True if warnings were found (expired, expires soon, missing, or error).
    """
    warnings_found = False

    if cert_path.exists():
        try:
            cert_info = ca_manager.get_certificate_info(cert_path)

            if cert_info.is_expired:
                status = "✗ Expired"
                days_str = "Expired"
                warnings_found = True
            elif cert_info.expires_soon(days):
                status = "⚠ Expires Soon"
                remaining_days = (
                    cert_info.not_valid_after - datetime.now().astimezone()
                ).days
                days_str = str(remaining_days)
                warnings_found = True
            else:
                remaining_days = (
                    cert_info.not_valid_after - datetime.now().astimezone()
                ).days
                status = "✓ Valid"
                days_str = str(remaining_days)

        except Exception as e:
            status = "? Check Failed"
            days_str = f"Error: {e}"
            warnings_found = True
    else:
        status = "✗ Missing"
        days_str = "N/A"
        warnings_found = True

    status_table.add_row(cert_path.name, cert_type, status, days_str)
    return warnings_found


@ca_group.command("status")
@click.option(
    "--ca-dir",
    type=click.Path(exists=True),
    default=None,
    help="CA directory (default: ~/.config/vibectl/server/ca)",
)
@click.option(
    "--days", "-d", default=30, help="Days ahead to check for certificate expiry"
)
def ca_status(ca_dir: str | None, days: int) -> None:
    """Show CA and certificate status."""
    # Show CA status
    status_result = _show_ca_status(ca_dir, days)
    handle_result(status_result)


def _show_ca_status(ca_dir: str | None, days: int) -> Result:
    """Show the status of the CA and certificates."""
    # Determine CA directory
    if ca_dir is None:
        config_dir = ensure_config_dir("server")
        ca_dir_path = config_dir / "ca"
    else:
        ca_dir_path = Path(ca_dir)

    if not ca_dir_path.exists():
        return Error(
            error=f"CA directory not found: {ca_dir_path}",
            recovery_suggestions="Initialize CA first with: vibectl-server ca init",
        )

    # Create CAManager with targeted exception handling
    try:
        ca_manager = CAManager(ca_dir_path)
    except CAManagerError as e:
        return Error(error=f"CA manager initialization failed: {e}", exception=e)
    except Exception as e:
        return Error(
            error=f"Unexpected error initializing CA manager: {e}",
            exception=e,
        )

    console_manager.print("[blue]Certificate Authority Status[/blue]")
    console_manager.print(f"CA Directory: {ca_dir_path}")
    console_manager.print("")

    # Check CA structure and status
    root_ca_cert = ca_dir_path / "ca-root.crt"
    intermediate_ca_cert = ca_dir_path / "ca-intermediate.crt"
    certs_dir = ca_dir_path / "certs"

    # Create status table
    status_table = Table(title="CA Infrastructure Status")
    status_table.add_column("Certificate", style="cyan")
    status_table.add_column("Type", style="blue")
    status_table.add_column("Status", style="green")
    status_table.add_column("Days Until Expiry", style="yellow")

    warnings_found = False

    # Check root CA using helper
    warnings_found |= _check_certificate_status(
        root_ca_cert, "Root CA", ca_manager, days, status_table
    )

    # Check intermediate CA using helper
    warnings_found |= _check_certificate_status(
        intermediate_ca_cert, "Intermediate CA", ca_manager, days, status_table
    )

    # Check certificates directory status
    if certs_dir.exists():
        cert_files = list(certs_dir.glob("*.crt"))
        # Add a summary row for server certificates directory
        status_table.add_row(
            "Server Certs Dir",
            "Directory",
            f"✓ {len(cert_files)} certificates",
            "See below",
        )
    else:
        status_table.add_row("Server Certs Dir", "Directory", "✗ Missing", "N/A")
        warnings_found = True

    console_manager.safe_print(console_manager.console, status_table)

    # List server certificates if any exist
    if certs_dir.exists():
        cert_files = list(certs_dir.glob("*.crt"))
        if cert_files:
            console_manager.print("")
            cert_table = Table(title="Server Certificates")
            cert_table.add_column("Certificate", style="cyan")
            cert_table.add_column("Type", style="blue")
            cert_table.add_column("Status", style="green")
            cert_table.add_column("Days Until Expiry", style="yellow")

            for cert_file in sorted(cert_files):
                warnings_found |= _check_certificate_status(
                    cert_file, "Server", ca_manager, days, cert_table
                )

            console_manager.safe_print(console_manager.console, cert_table)

    message = "CA status displayed successfully"
    if warnings_found:
        message += " with warnings"

    return Success(message=message)


@ca_group.command("check-expiry")
@click.option(
    "--ca-dir",
    type=click.Path(exists=True),
    default=None,
    help="CA directory (default: ~/.config/vibectl/server/ca)",
)
@click.option(
    "--days",
    type=int,
    default=30,
    help="Days before expiry to warn about (default: 30)",
)
def ca_check_expiry(ca_dir: str | None, days: int) -> None:
    """Check for certificates that are expired or expiring soon."""
    # Check certificate expiry
    expiry_result = _check_certificate_expiry(ca_dir, days)
    handle_result(expiry_result)


def _check_certificate_expiry(ca_dir: str | None, days: int) -> Result:
    """Check for expired or expiring certificates."""
    # Determine CA directory
    if ca_dir is None:
        config_dir = ensure_config_dir("server")
        ca_dir_path = config_dir / "ca"
    else:
        ca_dir_path = Path(ca_dir)

    if not ca_dir_path.exists():
        return Error(
            error=f"CA directory not found: {ca_dir_path}",
            recovery_suggestions="Initialize CA first with: vibectl-server ca init",
        )

    # Create CAManager with targeted exception handling
    try:
        ca_manager = CAManager(ca_dir_path)
    except CAManagerError as e:
        return Error(error=f"CA manager initialization failed: {e}", exception=e)
    except Exception as e:
        return Error(
            error=f"Unexpected error initializing CA manager: {e}",
            exception=e,
        )

    console_manager.print(
        f"[blue]Certificate Expiry Check (threshold: {days} days)[/blue]"
    )
    console_manager.print("")

    # Create expiry table
    expiry_table = Table(title="Certificate Expiry Status")
    expiry_table.add_column("Certificate", style="cyan")
    expiry_table.add_column("Type", style="blue")
    expiry_table.add_column("Status", style="green")
    expiry_table.add_column("Days Until Expiry", style="yellow")

    # Check CA certificates using helper
    ca_certificates = [
        (ca_dir_path / "ca-root.crt", "Root CA"),
        (ca_dir_path / "ca-intermediate.crt", "Intermediate CA"),
    ]

    warnings_found = False

    # Check CA certificates using helper
    for cert_path, cert_type in ca_certificates:
        warnings_found |= _check_certificate_status(
            cert_path, cert_type, ca_manager, days, expiry_table
        )

    # Check server certificates using helper
    certs_dir = ca_dir_path / "certs"
    if certs_dir.exists():
        cert_files = list(certs_dir.glob("*.crt"))
        for cert_file in sorted(cert_files):
            warnings_found |= _check_certificate_status(
                cert_file, "Server", ca_manager, days, expiry_table
            )

    console_manager.safe_print(console_manager.console, expiry_table)

    if warnings_found:
        console_manager.print("")
        console_manager.print_warning("Some certificates are expired or expiring soon!")
        console_manager.print_note(
            "Use 'vibectl-server ca create-server-cert' to "
            "create new server certificates"
        )
        console_manager.print_note(
            "Consider renewing CA certificates if they are expiring"
        )

    message = "Certificate expiry check completed"
    if warnings_found:
        message += " with warnings"

    return Success(message=message)


def _build_config_overrides(
    host: str | None = None,
    port: int | None = None,
    model: str | None = None,
    max_workers: int | None = None,
    log_level: str | None = None,
    require_auth: bool = False,
    tls_overrides: dict[str, Any] | None = None,
    jwt_overrides: dict[str, Any] | None = None,
    acme_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build configuration overrides from CLI parameters and explicit overrides."""
    overrides: dict[str, Any] = {}

    # Build server section if any server parameters are provided
    server_params = {
        "host": host,
        "port": port,
        "default_model": model,
        "max_workers": max_workers,
        "log_level": log_level,
    }
    server_overrides = {k: v for k, v in server_params.items() if v is not None}
    if server_overrides:
        overrides["server"] = server_overrides

    # Build JWT section if authentication is enabled
    if require_auth:
        overrides["jwt"] = {"enabled": True}

    # Add explicit overrides
    if tls_overrides:
        overrides["tls"] = tls_overrides
    if jwt_overrides:
        if "jwt" in overrides:
            overrides["jwt"].update(jwt_overrides)
        else:
            overrides["jwt"] = jwt_overrides
    if acme_overrides:
        overrides["acme"] = acme_overrides

    return overrides


def _load_and_validate_config(config_path: Path | None, overrides: dict) -> Result:
    """Load configuration with CLI overrides and validation."""
    # Create server config instance
    server_config_manager = ServerConfig(config_path)

    # Load base configuration
    config_result = server_config_manager.load()
    if isinstance(config_result, Error):
        return config_result

    server_config = config_result.data if config_result.data is not None else {}

    # Apply overrides using the config manager's deep merge
    merged_config = server_config_manager.apply_overrides(server_config, overrides)

    # Validate configuration using the config manager
    validation_result = server_config_manager.validate(merged_config)
    if isinstance(validation_result, Error):
        return validation_result

    return Success(data=validation_result.data)


def _update_logging_level_from_config(server_config: dict) -> None:
    """Update logging level from server configuration."""
    log_level = server_config.get("server", {}).get("log_level")
    if log_level:
        update_logging_level(log_level)


def _create_and_start_server_common(server_config: dict) -> Result:
    """Common server creation and startup logic for all serve commands."""
    try:
        # Update logging level from config first
        _update_logging_level_from_config(server_config)

        # Log server configuration
        logger.info("Starting vibectl LLM proxy server")
        logger.info(f"Host: {server_config['server']['host']}")
        logger.info(f"Port: {server_config['server']['port']}")
        logger.info(f"Max workers: {server_config['server']['max_workers']}")

        auth_status = "enabled" if server_config["jwt"]["enabled"] else "disabled"
        logger.info(f"Authentication: {auth_status}")

        tls_status = "enabled" if server_config["tls"]["enabled"] else "disabled"
        logger.info(f"TLS: {tls_status}")

        # Handle ACME certificate provisioning if enabled
        if server_config["acme"]["enabled"]:
            logger.info("ACME: enabled")
            if server_config["acme"]["email"]:
                logger.info(f"ACME email: {server_config['acme']['email']}")
            if server_config["acme"]["domains"]:
                logger.info(
                    f"ACME domains: {', '.join(server_config['acme']['domains'])}"
                )
            if server_config["acme"].get("directory_url"):
                logger.info(f"ACME directory: {server_config['acme']['directory_url']}")
            else:
                logger.info(f"ACME directory: {LETSENCRYPT_PRODUCTION} (default)")

            # Validate ACME configuration
            email = server_config["acme"]["email"]
            if not email or not email.strip():
                return Error(
                    error="ACME enabled but no email provided. "
                    "Use --acme-email or set acme.email in config."
                )
            if not server_config["acme"]["domains"]:
                return Error(
                    error="ACME enabled but no domains provided. "
                    "Use --acme-domain or set acme.domains in config."
                )

            # Use async ACME architecture
            return _create_and_start_server_with_async_acme(server_config)
        else:
            logger.info("ACME: disabled")

        if server_config["server"]["default_model"]:
            logger.info(f"Default model: {server_config['server']['default_model']}")
        else:
            logger.info("No default model configured - clients must specify model")

        # Create the server
        # Handle TLS configuration safely
        if server_config["tls"]["enabled"]:
            cert_file = server_config["tls"].get("cert_file")
            key_file = server_config["tls"].get("key_file")
        else:
            cert_file = None
            key_file = None

        server = create_server(
            host=server_config["server"]["host"],
            port=server_config["server"]["port"],
            default_model=server_config["server"]["default_model"],
            max_workers=server_config["server"]["max_workers"],
            require_auth=server_config["jwt"]["enabled"],
            use_tls=server_config["tls"]["enabled"],
            cert_file=cert_file,
            key_file=key_file,
            hsts_settings=server_config["tls"].get("hsts", {}),
        )

        logger.info("Server created successfully")

        # Start serving (this will block until interrupted)
        server.serve_forever()

        return Success()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
        return Success()
    except Exception as e:
        return Error(error=f"Server startup failed: {e}", exception=e)


def _create_and_start_server_with_async_acme(server_config: dict) -> Result:
    """Create and start server with async ACME certificate management."""
    import asyncio

    # Check if we're already in an event loop
    try:
        asyncio.get_running_loop()
        # We're in an event loop, run in a thread
        import threading

        result_container: list[Result | None] = [None]
        exception_container: list[Exception | None] = [None]

        def run_async_server() -> None:
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                result_container[0] = new_loop.run_until_complete(
                    _async_acme_server_main(server_config)
                )
            except Exception as e:
                exception_container[0] = e
            finally:
                new_loop.close()

        # Run in separate thread
        thread = threading.Thread(target=run_async_server)
        thread.start()
        thread.join()

        if exception_container[0]:
            raise exception_container[0]

        return result_container[0] or Error(
            error="Async server thread returned no result"
        )

    except RuntimeError:
        # No event loop running, we can use asyncio normally
        return asyncio.run(_async_acme_server_main(server_config))


async def _async_acme_server_main(server_config: dict) -> Result:
    """Main async function for ACME server setup."""
    try:
        # Update logging level from config first
        _update_logging_level_from_config(server_config)

        from .acme_manager import ACMEManager

        acme_config = server_config["acme"]
        challenge_config = acme_config.get("challenge", {})
        challenge_type = challenge_config.get("type", "tls-alpn-01")

        challenge_server = None
        tls_alpn_challenge_server = None

        # Start appropriate challenge server based on challenge type
        if challenge_type == "http-01":
            from .http_challenge_server import HTTPChallengeServer

            # Get HTTP-01 challenge configuration from acme.challenge section
            http_host = challenge_config.get("http_host", "0.0.0.0")
            http_port = challenge_config.get("http_port", 80)

            logger.info(
                f"Starting HTTP challenge server on {http_host}:{http_port} "
                "for HTTP-01 challenges"
            )

            # Start HTTP challenge server
            challenge_server = HTTPChallengeServer(
                host=http_host,
                port=http_port,
                hsts_settings=server_config.get("tls", {}).get("hsts", {}),
                redirect_http=True,
            )
            await challenge_server.start()

            # Wait for challenge server to be ready
            if not await challenge_server.wait_until_ready():
                return Error(error="HTTP challenge server failed to start")

            logger.info("HTTP challenge server ready")

        elif challenge_type == "tls-alpn-01":
            from .alpn_multiplexer import create_alpn_multiplexer_for_acme
            from .tls_alpn_challenge_server import TLSALPNChallengeServer

            logger.info("Setting up TLS-ALPN-01 with ALPN multiplexing on port 443")

            # Create TLS-ALPN challenge manager (does not bind to any port)
            tls_alpn_challenge_server = TLSALPNChallengeServer()

        else:
            logger.info(
                f"Using {challenge_type} challenges - no challenge server needed"
            )

        try:
            # Handle TLS-ALPN-01 differently - use ALPN multiplexing
            if challenge_type == "tls-alpn-01":
                # For TLS-ALPN-01, we need to create a multiplexed server
                # Create gRPC server without starting it
                server = _create_grpc_server_with_temp_certs(server_config)

                # Get certificate paths for ALPN multiplexer
                cert_file = server_config["tls"].get("cert_file")
                key_file = server_config["tls"].get("key_file")

                if not cert_file or not key_file:
                    return Error(error="TLS certificate files required for TLS-ALPN-01")

                # Create ALPN multiplexer that handles both gRPC and TLS-ALPN-01
                alpn_multiplexer = await create_alpn_multiplexer_for_acme(
                    host=server_config["server"]["host"],
                    port=server_config["server"]["port"],  # Should be 443
                    cert_file=cert_file,
                    key_file=key_file,
                    grpc_server=server,
                    tls_alpn_server=tls_alpn_challenge_server,
                    grpc_internal_port=50051,  # Internal port for gRPC server
                )

                logger.info(
                    "ALPN multiplexer started on port 443 for gRPC + TLS-ALPN-01"
                )

                _signal_container_ready()

            else:
                # For other challenge types, start gRPC server normally
                server = _create_grpc_server_with_temp_certs(server_config)
                server.start()
                logger.info("gRPC server started with temporary certificates")

                _signal_container_ready()

            # Start ACME manager in background
            if challenge_type == "tls-alpn-01":
                logger.debug(
                    "Creating ACME manager for TLS-ALPN-01 with "
                    f"server_config['tls']: {server_config['tls']}"
                )
                acme_manager = ACMEManager(
                    challenge_server=None,  # No challenge server needed for TLS-ALPN-01
                    acme_config=server_config["acme"],
                    # Hot-reload the multiplexer's certificate
                    # once ACME provisioning succeeds
                    cert_reload_callback=lambda cert, key: _reload_server_certificates(
                        alpn_multiplexer, cert, key
                    ),
                    tls_alpn_challenge_server=tls_alpn_challenge_server,
                )
            else:
                acme_manager = ACMEManager(
                    challenge_server=challenge_server,
                    acme_config=server_config["acme"],
                    cert_reload_callback=lambda cert, key: _reload_server_certificates(
                        server, cert, key
                    ),
                )

            acme_start_result = await acme_manager.start()
            if isinstance(acme_start_result, Error):
                logger.error(f"ACME manager failed to start: {acme_start_result.error}")
                return acme_start_result

            logger.info("ACME manager started, certificate provisioning in progress")

            # Main server loop - wait for termination
            try:
                if challenge_type == "tls-alpn-01":
                    # For TLS-ALPN-01, wait indefinitely
                    # (multiplexer handles connections)
                    await asyncio.Event().wait()
                else:
                    # For HTTP-01, we need to wait asynchronously to avoid blocking
                    # the event loop that the HTTP challenge server depends on
                    shutdown_event = asyncio.Event()

                    def signal_shutdown() -> None:
                        shutdown_event.set()

                    # Set up signal handlers for graceful shutdown
                    import signal

                    for sig in [signal.SIGTERM, signal.SIGINT]:
                        signal.signal(sig, lambda signum, frame: signal_shutdown())

                    # Wait for shutdown signal while keeping event loop alive
                    await shutdown_event.wait()
            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt, shutting down...")

            return Success()

        finally:
            # Cleanup
            if "acme_manager" in locals():
                await acme_manager.stop()
            if "server" in locals():
                server.stop()
            if challenge_server:
                await challenge_server.stop()
            if "alpn_multiplexer" in locals():
                await alpn_multiplexer.stop()
            if tls_alpn_challenge_server:
                await tls_alpn_challenge_server.stop()

    except Exception as e:
        return Error(error=f"Async ACME server startup failed: {e}", exception=e)


def _create_grpc_server_with_temp_certs(server_config: dict) -> Any:
    """Create gRPC server with temporary certificates that can be reloaded later."""
    from vibectl.config_utils import get_config_dir

    from .cert_utils import (
        ensure_certificate_exists,
        generate_self_signed_certificate,
        get_default_cert_paths,
    )
    from .grpc_server import GRPCServer

    # Create temporary/default certificate if needed
    config_dir = get_config_dir("server")
    temp_cert_file, temp_key_file = get_default_cert_paths(config_dir)

    # Ensure temp certificates exist
    hostname = server_config["server"]["host"]
    if hostname in ("0.0.0.0", "::"):
        hostname = "localhost"

    # For TLS-ALPN-01, include ACME domains in the bootstrap certificate
    # This allows Pebble to connect during initial challenge validation
    if (
        server_config.get("acme", {}).get("enabled")
        and server_config.get("acme", {}).get("challenge", {}).get("type")
        == "tls-alpn-01"
        and server_config.get("acme", {}).get("domains")
    ):
        logger.info("Generating self-signed certificate for development use")
        acme_domains = server_config["acme"]["domains"]
        logger.info(f"Including ACME domains in bootstrap certificate: {acme_domains}")

        # Use the first ACME domain as the primary hostname
        primary_domain = acme_domains[0]

        # Generate certificate with all ACME domains as SANs
        generate_self_signed_certificate(
            hostname=primary_domain,
            cert_file=temp_cert_file,
            key_file=temp_key_file,
            days_valid=365,
            additional_sans=[
                *acme_domains,
                hostname,
                "localhost",
            ],  # Include original hostname and localhost
        )

        logger.info(
            "Generated bootstrap certificate with SANs for: "
            f"{', '.join([*acme_domains, hostname, 'localhost'])}"
        )
    else:
        ensure_certificate_exists(temp_cert_file, temp_key_file, hostname=hostname)

    # Create server with temp certs
    return GRPCServer(
        host=server_config["server"]["host"],
        port=server_config["server"]["port"],
        default_model=server_config["server"]["default_model"],
        max_workers=server_config["server"]["max_workers"],
        require_auth=server_config["jwt"]["enabled"],
        use_tls=server_config["tls"]["enabled"],
        cert_file=temp_cert_file,
        key_file=temp_key_file,
        hsts_settings=server_config["tls"].get("hsts", {}),
    )


def _reload_server_certificates(target: Any, cert_file: str, key_file: str) -> None:
    """Hot-reload certificates for a running server component.

    The ACME manager invokes this callback after new certificates have been
    written to disk.  For the TLS-ALPN-01 flow we terminate TLS inside the
    ``ALPNMultiplexer`` which owns an ``ssl.SSLContext`` instance.  That
    context supports live reloading via ``SSLContext.load_cert_chain`` - we
    simply need to re-load the new files.  If *target* does not expose an
    ``_ssl_context`` attribute we fall back to logging a warning (gRPC's
    built-in server credentials cannot be reloaded dynamically in
    python-grpc).
    """

    logger.info("Certificate reload requested: cert=%s, key=%s", cert_file, key_file)

    try:
        # Fast-path: ALPNMultiplexer (has `_ssl_context` attribute)
        ssl_ctx = getattr(target, "_ssl_context", None)
        if ssl_ctx is not None:
            ssl_ctx.load_cert_chain(cert_file, key_file)

            # Persist the new paths on the multiplexer for future restores
            if hasattr(target, "cert_file"):
                target.cert_file = cert_file
            if hasattr(target, "key_file"):
                target.key_file = key_file

            logger.info("🔄 Hot certificate reload completed successfully")
            return

        # For GRPCServer, we need to restart it with new certificates
        # since python-grpc doesn't support hot certificate reloading
        from .grpc_server import GRPCServer

        if isinstance(target, GRPCServer):
            logger.info("🔄 Restarting gRPC server with new ACME certificates...")

            # Stop the current server
            target.stop(grace_period=2.0)

            # Update certificate paths
            target.cert_file = cert_file
            target.key_file = key_file

            # Restart the server with new certificates
            target.start()

            logger.info("✅ gRPC server restarted successfully with new certificates")
            return

        # Fallback / unsupported targets
        logger.warning(
            "Hot certificate reload not supported for target %s - restart required",
            type(target).__name__,
        )

    except Exception as exc:  # pragma: no cover - best-effort reload
        logger.error("❌ Failed to hot-reload certificates: %s", exc)


def determine_serve_mode(config: dict) -> ServeMode:
    """Determine which specialized serve command to use based on configuration."""
    tls_enabled = config.get("tls", {}).get("enabled", False)
    acme_enabled = config.get("acme", {}).get("enabled", False)

    if not tls_enabled:
        return ServeMode.INSECURE
    elif acme_enabled:
        return ServeMode.ACME
    elif config.get("tls", {}).get("cert_file") and config.get("tls", {}).get(
        "key_file"
    ):
        return ServeMode.CUSTOM
    else:
        # Default to CA mode for TLS without explicit cert files
        return ServeMode.CA


@cli.command(name="serve-insecure")
@common_server_options()
def serve_insecure(
    host: str | None,
    port: int | None,
    model: str | None,
    max_workers: int | None,
    log_level: str | None,
    require_auth: bool,
    config: str | None,
) -> None:
    """Start insecure HTTP server (development only)."""

    # Build configuration overrides using helper
    overrides = _build_config_overrides(
        host=host,
        port=port,
        model=model,
        max_workers=max_workers,
        log_level=log_level,
        require_auth=require_auth,
        tls_overrides={"enabled": False},  # Force TLS off
        acme_overrides={"enabled": False},  # Force ACME off
    )

    config_path = Path(config) if config else None
    config_result = _load_and_validate_config(config_path, overrides)
    if isinstance(config_result, Error):
        handle_result(config_result)
        return

    server_config = config_result.data
    if server_config is None:
        handle_result(Error(error="Failed to load server configuration"))
        return

    # Ensure server_config is a dict type for mypy
    assert isinstance(server_config, dict), "server_config must be a dict"

    # Security warning for insecure mode
    console_manager.print_warning("⚠️  Running in INSECURE mode - no TLS encryption!")
    console_manager.print_note(
        "This mode should only be used for development or internal networks"
    )

    result = _create_and_start_server_common(server_config)
    handle_result(result)


@cli.command(name="serve-ca")
@common_server_options()
@click.option("--ca-dir", type=click.Path(), help="CA directory path")
@click.option("--hostname", default="localhost", help="Certificate hostname")
@click.option("--san", multiple=True, help="Subject Alternative Names")
@click.option(
    "--validity-days", type=int, default=90, help="Certificate validity in days"
)
def serve_ca(
    host: str | None,
    port: int | None,
    model: str | None,
    max_workers: int | None,
    log_level: str | None,
    require_auth: bool,
    config: str | None,
    ca_dir: str | None,
    hostname: str,
    san: tuple[str, ...],
    validity_days: int,
) -> None:
    """Start server with private CA certificates."""

    # Determine CA directory
    if ca_dir is None:
        config_dir = ensure_config_dir("server")
        ca_dir_path = config_dir / "ca"
    else:
        ca_dir_path = Path(ca_dir)

    if not ca_dir_path.exists():
        handle_result(
            Error(
                error=f"CA directory not found: {ca_dir_path}",
                recovery_suggestions="Initialize CA first with: vibectl-server ca init",
            )
        )
        return

    # Auto-create server certificate for the specified hostname
    try:
        ca_manager = CAManager(ca_dir_path)
        cert_path, key_path = ca_manager.create_server_certificate(
            hostname=hostname, san_list=list(san), validity_days=validity_days
        )

        console_manager.print_success(f"✅ Using CA certificate for {hostname}")

    except Exception as e:
        handle_result(Error(error=f"Failed to create server certificate: {e}"))
        return

    # Build configuration overrides using helper
    overrides = _build_config_overrides(
        host=host,
        port=port,
        model=model,
        max_workers=max_workers,
        log_level=log_level,
        require_auth=require_auth,
        tls_overrides={
            "enabled": True,
            "cert_file": str(cert_path),
            "key_file": str(key_path),
        },
        acme_overrides={"enabled": False},
    )

    config_path = Path(config) if config else None
    config_result = _load_and_validate_config(config_path, overrides)
    if isinstance(config_result, Error):
        handle_result(config_result)
        return

    server_config = config_result.data
    if server_config is None:
        handle_result(Error(error="Failed to load server configuration"))
        return

    # Ensure server_config is a dict type for mypy
    assert isinstance(server_config, dict), "server_config must be a dict"

    result = _create_and_start_server_common(server_config)
    handle_result(result)


@cli.command(name="serve-acme")
@common_server_options()
@click.option("--email", required=True, help="ACME account email")
@click.option(
    "--domain",
    multiple=True,
    required=True,
    help="Certificate domain (multiple allowed)",
)
@click.option(
    "--directory-url",
    help="ACME directory URL (defaults to Let's Encrypt production)",
)
@click.option(
    "--challenge-type",
    type=click.Choice(["http-01", "dns-01", "tls-alpn-01"]),
    default="tls-alpn-01",
    help="Challenge type",
)
def serve_acme(
    host: str | None,
    port: int | None,
    model: str | None,
    max_workers: int | None,
    log_level: str | None,
    require_auth: bool,
    config: str | None,
    email: str,
    domain: tuple[str, ...],
    directory_url: str | None,
    challenge_type: str,
) -> None:
    """Start server with Let's Encrypt ACME certificates."""

    # Build configuration overrides using helper
    # Default to port 443 for ACME/TLS if no port specified
    acme_port = port if port is not None else 443

    acme_overrides = {
        "enabled": True,
        "email": email,
        "domains": list(domain),
        "challenge": {"type": challenge_type},
    }

    # Add directory_url if provided
    if directory_url is not None:
        acme_overrides["directory_url"] = directory_url

    overrides = _build_config_overrides(
        host=host,
        port=acme_port,
        model=model,
        max_workers=max_workers,
        log_level=log_level,
        require_auth=require_auth,
        tls_overrides={"enabled": True},
        acme_overrides=acme_overrides,
    )

    config_path = Path(config) if config else None
    config_result = _load_and_validate_config(config_path, overrides)
    if isinstance(config_result, Error):
        handle_result(config_result)
        return

    server_config = config_result.data
    if server_config is None:
        handle_result(Error(error="Failed to load server configuration"))
        return

    # Ensure server_config is a dict type for mypy
    assert isinstance(server_config, dict), "server_config must be a dict"

    result = _create_and_start_server_common(server_config)
    handle_result(result)


@cli.command(name="serve-custom")
@common_server_options()
@click.option(
    "--cert-file",
    required=True,
    type=click.Path(exists=True),
    help="TLS certificate file path",
)
@click.option(
    "--key-file",
    required=True,
    type=click.Path(exists=True),
    help="TLS private key file path",
)
@click.option(
    "--ca-bundle-file",
    type=click.Path(exists=True),
    help="CA bundle for client verification",
)
def serve_custom(
    host: str | None,
    port: int | None,
    model: str | None,
    max_workers: int | None,
    log_level: str | None,
    require_auth: bool,
    config: str | None,
    cert_file: str,
    key_file: str,
    ca_bundle_file: str | None,
) -> None:
    """Start server with custom TLS certificates."""

    # Prepare TLS overrides with cert files
    tls_overrides = {
        "enabled": True,
        "cert_file": cert_file,
        "key_file": key_file,
    }

    if ca_bundle_file:
        tls_overrides["ca_bundle_file"] = ca_bundle_file

    # Build configuration overrides using helper
    overrides = _build_config_overrides(
        host=host,
        port=port,
        model=model,
        max_workers=max_workers,
        log_level=log_level,
        require_auth=require_auth,
        tls_overrides=tls_overrides,
        acme_overrides={"enabled": False},
    )

    config_path = Path(config) if config else None
    config_result = _load_and_validate_config(config_path, overrides)
    if isinstance(config_result, Error):
        handle_result(config_result)
        return

    server_config = config_result.data
    if server_config is None:
        handle_result(Error(error="Failed to load server configuration"))
        return

    # Ensure server_config is a dict type for mypy
    assert isinstance(server_config, dict), "server_config must be a dict"

    result = _create_and_start_server_common(server_config)
    handle_result(result)


@cli.command()
@click.option("--config", type=click.Path(), help="Configuration file path")
@click.pass_context
def serve(ctx: click.Context, config: str | None) -> None:
    """Start the gRPC server with intelligent routing."""

    # Load config to determine routing
    config_path = Path(config) if config else None
    config_result = load_server_config(config_path)

    if isinstance(config_result, Error):
        handle_result(config_result)
        return

    server_config = config_result.data
    if server_config is None:
        handle_result(Error(error="Failed to load server configuration"))
        return

    mode = determine_serve_mode(server_config)

    console_manager.print_note(f"🔍 Detected configuration mode: {mode}")

    # Route to appropriate specialized command
    if mode == ServeMode.INSECURE:
        ctx.invoke(serve_insecure, config=config)
    elif mode == ServeMode.CA:
        # Extract CA configuration with proper defaults
        ca_dir = None  # Let serve_ca determine the default CA directory
        hostname = "localhost"  # Default hostname
        san = ()  # Empty tuple for SANs
        validity_days = 90  # Default validity

        ctx.invoke(
            serve_ca,
            config=config,
            ca_dir=ca_dir,
            hostname=hostname,
            san=san,
            validity_days=validity_days,
        )
    elif mode == ServeMode.ACME:
        # For ACME mode, use the loaded config directly to avoid CLI override issues
        # that can cause port 443 default to override config file port values
        result = _create_and_start_server_common(server_config)
        handle_result(result)
    elif mode == ServeMode.CUSTOM:
        # Extract certificate paths from config for serve-custom
        cert_file = server_config.get("tls", {}).get("cert_file")
        key_file = server_config.get("tls", {}).get("key_file")
        ca_bundle_file = server_config.get("tls", {}).get("ca_bundle_file")

        if not cert_file or not key_file:
            handle_result(
                Error(
                    error="serve-custom mode requires cert_file and key_file "
                    "in configuration",
                    recovery_suggestions="Set tls.cert_file and tls.key_file in your "
                    "config file",
                )
            )
            return

        # Pass required arguments to serve_custom
        ctx.invoke(
            serve_custom,
            config=config,
            cert_file=cert_file,
            key_file=key_file,
            ca_bundle_file=ca_bundle_file,
        )
    else:
        handle_result(Error(error=f"Unknown serve mode: {mode}"))


def main() -> int:
    """Main entry point for the server.

    Returns:
        int: Exit code (0 for success, non-zero for error)
    """
    try:
        # Initialize logging first, like cli.py
        init_logging()

        # Run the CLI with centralized exception handling
        cli(standalone_mode=False)
        return 0

    except Exception as e:
        handle_exception(e)
        return 1


if __name__ == "__main__":
    sys.exit(main())


def _signal_container_ready(path: str = "/tmp/ready") -> None:
    """Create a readiness file so an exec/readinessProbe can detect readiness."""

    try:
        from pathlib import Path

        ready_file = Path(path)
        ready_file.touch(exist_ok=True)
        logger.info("📣 Container readiness signalled (created %s)", path)
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("⚠️ Failed to create readiness file %s: %s", path, exc)
