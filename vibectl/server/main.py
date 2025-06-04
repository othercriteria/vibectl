#!/usr/bin/env python3
"""
Main entry point for the vibectl gRPC LLM proxy server.

This script provides a standalone server that can be run independently
of the main vibectl CLI, reducing complexity and enabling dedicated
server deployment scenarios.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import yaml

from vibectl.logutil import logger

from .grpc_server import create_server
from .jwt_auth import JWTAuthManager, load_jwt_config_from_env


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


def get_server_config_dir() -> Path:
    """Get the server configuration directory path.

    Returns:
        Path to the server configuration directory
    """
    config_home = os.environ.get("XDG_CONFIG_HOME")
    if config_home:
        return Path(config_home) / "vibectl" / "server"
    else:
        return Path.home() / ".config" / "vibectl" / "server"


def ensure_server_config_dir() -> Path:
    """Ensure the server configuration directory exists.

    Returns:
        Path to the server configuration directory
    """
    config_dir = get_server_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def load_server_config() -> dict:
    """Load server configuration.

    Returns:
        dict: Server configuration dictionary
    """
    # Default configuration
    default_config = {
        "host": "localhost",
        "port": 50051,
        "default_model": None,
        "max_workers": 10,
        "log_level": "INFO",
        "enable_auth": False,
    }

    # Try to load from config file
    config_dir = get_server_config_dir()
    config_file = config_dir / "config.yaml"

    if config_file.exists():
        try:
            with open(config_file) as f:
                file_config = yaml.safe_load(f) or {}

            # Merge with defaults
            config = {**default_config, **file_config}
            logger.debug(f"Loaded configuration from {config_file}")
            return config

        except Exception as e:
            logger.warning(f"Failed to load config from {config_file}: {e}")
            logger.info("Using default configuration")

    return default_config


def create_default_config() -> None:
    """Create a default configuration file if it doesn't exist."""
    config_dir = ensure_server_config_dir()
    config_file = config_dir / "config.yaml"

    if not config_file.exists():
        default_config = {
            "# vibectl server configuration": None,
            "host": "localhost",
            "port": 50051,
            "default_model": None,
            "max_workers": 10,
            "log_level": "INFO",
            "enable_auth": False,
        }

        # Remove the comment key before writing
        config_to_write = {
            k: v for k, v in default_config.items() if not k.startswith("#")
        }

        try:
            with open(config_file, "w") as f:
                f.write("# vibectl server configuration\n")
                f.write(
                    "# See https://github.com/your-repo/vibectl for documentation\n\n"
                )
                yaml.dump(config_to_write, f, default_flow_style=False)

            logger.info(f"Created default configuration file: {config_file}")

        except Exception as e:
            logger.warning(f"Failed to create default config file: {e}")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        argparse.Namespace: Parsed arguments
    """
    # Check if user is asking for help on the main command
    if len(sys.argv) == 1 or (len(sys.argv) == 2 and sys.argv[1] in ["-h", "--help"]):
        # Show main help with all subcommands
        parser = argparse.ArgumentParser(
            description="vibectl gRPC LLM proxy server",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )
        subparsers = parser.add_subparsers(dest="command", help="Available commands")

        # Add subparsers just for help display
        subparsers.add_parser("serve", help="Start the gRPC server (default command)")
        subparsers.add_parser(
            "generate-token", help="Generate a JWT token for client authentication"
        )
        subparsers.add_parser(
            "init-config", help="Initialize server configuration directory and files"
        )

        parser.parse_args()
        return argparse.Namespace()  # This won't be reached due to parse_args() exit

    # Check if first argument is a known subcommand
    known_subcommands = ["serve", "generate-token", "init-config"]
    if len(sys.argv) > 1 and sys.argv[1] in known_subcommands:
        # Standard subcommand parsing
        parser = argparse.ArgumentParser(
            description="vibectl gRPC LLM proxy server",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )
        subparsers = parser.add_subparsers(dest="command", help="Available commands")
    else:
        # No subcommand provided, or first arg looks like a flag - default to serve
        # Insert "serve" as the first argument
        sys.argv.insert(1, "serve")
        parser = argparse.ArgumentParser(
            description="vibectl gRPC LLM proxy server",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )
        subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Server command (default)
    server_parser = subparsers.add_parser(
        "serve",
        help="Start the gRPC server (default command)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    server_parser.add_argument(
        "--host", default=None, help="Host to bind the gRPC server to"
    )

    server_parser.add_argument(
        "--port", type=int, default=None, help="Port to bind the gRPC server to"
    )

    server_parser.add_argument(
        "--model",
        default=None,
        help=(
            "Default LLM model to use (if not specified, server will require "
            "clients to specify model)"
        ),
    )

    server_parser.add_argument(
        "--max-workers", type=int, default=None, help="Maximum number of worker threads"
    )

    server_parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default=None,
        help="Logging level",
    )

    server_parser.add_argument(
        "--enable-auth",
        action="store_true",
        help="Enable JWT authentication for the server",
    )

    server_parser.add_argument(
        "--config", help="Path to server configuration file (not yet implemented)"
    )

    # Token generation command
    token_parser = subparsers.add_parser(
        "generate-token",
        help="Generate a JWT token for client authentication",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    token_parser.add_argument(
        "subject",
        help="Subject identifier for the token (e.g., username or client identifier)",
    )

    token_parser.add_argument(
        "--expires-in",
        default="1y",
        help="Token expiration time (e.g., '30d', '1y', '6m')",
    )

    token_parser.add_argument(
        "--output", help="Output file for the token (prints to stdout if not specified)"
    )

    token_parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Logging level",
    )

    # Config initialization command
    config_parser = subparsers.add_parser(
        "init-config",
        help="Initialize server configuration directory and files",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    config_parser.add_argument(
        "--force", action="store_true", help="Overwrite existing configuration files"
    )

    args = parser.parse_args()

    # If no command provided, default to serve (but only if we're not just showing help)
    if args.command is None:
        args.command = "serve"

    return args


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


def cmd_generate_token(args: argparse.Namespace) -> int:
    """Handle the generate-token command.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    try:
        # Setup logging
        setup_logging(args.log_level)

        # Parse the expiration duration
        expiration_days = parse_duration(args.expires_in)

        # Load JWT configuration
        config = load_jwt_config_from_env()
        jwt_manager = JWTAuthManager(config)

        # Generate the token
        token = jwt_manager.generate_token(
            subject=args.subject, expiration_days=expiration_days
        )

        # Output the token
        if args.output:
            with open(args.output, "w") as f:
                f.write(token)
            logger.info(f"Token written to {args.output}")
            print(f"Token generated and saved to {args.output}")
        else:
            print(token)

        logger.info(
            f"Successfully generated token for subject '{args.subject}' "
            f"(expires in {expiration_days} days)"
        )
        return 0

    except Exception as e:
        logger.error(f"Token generation failed: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 1


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


def cmd_init_config(args: argparse.Namespace) -> int:
    """Handle the init-config command.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    try:
        config_dir = ensure_server_config_dir()
        config_file = config_dir / "config.yaml"

        if config_file.exists() and not args.force:
            print(f"Configuration file already exists: {config_file}")
            print("Use --force to overwrite")
            return 1

        create_default_config()

        print(f"Server configuration initialized at: {config_dir}")
        print(f"Configuration file: {config_file}")
        print("\nEdit the configuration file to customize server settings.")

        return 0

    except Exception as e:
        logger.error(f"Config initialization failed: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_serve(args: argparse.Namespace) -> int:
    """Handle the serve command.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    try:
        # Load configuration from file first
        config = load_server_config()

        # Override with command line arguments (only if they were explicitly provided)
        if args.host is not None:
            config["host"] = args.host
        if args.port is not None:
            config["port"] = args.port
        if args.model is not None:
            config["default_model"] = args.model
        if args.max_workers is not None:
            config["max_workers"] = args.max_workers
        if args.log_level is not None:
            config["log_level"] = args.log_level
        if args.enable_auth:
            config["enable_auth"] = True

        # Setup logging
        setup_logging(config["log_level"])

        # Validate configuration
        validate_config(config["host"], config["port"], config["max_workers"])

        logger.info("Starting vibectl LLM proxy server")
        logger.info(f"Host: {config['host']}")
        logger.info(f"Port: {config['port']}")
        logger.info(f"Max workers: {config['max_workers']}")
        logger.info(
            f"Authentication: {'enabled' if config['enable_auth'] else 'disabled'}"
        )

        if config["default_model"]:
            logger.info(f"Default model: {config['default_model']}")
        else:
            logger.info("No default model configured - clients must specify model")

        # Create and start the server
        server = create_server(
            host=config["host"],
            port=config["port"],
            default_model=config["default_model"],
            max_workers=config["max_workers"],
            enable_auth=config["enable_auth"],
        )

        logger.info("Server created successfully")

        # Start serving (this will block until interrupted)
        server.serve_forever()

        logger.info("Server stopped")
        return 0

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
        return 0

    except Exception as e:
        logger.error(f"Server startup failed: {e}", exc_info=True)
        return 1


def main() -> int:
    """Main entry point for the server.

    Returns:
        int: Exit code (0 for success, non-zero for error)
    """
    try:
        # Parse command line arguments
        args = parse_args()

        # Route to the appropriate command handler
        if args.command == "generate-token":
            return cmd_generate_token(args)
        elif args.command == "init-config":
            return cmd_init_config(args)
        else:  # Default to serve
            return cmd_serve(args)

    except Exception as e:
        logger.error(f"Command failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
