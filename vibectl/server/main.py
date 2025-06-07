#!/usr/bin/env python3
"""
Main entry point for the vibectl gRPC LLM proxy server.

This script provides a standalone server that can be run independently
of the main vibectl CLI, reducing complexity and enabling dedicated
server deployment scenarios.
"""

import sys
from datetime import datetime
from pathlib import Path

import click
from rich.table import Table

from vibectl.config_utils import (
    ensure_config_dir,
    get_config_dir,
    load_yaml_config,
)
from vibectl.console import console_manager
from vibectl.logutil import init_logging, logger
from vibectl.types import Error, Result, Success
from vibectl.utils import handle_exception

from .ca_manager import CAManager, CAManagerError, setup_private_ca
from .grpc_server import create_server
from .jwt_auth import JWTAuthManager, load_config_with_generation

# Graceful shutdown handling
shutdown_event = False


def signal_handler(signum: int, frame: object) -> None:
    """Handle shutdown signals gracefully."""
    global shutdown_event
    logger.info("Received shutdown signal %s, shutting down gracefully...", signum)
    shutdown_event = True


def get_server_config_path() -> Path:
    """Get the path to the server configuration file.

    Returns:
        Path to the server configuration file
    """
    return get_config_dir("server") / "config.yaml"


def get_default_server_config() -> dict:
    """Get the default server configuration.

    This function provides the default configuration values used by both
    load_server_config() and create_default_config() to avoid duplication.

    Returns:
        dict: Default server configuration
    """
    return {
        "server": {
            "host": "0.0.0.0",
            "port": 50051,
            "default_model": "anthropic/claude-3-7-sonnet-latest",
            "max_workers": 10,
            "log_level": "INFO",
        },
        "tls": {
            "enabled": False,
            "cert_file": None,
            "key_file": None,
            "ca_bundle_file": None,
        },
        "jwt": {
            "enabled": False,
            "secret_key": None,  # Will use environment or generate if None
            "secret_key_file": None,  # Path to file containing secret key
            "algorithm": "HS256",
            "issuer": "vibectl-server",
            "expiration_days": 30,
        },
    }


def load_server_config(config_path: Path | None = None) -> Result:
    """Load server configuration from file or create defaults.

    Args:
        config_path: Optional path to configuration file

    Returns:
        Success with configuration dict or Error
    """
    if config_path is None:
        config_path = get_server_config_path()

    try:
        # Use shared config loading utility with deep merge
        config = load_yaml_config(config_path, get_default_server_config())
        return Success(data=config)
    except ValueError as e:
        logger.error("Failed to load config from %s: %s", config_path, e)
        logger.info("Using default configuration")
        return Success(data=get_default_server_config())


def create_default_config(config_path: Path | None = None) -> Result:
    """Create a default configuration file.

    Args:
        config_path: Optional path for the configuration file

    Returns:
        Success or Error
    """
    import yaml

    if config_path is None:
        config_path = get_server_config_path()

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        default_config = get_default_server_config()

        with config_path.open("w") as f:
            yaml.dump(default_config, f, default_flow_style=False, sort_keys=False)

        return Success(message=f"Created default config at {config_path}")
    except Exception as e:
        return Error(
            error=f"Failed to create config file at {config_path}: {e}", exception=e
        )


def parse_duration(duration_str: str) -> Result:
    """Parse a duration string into days.

    Args:
        duration_str: Duration string (e.g., '30d', '6m', '1y', or just '30')

    Returns:
        Success with number of days or Error
    """
    try:
        duration_str = duration_str.strip().lower()

        # If it's just a number, treat as days
        if duration_str.isdigit():
            return Success(data=int(duration_str))

        # Parse with suffix
        if len(duration_str) < 2:
            return Error(
                error=f"Invalid duration format: {duration_str}. "
                "Use format like '30d', '6m', '1y', or just a number for days"
            )

        value_str = duration_str[:-1]
        suffix = duration_str[-1]

        try:
            value = int(value_str)
        except ValueError:
            return Error(
                error=f"Invalid duration format: {duration_str}. "
                "Use format like '30d', '6m', '1y', or just a number for days"
            )

        if suffix == "d":
            return Success(data=value)
        elif suffix == "m":
            return Success(data=value * 30)  # Approximate month as 30 days
        elif suffix == "y":
            return Success(data=value * 365)  # Approximate year as 365 days
        else:
            return Error(
                error=f"Invalid duration suffix: {suffix}. "
                "Use 'd' for days, 'm' for months, 'y' for years"
            )
    except Exception as e:
        return Error(error=f"Failed to parse duration: {e}", exception=e)


