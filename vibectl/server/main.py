#!/usr/bin/env python3
"""
Main entry point for the vibectl gRPC LLM proxy server.

This script provides a standalone server that can be run independently
of the main vibectl CLI, reducing complexity and enabling dedicated
server deployment scenarios.
"""

import logging
import sys
from pathlib import Path

import click

from vibectl.config_utils import (
    ensure_config_dir,
    get_config_dir,
    load_yaml_config,
)
from vibectl.logutil import logger

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
            "require_auth": False,
        },
        "jwt": {
            "secret_key": None,  # Will use environment or generate if None
            "secret_key_file": None,  # Path to file containing secret key
            "algorithm": "HS256",
            "issuer": "vibectl-server",
            "expiration_days": 30,
        },
    }


def load_server_config(config_path: Path | None = None) -> dict:
    """Load server configuration from file or create defaults.

    Args:
        config_path: Optional path to configuration file

    Returns:
        dict: Server configuration
    """
    if config_path is None:
        config_path = get_server_config_path()

    try:
        # Use shared config loading utility with deep merge
        return load_yaml_config(config_path, get_default_server_config())
    except ValueError as e:
        logger.error("Failed to load config from %s: %s", config_path, e)
        logger.info("Using default configuration")
        return get_default_server_config()


def create_default_config(config_path: Path | None = None) -> None:
    """Create a default configuration file.

    Args:
        config_path: Optional path for the configuration file
    """
    import yaml

    if config_path is None:
        config_path = get_server_config_path()

    config_path.parent.mkdir(parents=True, exist_ok=True)

    default_config = get_default_server_config()

    try:
        with config_path.open("w") as f:
            yaml.dump(default_config, f, default_flow_style=False, sort_keys=False)
        logger.info("Created default config at %s", config_path)
    except Exception as e:
        logger.error("Failed to create config file at %s: %s", config_path, e)
        raise


def setup_logging(log_level: str = "INFO") -> None:
    """Setup logging configuration for the server.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {log_level}")

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_duration(duration_str: str) -> int:
    """Parse a duration string into days.

    Args:
        duration_str: Duration string (e.g., '30d', '6m', '1y', or just '30')

    Returns:
        int: Number of days

    Raises:
        ValueError: If duration format is invalid
    """
    duration_str = duration_str.strip().lower()

    # If it's just a number, treat as days
    if duration_str.isdigit():
        return int(duration_str)

    # Parse with suffix
    if len(duration_str) < 2:
        raise ValueError(
            f"Invalid duration format: {duration_str}. "
            "Use format like '30d', '6m', '1y', or just a number for days"
        ) from None

    value_str = duration_str[:-1]
    suffix = duration_str[-1]

    try:
        value = int(value_str)
    except ValueError:
        raise ValueError(
            f"Invalid duration format: {duration_str}. "
            "Use format like '30d', '6m', '1y', or just a number for days"
        ) from None

    if suffix == "d":
        return value
    elif suffix == "m":
        return value * 30  # Approximate month as 30 days
    elif suffix == "y":
        return value * 365  # Approximate year as 365 days
    else:
        raise ValueError(
            f"Invalid duration format: {duration_str}. "
            "Use format like '30d', '6m', '1y', or just a number for days"
        ) from None


def validate_config(host: str, port: int, max_workers: int) -> None:
    """Validate server configuration parameters.

    Args:
        host: Server host
        port: Server port
        max_workers: Maximum worker threads

    Raises:
        ValueError: If any configuration parameter is invalid
    """
    if not host:
        raise ValueError("Host cannot be empty")

    if port < 1 or port > 65535:
        raise ValueError(f"Port must be between 1 and 65535, got {port}")

    if max_workers < 1:
        raise ValueError(f"Max workers must be at least 1, got {max_workers}")


# Click CLI Group and Commands
@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """vibectl gRPC LLM proxy server"""
    # If no subcommand is provided, default to serve
    if ctx.invoked_subcommand is None:
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
    "--require-auth",
    is_flag=True,
    default=False,
    help="Require JWT authentication for all server requests",
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
    require_auth: bool,
    config: str | None,
) -> None:
    """Start the gRPC server (default command)"""
    try:
        # Load configuration from file first
        server_config = load_server_config()

        # Override with command line arguments (only if they were explicitly provided)
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
        if require_auth:
            server_config["server"]["require_auth"] = True

        # Setup logging
        setup_logging(server_config["server"]["log_level"])

        # Validate configuration
        validate_config(
            server_config["server"]["host"],
            server_config["server"]["port"],
            server_config["server"]["max_workers"],
        )

        logger.info("Starting vibectl LLM proxy server")
        logger.info(f"Host: {server_config['server']['host']}")
        logger.info(f"Port: {server_config['server']['port']}")
        logger.info(f"Max workers: {server_config['server']['max_workers']}")
        auth_status = (
            "enabled" if server_config["server"]["require_auth"] else "disabled"
        )
        logger.info(f"Authentication: {auth_status}")

        if server_config["server"]["default_model"]:
            logger.info(f"Default model: {server_config['server']['default_model']}")
        else:
            logger.info("No default model configured - clients must specify model")

        # Create and start the server
        server = create_server(
            host=server_config["server"]["host"],
            port=server_config["server"]["port"],
            default_model=server_config["server"]["default_model"],
            max_workers=server_config["server"]["max_workers"],
            require_auth=server_config["server"]["require_auth"],
        )

        logger.info("Server created successfully")

        # Start serving (this will block until interrupted)
        server.serve_forever()

        logger.info("Server stopped")

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")

    except Exception as e:
        logger.error(f"Server startup failed: {e}", exc_info=True)
        sys.exit(1)


@cli.command()
@click.argument("subject")
@click.option(
    "--expires-in", default="1y", help="Token expiration time (e.g., '30d', '1y', '6m')"
)
@click.option(
    "--output", help="Output file for the token (prints to stdout if not specified)"
)
@click.option(
    "--log-level",
    type=click.Choice(
        ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], case_sensitive=False
    ),
    default="INFO",
    help="Logging level",
)
def generate_token(
    subject: str,
    expires_in: str,
    output: str | None,
    log_level: str,
) -> None:
    """Generate a JWT token for client authentication"""
    try:
        # Setup logging
        setup_logging(log_level)

        # Parse the expiration duration
        expiration_days = parse_duration(expires_in)

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
            click.echo(f"Token generated and saved to {output}")
        else:
            click.echo(token)

        logger.info(
            f"Successfully generated token for subject '{subject}' "
            f"(expires in {expiration_days} days)"
        )

    except Exception as e:
        logger.error(f"Token generation failed: {e}")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--force", is_flag=True, help="Overwrite existing configuration files")
def init_config(force: bool) -> None:
    """Initialize server configuration directory and files"""
    try:
        config_dir = ensure_config_dir("server")
        config_file = config_dir / "config.yaml"

        if config_file.exists() and not force:
            click.echo(f"Configuration file already exists: {config_file}")
            click.echo("Use --force to overwrite")
            sys.exit(1)

        create_default_config()

        click.echo(f"Server configuration initialized at: {config_dir}")
        click.echo(f"Configuration file: {config_file}")
        click.echo("\nEdit the configuration file to customize server settings.")

    except Exception as e:
        logger.error(f"Config initialization failed: {e}")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def main() -> int:
    """Main entry point for the server.

    Returns:
        int: Exit code (0 for success, non-zero for error)
    """
    try:
        # Run the CLI
        cli()
        return 0

    except Exception as e:
        logger.error(f"Command failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
