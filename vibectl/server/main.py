#!/usr/bin/env python3
"""
Main entry point for the vibectl gRPC LLM proxy server.

This script provides a standalone server that can be run independently
of the main vibectl CLI, reducing complexity and enabling dedicated
server deployment scenarios.
"""

import argparse
import logging
import sys

from vibectl.grpc_server import create_server
from vibectl.logutil import logger


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


def load_server_config() -> dict:
    """Load server configuration.

    Returns:
        dict: Server configuration dictionary

    Note:
        Currently uses basic defaults. In the future, this will load
        from ~/.config/vibectl/server/config.yaml
    """
    # TODO: Implement proper server configuration loading
    # For now, return basic defaults
    return {
        "host": "localhost",
        "port": 50051,
        "default_model": None,
        "max_workers": 10,
        "log_level": "INFO",
    }


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        argparse.Namespace: Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="vibectl gRPC LLM proxy server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--host", default="localhost", help="Host to bind the gRPC server to"
    )

    parser.add_argument(
        "--port", type=int, default=50051, help="Port to bind the gRPC server to"
    )

    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Default LLM model to use (if not specified, server will require "
            "clients to specify model)"
        ),
    )

    parser.add_argument(
        "--max-workers", type=int, default=10, help="Maximum number of worker threads"
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Logging level",
    )

    parser.add_argument(
        "--config", help="Path to server configuration file (not yet implemented)"
    )

    return parser.parse_args()


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


def main() -> int:
    """Main entry point for the server.

    Returns:
        int: Exit code (0 for success, non-zero for error)
    """
    try:
        # Parse command line arguments
        args = parse_args()

        # Setup logging
        setup_logging(args.log_level)

        # Validate configuration
        validate_config(args.host, args.port, args.max_workers)

        logger.info("Starting vibectl LLM proxy server")
        logger.info(f"Host: {args.host}")
        logger.info(f"Port: {args.port}")
        logger.info(f"Max workers: {args.max_workers}")

        if args.model:
            logger.info(f"Default model: {args.model}")
        else:
            logger.info("No default model configured - clients must specify model")

        # Create and start the server
        server = create_server(
            host=args.host,
            port=args.port,
            default_model=args.model,
            max_workers=args.max_workers,
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


if __name__ == "__main__":
    sys.exit(main())
