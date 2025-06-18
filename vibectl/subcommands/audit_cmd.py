"""
Audit subcommands for vibectl.

Provides convenient commands for viewing, exporting, and inspecting audit logs
produced by the proxy-security hardening work.
"""

from __future__ import annotations

import csv
import io
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import asyncclick as click
from rich.table import Table

from vibectl.config import Config
from vibectl.console import console_manager
from vibectl.logutil import logger
from vibectl.security.audit import AuditLogger
from vibectl.security.config import SecurityConfig
from vibectl.utils import handle_exception

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _parse_since(value: str | None) -> datetime | None:
    """Parse a --since value which may be ISO, UNIX seconds, or relative (e.g., 2h).

    Supports:
        • Absolute ISO 8601 timestamps ("2025-06-18T12:34:56Z" or without Z)
        • UNIX epoch seconds (e.g., "1718700000")
        • Relative durations like "2h", "30m", "1d".
    """
    if value is None:
        return None

    value = value.strip()

    # Relative duration (ends with single char)
    if value[-1] in {"s", "m", "h", "d"} and value[:-1].isdigit():
        qty = int(value[:-1])
        unit = value[-1]
        delta_map = {
            "s": timedelta(seconds=qty),
            "m": timedelta(minutes=qty),
            "h": timedelta(hours=qty),
            "d": timedelta(days=qty),
        }
        return datetime.utcnow() - delta_map[unit]

    # Unix epoch seconds
    if value.isdigit():
        try:
            return datetime.utcfromtimestamp(int(value))
        except Exception:
            pass

    # ISO 8601
    try:
        # Allow Z suffix
        if value.endswith("Z"):
            value = value[:-1]
        return datetime.fromisoformat(value)
    except Exception:
        raise click.BadParameter(
            "Invalid --since value. Use ISO timestamp, epoch seconds, or "
            "relative (e.g., 2h, 30m, 1d)."
        ) from None


def _get_security_config(profile_cfg: dict[str, Any] | None) -> SecurityConfig:
    if not profile_cfg:
        # Default security config (audit enabled)
        return SecurityConfig()
    security_dict = (
        profile_cfg.get("security", {}) if isinstance(profile_cfg, dict) else {}
    )
    return SecurityConfig.from_dict(security_dict)


# ---------------------------------------------------------------------------
# Click group and commands
# ---------------------------------------------------------------------------


@click.group(name="audit")
def audit_group() -> None:
    """Audit-log related commands."""
    pass


# --------------------------- audit show -----------------------------------


@audit_group.command(name="show")
@click.option(
    "--proxy",
    "proxy_profile",
    help="Proxy profile to show logs for (defaults to active profile)",
)
@click.option(
    "--since",
    "since_opt",
    help=(
        "Only show entries since the given time (ISO, epoch seconds, or "
        "relative 2h/30m/1d)"
    ),
)
@click.option(
    "--limit",
    "limit",
    type=int,
    default=20,
    help="Number of entries to display (default 20, 0 = unlimited)",
)
def audit_show(proxy_profile: str | None, since_opt: str | None, limit: int) -> None:
    """Pretty-print recent audit-log events."""

    try:
        cfg = Config()
        if proxy_profile is None:
            proxy_profile = cfg.get_active_proxy_profile()

        if proxy_profile is None:
            console_manager.print_error(
                "No proxy profile specified and no active profile set."
            )
            return

        profile_cfg = cfg.get_proxy_profile(proxy_profile)
        if profile_cfg is None:
            console_manager.print_error(f"Proxy profile '{proxy_profile}' not found.")
            return

        sec_cfg = _get_security_config(profile_cfg)
        if not sec_cfg.audit_logging:
            console_manager.print_warning("Audit logging disabled for this profile.")
            return

        logger.debug("Loading audit entries for profile %s", proxy_profile)
        audit_logger = AuditLogger(sec_cfg, proxy_profile)
        since_dt = _parse_since(since_opt)
        limit_arg = None if limit == 0 else limit
        entries = audit_logger.get_audit_entries(limit=limit_arg, since=since_dt)

        if not entries:
            console_manager.print_note("No audit entries found.")
            return

        table = Table(
            title=f"Audit log ({proxy_profile}) - showing {len(entries)} entries"
        )
        table.add_column("Timestamp")
        table.add_column("Event")
        table.add_column("Details")

        for entry in entries:
            ts = entry.get("timestamp", "")
            evt = entry.get("event_type", "")
            details = _summarize_entry(entry)
            table.add_row(ts, evt, details)

        console_manager.safe_print(console_manager.console, table)
    except Exception as e:
        handle_exception(e)


def _summarize_entry(entry: dict[str, Any]) -> str:
    """Return a short human-readable summary line for an audit entry."""
    evt_type = entry.get("event_type", "")
    if evt_type == "llm_request":
        cmd = entry.get("command_generated")
        model = entry.get("model_used")
        return (
            f"cmd={cmd or '-'} model={model or '-'} "
            f"secrets={entry.get('secrets_detected', 0)}"
        )
    if evt_type == "sanitization":
        return (
            f"secrets={entry.get('secrets_detected', 0)} "
            f"types={','.join(entry.get('secrets_types', []))}"
        )
    if evt_type == "proxy_connection":
        ok = "✓" if entry.get("success") else "✗"
        return f"{ok} {entry.get('server_url', '')}"
    return "-"