def validate_config(host: str, port: int, max_workers: int) -> Result:
    """Validate server configuration values.

    Args:
        host: Host address to bind to
        port: Port number to bind to
        max_workers: Maximum number of worker threads

    Returns:
        Success or Error
    """
    try:
        if not isinstance(port, int) or port < 1 or port > 65535:
            return Error(
                error=f"Invalid port number: {port}. Must be between 1 and 65535"
            )

        if not isinstance(max_workers, int) or max_workers < 1:
            return Error(error=f"Invalid max_workers: {max_workers}. Must be >= 1")

        # Host validation would go here if needed
        return Success()
    except Exception as e:
        return Error(error=f"Configuration validation failed: {e}", exception=e)


def handle_result(result: Result) -> None:
    """Handle command results using console manager.

    Args:
        result: The result to handle
    """
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

    sys.exit(exit_code)


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """vibectl gRPC LLM proxy server"""
    if ctx.invoked_subcommand is None:
        # Default to serve command
        ctx.invoke(serve)


@cli.command()
@click.option("--host", default=None, help="Host to bind the gRPC server to")
@click.option("--port", type=int, default=None, help="Port to bind the gRPC server to")
@click.option(
    "--model",
    default=None,
    help="Default LLM model to use (if not specified, server will require "
    "clients to specify model)",
)
@click.option(
    "--max-workers", type=int, default=None, help="Maximum number of worker threads"
)
@click.option(
    "--log-level",
    type=click.Choice(
        ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], case_sensitive=False
    ),
    default=None,
    help="Logging level",
)
@click.option(
    "--require-auth/--no-require-auth",
    default=None,
    help="Require JWT authentication for all server requests",
)
@click.option(
    "--tls/--no-tls",
    default=None,
    help="Enable or disable TLS encryption (default: disabled for development)",
)
@click.option(
    "--cert-file",
    type=click.Path(exists=False),
    default=None,
    help="Path to TLS certificate file (auto-generated if not specified)",
)
@click.option(
    "--key-file",
    type=click.Path(exists=False),
    default=None,
    help="Path to TLS private key file (auto-generated if not specified)",
)
@click.option(
    "--generate-certs",
    is_flag=True,
    default=False,
    help="Force regeneration of TLS certificates (for development)",
)
@click.option(
    "--config", help="Path to server configuration file (not yet implemented)"
)
def serve(
    host: str | None,
    port: int | None,
    model: str | None,
    max_workers: int | None,
    log_level: str | None,
    require_auth: bool | None,
    tls: bool | None,
    cert_file: str | None,
    key_file: str | None,
    generate_certs: bool,
    config: str | None,
) -> None:
    """Start the gRPC server (default command)"""
    # Load configuration from file first
    config_path = Path(config) if config else None
    config_result = load_server_config(config_path)
    if isinstance(config_result, Error):
        handle_result(config_result)
        return

    # Cast from Any to dict since we know load_server_config returns dict on success
    server_config = config_result.data if config_result.data is not None else {}

    # Apply CLI overrides to server configuration
    if host is not None:
        server_config["server"]["host"] = host
    if port is not None:
        server_config["server"]["port"] = port
    if model is not None:
        server_config["server"]["default_model"] = model
    if max_workers is not None:
        server_config["server"]["max_workers"] = max_workers
    if log_level is not None:
        server_config["server"]["log_level"] = log_level
    if require_auth is not None:
        server_config["jwt"]["enabled"] = require_auth
    if tls is not None:
        server_config["tls"]["enabled"] = tls
    if cert_file is not None:
        server_config["tls"]["cert_file"] = cert_file
    if key_file is not None:
        server_config["tls"]["key_file"] = key_file

    # Debug: Log loaded configuration
    logger.info(f"Config loaded from: {config_path or 'default path'}")
    logger.info(f"Config use_tls: {server_config['tls']['enabled']}")
    logger.info(f"Config require_auth: {server_config['jwt']['enabled']}")

    # Validate configuration
    validation_result = validate_config(
        server_config["server"]["host"],
        server_config["server"]["port"],
        server_config["server"]["max_workers"],
    )
    if isinstance(validation_result, Error):
        handle_result(validation_result)
        return

    logger.info("Starting vibectl LLM proxy server")
    logger.info(f"Host: {server_config['server']['host']}")
    logger.info(f"Port: {server_config['server']['port']}")
    logger.info(f"Max workers: {server_config['server']['max_workers']}")
    auth_status = "enabled" if server_config["jwt"]["enabled"] else "disabled"
    logger.info(f"Authentication: {auth_status}")
    tls_status = "enabled" if server_config["tls"]["enabled"] else "disabled"
    logger.info(f"TLS: {tls_status}")

    if server_config["server"]["default_model"]:
        logger.info(f"Default model: {server_config['server']['default_model']}")
    else:
        logger.info("No default model configured - clients must specify model")

    # Handle certificate generation if requested
    if generate_certs and server_config["tls"]["enabled"]:
        cert_result = _handle_certificate_generation(server_config)
        if isinstance(cert_result, Error):
            handle_result(cert_result)
            return

    # Create and start the server
    server_result = _create_and_start_server(server_config)
    if isinstance(server_result, Error):
        handle_result(server_result)
        return

    logger.info("Server stopped")


