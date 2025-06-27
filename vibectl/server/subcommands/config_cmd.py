"""vibectl-server configuration CLI helpers.

This module defines a ``config`` command group (mirroring the client-side
``vibectl config`` helpers) that operates on the *server* configuration file.

It is imported and registered by :pymod:`vibectl.server.main`.
"""

from __future__ import annotations

import sys
from typing import Any, cast

import click
import yaml

from vibectl.console import console_manager
from vibectl.server.config import ServerConfig
from vibectl.types import Error, Success

__all__: list[str] = [
    "config_group",
]


def _fail(result: Error | str) -> None:  # pragma: no cover - thin helper
    """Render an error (or Error.result) and exit with status 1."""

    if isinstance(result, Error):
        console_manager.print_error(result.error)
    else:
        console_manager.print_error(str(result))
    sys.exit(1)


# ---------------------------------------------------------------------------
# Click command group
# ---------------------------------------------------------------------------


@click.group(name="config", help="Manage vibectl-server configuration.")
def config_group() -> None:  # pragma: no cover - thin wrapper
    """Server configuration commands."""


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


@config_group.command(name="show")
@click.argument("section", required=False)
def config_show(section: str | None = None) -> None:
    """Show the server configuration.

    If *SECTION* is omitted, the full configuration is printed. *SECTION* may be
    a *top-level* section (e.g. ``server`` or ``jwt``) **or** a *dotted path*
    such as ``server.host``.
    """

    cfg = ServerConfig()
    load_result = cfg.load()
    if isinstance(load_result, Error):
        _fail(load_result)

    # At this point mypy cannot infer Success, so cast.
    success = cast(Success, load_result)
    config_data: dict[str, Any] = success.data or {}

    # No section → full dump
    if section is None:
        console_manager.print(
            yaml.dump(config_data, default_flow_style=False, indent=2)
        )
        return

    # Dotted path → single value
    if "." in section:
        value = cfg.get(section)
        if value is None:
            _fail(f"Config key not found: {section}")
        console_manager.print(f"{section}: {value}")
        return

    # Top-level section
    if section not in config_data:
        available = ", ".join(config_data.keys())
        _fail(f"Section '{section}' not found. Available sections: {available}")

    console_manager.print(
        yaml.dump({section: config_data[section]}, default_flow_style=False, indent=2)
    )


# ---------------------------------------------------------------------------
# set
# ---------------------------------------------------------------------------


@config_group.command(name="set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """Set a configuration value.

    ``KEY`` supports dotted notation (e.g. ``server.port``). ``VALUE`` is parsed
    as YAML, allowing booleans / ints / lists without quoting. Examples:

        vibectl-server config set server.port 6000
        vibectl-server config set server.limits.global.max_requests_per_minute 120
        vibectl-server config set jwt.enabled true
    """

    # YAML parsing gives us basic typing (numbers, bools, lists,…).
    try:
        parsed_value: Any = yaml.safe_load(value)
    except yaml.YAMLError:
        parsed_value = value  # Fallback to raw string

    cfg = ServerConfig()
    result = cfg.set(key, parsed_value)
    if isinstance(result, Error):
        _fail(result)

    console_manager.print_success(f"Configuration {key} set to {parsed_value}")


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


@config_group.command(name="validate")
def config_validate() -> None:
    """Validate the configuration file and report problems."""

    cfg = ServerConfig()
    result = cfg.validate()
    if isinstance(result, Error):
        _fail(result)

    console_manager.print_success("Server configuration is valid ✅")