# --------------------------- audit export ---------------------------------


@audit_group.command(name="export")
@click.option(
    "--proxy",
    "proxy_profile",
    help="Proxy profile to export logs for (defaults to active profile)",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "jsonl", "csv"], case_sensitive=False),
    default="json",
    help="Export format (json, jsonl, csv)",
)
@click.option(
    "--output",
    "output_path",
    type=str,
    default=None,
    help="Output file path (defaults to stdout)",
)
@click.option("--since", "since_opt", help="Only export entries since given time")
def audit_export(
    proxy_profile: str | None, fmt: str, output_path: str | None, since_opt: str | None
) -> None:
    """Export audit-log entries in JSON or CSV format."""
    try:
        cfg = Config()
        if proxy_profile is None:
            proxy_profile = cfg.get_active_proxy_profile()

        if proxy_profile is None:
            console_manager.print_error(
                "No proxy profile specified and no active profile set."
            )
            return

        profile_cfg = cfg.get_proxy_profile(proxy_profile)
        if profile_cfg is None:
            console_manager.print_error(f"Proxy profile '{proxy_profile}' not found.")
            return

        sec_cfg = _get_security_config(profile_cfg)
        audit_logger = AuditLogger(sec_cfg, proxy_profile)
        since_dt = _parse_since(since_opt)
        entries = audit_logger.get_audit_entries(since=since_dt)

        fmt_lower = fmt.lower()
        if fmt_lower == "json":
            data = json.dumps(entries, indent=2)
        elif fmt_lower == "jsonl":
            # Newline-delimited JSON; each line is compact JSON object
            data_lines = [json.dumps(e, separators=(",", ":")) for e in entries]
            data = "\n".join(data_lines)
        else:  # csv
            if not entries:
                data = ""
            else:
                # Collect all possible fieldnames from all entries
                all_fieldnames: set[str] = set()
                for entry in entries:
                    all_fieldnames.update(entry.keys())
                fieldnames = sorted(all_fieldnames)

                string_io = io.StringIO()
                csv_writer = csv.DictWriter(string_io, fieldnames=fieldnames)
                csv_writer.writeheader()
                for row in entries:
                    # Handle lists by converting to strings
                    csv_row = {}
                    for field in fieldnames:
                        value = row.get(field, "")
                        if isinstance(value, list):
                            csv_row[field] = ",".join(str(v) for v in value)
                        else:
                            csv_row[field] = value
                    csv_writer.writerow(csv_row)
                data = string_io.getvalue().rstrip("\n")
                string_io.close()

        if output_path:
            Path(output_path).expanduser().write_text(data + "\n")
            console_manager.print_success(
                f"Exported {len(entries)} entries to {output_path}"
            )
        else:
            # Print raw data directly to stdout to avoid any console formatting
            print(data, end="")
    except Exception as e:
        handle_exception(e)


# --------------------------- audit info -----------------------------------


@audit_group.command(name="info")
@click.option("--proxy", "proxy_profile", help="Show info for a single proxy profile")
@click.option(
    "--paths-only", is_flag=True, help="Only print log file paths (newline-separated)"
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    help="Output format",
)
def audit_info(proxy_profile: str | None, paths_only: bool, fmt: str) -> None:
    """Show locations and metadata for audit logs."""

    try:
        cfg = Config()

        profiles: list[str] = (
            [proxy_profile] if proxy_profile else cfg.list_proxy_profiles()
        )

        if not profiles:
            console_manager.print_note("No proxy profiles configured.")
            return

        info_rows: list[dict[str, Any]] = []

        for p_name in profiles:
            p_cfg = cfg.get_proxy_profile(p_name)
            if p_cfg is None:
                continue
            sec_cfg = _get_security_config(p_cfg)
            a_logger = AuditLogger(sec_cfg, p_name)
            path_obj = a_logger.log_path
            enabled = sec_cfg.audit_logging
            if path_obj and path_obj.exists():
                exists = True
                size = path_obj.stat().st_size
                last_mod = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(path_obj.stat().st_mtime)
                )
                path_str = str(path_obj)
            else:
                exists = False
                size = 0
                last_mod = "-"
                path_str = str(path_obj) if path_obj else "-"
            info_rows.append(
                {
                    "profile": p_name,
                    "enabled": enabled,
                    "path": path_str,
                    "exists": exists,
                    "size": size,
                    "last_modified": last_mod,
                }
            )

        if paths_only:
            for row in info_rows:
                if row["path"] != "-":
                    # Print paths directly to avoid console wrapping
                    print(row["path"])
            return

        if fmt == "json":
            # Print JSON directly to avoid console formatting issues
            print(json.dumps(info_rows, indent=2, ensure_ascii=False))
            return

        # Default fancy table
        table = Table(title="Audit log information")
        table.add_column("Profile")
        table.add_column("Enabled")
        table.add_column("Log path")
        table.add_column("Exists")
        table.add_column("Size")
        table.add_column("Last modified")

        for row in info_rows:
            table.add_row(
                row["profile"],
                "Yes" if row["enabled"] else "No",
                row["path"],
                "Yes" if row["exists"] else "No",
                f"{row['size']} bytes" if row["exists"] else "-",
                row["last_modified"],
            )

        console_manager.safe_print(console_manager.console, table)
    except Exception as e:
        handle_exception(e)