def _handle_certificate_generation(server_config: dict) -> Result:
    """Handle certificate generation for TLS.

    Args:
        server_config: Server configuration dictionary

    Returns:
        Success or Error
    """
    try:
        from .cert_utils import ensure_certificate_exists, get_default_cert_paths

        cert_file = server_config["tls"]["cert_file"]
        key_file = server_config["tls"]["key_file"]

        # Use default paths if not specified
        if cert_file is None or key_file is None:
            config_dir = get_config_dir("server")
            default_cert_file, default_key_file = get_default_cert_paths(config_dir)
            cert_file = cert_file or default_cert_file
            key_file = key_file or default_key_file

        hostname = server_config["server"]["host"]
        if hostname in ("0.0.0.0", "::"):
            hostname = "localhost"

        logger.info("Regenerating TLS certificates...")
        ensure_certificate_exists(
            str(cert_file), str(key_file), hostname=hostname, regenerate=True
        )
        return Success(message="TLS certificates regenerated successfully")
    except Exception as e:
        return Error(error=f"Certificate generation failed: {e}", exception=e)


def _create_and_start_server(server_config: dict) -> Result:
    """Create and start the gRPC server.

    Args:
        server_config: Server configuration dictionary

    Returns:
        Success or Error
    """
    try:
        # Create the server
        server = create_server(
            host=server_config["server"]["host"],
            port=server_config["server"]["port"],
            default_model=server_config["server"]["default_model"],
            max_workers=server_config["server"]["max_workers"],
            require_auth=server_config["jwt"]["enabled"],
            use_tls=server_config["tls"]["enabled"],
            cert_file=server_config["tls"]["cert_file"],
            key_file=server_config["tls"]["key_file"],
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
    """Generate a JWT token.

    Args:
        subject: Token subject
        expiration_days: Token expiration in days
        output: Output file path or None for stdout

    Returns:
        Success or Error
    """
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
    """Initialize server configuration directory and files"""
    try:
        config_dir = ensure_config_dir("server")
        config_file = config_dir / "config.yaml"

        if config_file.exists() and not force:
            console_manager.print_error(
                f"Configuration file already exists: {config_file}"
            )
            console_manager.print_note("Use --force to overwrite")
            sys.exit(1)

        result = create_default_config()
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
    """Perform the actual certificate generation.

    Args:
        hostname: Hostname for the certificate
        cert_file: Certificate file path
        key_file: Key file path
        force: Whether to overwrite existing files

    Returns:
        Success or Error
    """
    try:
        from .cert_utils import ensure_certificate_exists, get_default_cert_paths

        config_dir = get_config_dir("server")

        # Use default paths if not specified
        if cert_file is None or key_file is None:
            default_cert_file, default_key_file = get_default_cert_paths(config_dir)
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
        ensure_certificate_exists(
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
    """Initialize the Certificate Authority.

    Args:
        ca_dir: CA directory path
        root_cn: Root CA common name
        intermediate_cn: Intermediate CA common name
        organization: Organization name
        country: Country code
        force: Whether to overwrite existing CA

    Returns:
        Success or Error
    """
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

        # Initialize the CA - Note: setup_private_ca signature needs to be checked
        setup_private_ca(ca_dir_path)

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
    """Create a server certificate using the CA.

    Args:
        hostname: Hostname for the certificate
        ca_dir: CA directory path
        san: Subject Alternative Names
        validity_days: Certificate validity in days
        force: Whether to overwrite existing certificate

    Returns:
        Success or Error
    """
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
        certs_dir = ca_dir_path / "certs"
        expected_cert_path = certs_dir / f"{hostname}.crt"
        expected_key_path = certs_dir / f"{hostname}.key"

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

    Args:
        cert_path: Path to certificate file
        cert_type: Type description for the certificate
        ca_manager: CAManager instance for certificate operations
        days: Number of days for expiry warning threshold
        status_table: Table to add the status row to

    Returns:
        True iff warnings were found (expired, expires soon, missing, or error)
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
    """Show the status of the CA and certificates.

    Args:
        ca_dir: CA directory path
        days: Days ahead to check for certificate expiry

    Returns:
        Success or Error
    """
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
    """Check for expired or expiring certificates.

    Args:
        ca_dir: CA directory path
        days: Days threshold for expiry warning

    Returns:
        Success or Error
    """
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
