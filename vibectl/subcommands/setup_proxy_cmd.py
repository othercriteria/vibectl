"""
Setup proxy command for configuring client proxy usage.

This module provides functionality to configure vibectl clients to use
a central LLM proxy server for model requests.
"""

import asyncio
import sys
from typing import Any

import asyncclick as click
import grpc  # type: ignore
from rich.panel import Panel
from rich.table import Table

from vibectl.config import Config, build_proxy_url, parse_proxy_url
from vibectl.console import console_manager
from vibectl.logutil import logger

try:
    from vibectl.proto import (
        llm_proxy_pb2,  # type: ignore[import-not-found]
        llm_proxy_pb2_grpc,  # type: ignore[import-not-found]
    )

    GRPC_AVAILABLE = True
except ImportError:
    # Protobuf modules not available - this can happen in CI or testing environments
    llm_proxy_pb2 = None  # type: ignore[assignment]
    llm_proxy_pb2_grpc = None  # type: ignore[assignment]
    GRPC_AVAILABLE = False

from vibectl.types import Error, Result, Success
from vibectl.utils import handle_exception


def validate_proxy_url(url: str) -> tuple[bool, str | None]:
    """Validate that a proxy URL has the correct format.

    Args:
        url: The proxy URL to validate

    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    if not url or not url.strip():
        return False, "Proxy URL cannot be empty"

    url = url.strip()

    try:
        proxy_config = parse_proxy_url(url)
        if proxy_config is None:
            return False, "Invalid proxy URL format"
        return True, None
    except ValueError as e:
        # Extract more specific error from parse_proxy_url
        error_msg = str(e)
        if "Invalid proxy URL scheme" in error_msg:
            return False, (
                "Invalid URL scheme. Use 'vibectl-server://' for secure connections "
                "or 'vibectl-server-insecure://' for insecure connections.\n"
                "Examples:\n"
                "  - vibectl-server://myserver.com:443\n"
                "  - vibectl-server://jwt-token@myserver.com:443 (with JWT auth)\n"
                "  - vibectl-server-insecure://localhost:50051"
            )
        elif "must include hostname" in error_msg:
            return False, (
                "URL must include a hostname.\n"
                "Examples:\n"
                "  - vibectl-server://myserver.com:443\n"
                "  - vibectl-server://jwt-token@localhost:50051 (with JWT auth)"
            )
        else:
            return False, f"Invalid URL format: {error_msg}"
    except Exception as e:
        return False, f"URL validation failed: {e}"


async def check_proxy_connection(url: str, timeout_seconds: int = 10) -> Result:
    """Test connection to a proxy server.

    Args:
        url: The proxy server URL
        timeout_seconds: Connection timeout in seconds

    Returns:
        Result indicating success or failure with details
    """
    if not GRPC_AVAILABLE:
        return Error(
            error="gRPC modules are not available. "
            "This functionality requires protobuf files to be generated. "
            "In development environments, this test may be skipped.",
            exception=ImportError("protobuf modules not available"),
        )

    try:
        proxy_config = parse_proxy_url(url)
        if not proxy_config:
            return Error(
                error="Invalid proxy URL format",
                exception=ValueError("Failed to parse proxy URL"),
            )

        # Create gRPC channel and test connection
        target = f"{proxy_config.host}:{proxy_config.port}"

        # Use secure channel if TLS is enabled
        if proxy_config.use_tls:
            channel = grpc.secure_channel(target, grpc.ssl_channel_credentials())
        else:
            channel = grpc.insecure_channel(target)

        stub = llm_proxy_pb2_grpc.VibectlLLMProxyStub(channel)

        # Create request with authentication metadata if JWT token is provided
        metadata = []
        if proxy_config.jwt_token:
            metadata.append(("authorization", f"Bearer {proxy_config.jwt_token}"))

        # Test connection with GetServerInfo call
        request = llm_proxy_pb2.GetServerInfoRequest()  # type: ignore[attr-defined]

        try:
            # Set a timeout for the request and make the call in executor
            response = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: stub.GetServerInfo(
                        request, metadata=metadata, timeout=timeout_seconds
                    ),
                ),
                timeout=timeout_seconds,
            )

            # Close the channel
            channel.close()

            server_info: dict[str, Any] = {
                "server_name": response.server_name,
                "version": response.server_version,
                "supported_models": [
                    model.model_id for model in response.available_models
                ],
                "limits": {
                    "max_request_size": getattr(response.limits, "max_input_length", 0),
                    "max_concurrent_requests": getattr(
                        response.limits, "max_concurrent_requests", 0
                    ),
                    "timeout_seconds": getattr(
                        response.limits, "request_timeout_seconds", 0
                    ),
                },
            }

            return Success(data=server_info)

        except grpc.RpcError as e:
            channel.close()

            # Provide detailed error messages based on gRPC status code
            status_code = e.code()
            details = e.details()

            if status_code == grpc.StatusCode.UNAVAILABLE:
                return Error(
                    error=f"Server unavailable at {target}. "
                    f"Please check:\n"
                    f"  - Server is running and listening on port {proxy_config.port}\n"
                    f"  - Network connectivity to {proxy_config.host}\n"
                    f"  - No firewall blocking the connection\n"
                    f"Original error: {details}",
                    exception=e,
                )
            elif status_code == grpc.StatusCode.UNAUTHENTICATED:
                return Error(
                    error=f"Authentication failed. "
                    f"Please check:\n"
                    f"  - Server requires JWT authentication\n"
                    f"  - Format: vibectl-server://jwt-token@{proxy_config.host}:"
                    f"{proxy_config.port}\n"
                    f"  - Generate token: vibectl-server generate-token "
                    f"<subject> --expires-in 30d\n"
                    f"Original error: {details}",
                    exception=e,
                )
            elif status_code == grpc.StatusCode.PERMISSION_DENIED:
                return Error(
                    error=f"Permission denied. "
                    f"The provided JWT token may be invalid or expired.\n"
                    f"For JWT authentication, generate a new token:\n"
                    f"  vibectl-server generate-token <subject> --expires-in 30d\n"
                    f"Original error: {details}",
                    exception=e,
                )
            elif status_code == grpc.StatusCode.UNIMPLEMENTED:
                return Error(
                    error=f"Server does not support the required service. "
                    f"Please verify this is a vibectl LLM proxy server.\n"
                    f"Original error: {details}",
                    exception=e,
                )
            else:
                return Error(
                    error=f"gRPC error ({status_code.name}): {details}", exception=e
                )

        except TimeoutError:
            channel.close()
            return Error(
                error=f"Connection timeout after {timeout_seconds} seconds. "
                f"Please check:\n"
                f"  - Server is running at {target}\n"
                f"  - Network latency to {proxy_config.host}\n"
                f"  - Try increasing timeout with --timeout option",
                exception=TimeoutError(),
            )

    except Exception as e:
        logger.exception("Failed to test proxy connection")
        return Error(error=f"Connection test failed: {e!s}", exception=e)


def configure_proxy_settings(proxy_url: str) -> Result:
    """Configure proxy settings in the configuration.

    Args:
        proxy_url: The proxy server URL

    Returns:
        Result indicating success or failure
    """
    try:
        # Validate proxy URL format with enhanced error messages
        is_valid, error_message = validate_proxy_url(proxy_url)
        if not is_valid:
            return Error(error=error_message or "Invalid proxy URL format")

        # Parse proxy URL to validate components
        proxy_config = parse_proxy_url(proxy_url)
        if proxy_config is None:
            return Error(error="Failed to parse proxy URL")

        # Get configuration
        config = Config()

        # Set proxy configuration
        config.set("proxy.enabled", True)
        config.set("proxy.server_url", proxy_url)

        return Success(message="✓ Proxy configured successfully")

    except Exception as e:
        logger.error(f"Failed to configure proxy: {e}")
        return Error(error=f"Failed to configure proxy: {e}")


def disable_proxy() -> Result:
    """Disable proxy mode in the client configuration.

    Returns:
        Result indicating success or failure
    """
    try:
        config = Config()

        # Check current state to provide helpful feedback
        currently_enabled = config.get("proxy.enabled", False)
        if not currently_enabled:
            return Success(data="Proxy is already disabled")

        # Disable proxy directly - avoid model adapter initialization
        config.set("proxy.enabled", False)
        config.unset("proxy.server_url")

        # Reset to defaults
        config.unset("proxy.timeout_seconds")
        config.unset("proxy.retry_attempts")

        # Save configuration - this is the critical step that was missing
        config.save()

        return Success(data="Proxy disabled")

    except Exception as e:
        logger.exception("Failed to disable proxy")
        return Error(error=f"Failed to disable proxy: {e!s}", exception=e)


def show_proxy_status() -> None:
    """Show current proxy configuration status."""
    try:
        config = Config()

        # Get proxy configuration
        enabled = config.get("proxy.enabled", False)
        server_url = config.get("proxy.server_url")
        timeout = config.get("proxy.timeout_seconds", 30)
        retries = config.get("proxy.retry_attempts", 3)

        # Create status table
        table = Table(title="Proxy Configuration Status")
        table.add_column("Setting")
        table.add_column("Value", style="green" if enabled else "red")

        table.add_row("Enabled", str(enabled))

        if enabled and server_url:
            table.add_row("Server URL", server_url)
            table.add_row("Timeout (seconds)", str(timeout))
            table.add_row("Retry attempts", str(retries))
        else:
            table.add_row("Server URL", "Not configured")
            table.add_row("Mode", "Direct LLM calls")

        console_manager.safe_print(console_manager.console, table)

        if enabled and server_url:
            console_manager.print_success(
                "Proxy is enabled. LLM calls will be forwarded to "
                "the configured server."
            )
        else:
            console_manager.print_note(
                "Proxy is disabled. LLM calls will be made directly to providers."
            )

    except Exception as e:
        handle_exception(e)


@click.group(name="setup-proxy")
def setup_proxy_group() -> None:
    """Setup and manage proxy configuration for LLM requests.

    The proxy system allows you to centralize LLM API calls through a single
    server, which can provide benefits like:

    - Centralized API key management
    - Request logging and monitoring
    - Rate limiting and quotas
    - Cost tracking across teams
    - Caching for improved performance

    Common workflows:

    1. Configure a new proxy:
       vibectl setup-proxy configure vibectl-server://myserver.com:443

    2. Test connection to server:
       vibectl setup-proxy test

    3. Check current status:
       vibectl setup-proxy status

    4. Disable proxy mode:
       vibectl setup-proxy disable
    """
    pass


@setup_proxy_group.command("configure")
@click.argument("proxy_url")
@click.option("--no-test", is_flag=True, help="Skip connection test")
async def setup_proxy_configure(proxy_url: str, no_test: bool) -> None:
    """Configure proxy settings for LLM calls.

    PROXY_URL should be in the format:
    vibectl-server://[jwt-token@]host:port (secure)
    vibectl-server-insecure://[jwt-token@]host:port (insecure)

    Examples:
        # Secure connection to production server
        vibectl setup-proxy configure vibectl-server://llm-server.example.com:443

        # Secure connection with JWT authentication
        vibectl setup-proxy configure vibectl-server://eyJ0eXAiOiJKV1Q...@llm-server.example.com:443

        # Legacy authentication with secret
        vibectl setup-proxy configure vibectl-server://secret123@llm-server.example.com:8080

        # Insecure connection for local development
        vibectl setup-proxy configure vibectl-server-insecure://localhost:50051

        # Skip connection test if server isn't running yet
        vibectl setup-proxy configure vibectl-server://myserver.com:443 --no-test

    JWT Authentication:
        For production servers, use JWT tokens generated by the server admin:

        # Server generates token (admin command)
        vibectl-server generate-token my-client --expires-in 30d \\
            --output client-token.jwt

        # Client uses token in URL
        vibectl setup-proxy configure \\
            vibectl-server://$(cat client-token.jwt)@production.example.com:443

    The command will:
    1. Validate the URL format
    2. Test connection to the server (unless --no-test is specified)
    3. Save the configuration for future use
    4. Show server information and capabilities
    """
    try:
        console_manager.print(f"Configuring proxy: {proxy_url}")

        # Test connection if requested
        if not no_test:
            console_manager.print("Testing connection to proxy server...")

            test_result = await check_proxy_connection(proxy_url, timeout_seconds=30)

            if isinstance(test_result, Error):
                console_manager.print_error(
                    f"Connection test failed: {test_result.error}"
                )
                console_manager.print_note(
                    "You can skip the connection test with --no-test if the "
                    "server is not running yet."
                )
                sys.exit(1)

            # Show successful connection details
            data = test_result.data
            if data:
                console_manager.print_success("✓ Connection test successful!")

                info_table = Table(title="Server Information")
                info_table.add_column("Property")
                info_table.add_column("Value", style="green")

                info_table.add_row("Server Name", data["server_name"])
                info_table.add_row("Version", data["version"])
                info_table.add_row(
                    "Supported Models", ", ".join(data["supported_models"])
                )
                info_table.add_row(
                    "Max Request Size", f"{data['limits']['max_request_size']} bytes"
                )
                info_table.add_row(
                    "Max Concurrent Requests",
                    str(data["limits"]["max_concurrent_requests"]),
                )
                info_table.add_row(
                    "Server Timeout", f"{data['limits']['timeout_seconds']} seconds"
                )

                console_manager.safe_print(console_manager.console, info_table)

        # Configure proxy settings
        config_result = configure_proxy_settings(proxy_url)

        if isinstance(config_result, Error):
            console_manager.print_error(f"Configuration failed: {config_result.error}")
            sys.exit(1)

        console_manager.print_success("✓ Proxy configuration saved!")

        # Show final configuration
        show_proxy_status()

        console_manager.safe_print(
            console_manager.console,
            Panel(
                "[bold green]Setup Complete![/bold green]\n\n"
                "Your vibectl client is now configured to use the proxy server.\n"
                "All LLM calls will be forwarded to the configured server.\n\n"
                "Use 'vibectl setup-proxy status' to check configuration.\n"
                "Use 'vibectl setup-proxy disable' to switch back to direct calls.",
                title="Proxy Setup",
            ),
        )

    except Exception as e:
        handle_exception(e)


@setup_proxy_group.command(name="test")
@click.argument("server_url", required=False)
@click.option(
    "--timeout", "-t", default=10, help="Connection timeout in seconds (default: 10)"
)
async def test_proxy(server_url: str | None, timeout: int) -> None:
    """Test connection to a proxy server.

    If no SERVER_URL is provided, tests the currently configured proxy.

    This command verifies:
    - Network connectivity to the server
    - gRPC service availability
    - Authentication (if configured)
    - Server capabilities and supported models

    Examples:
        # Test current configuration
        vibectl setup-proxy test

        # Test a specific server with JWT authentication
        vibectl setup-proxy test vibectl-server://eyJ0eXAiOiJKV1Q...@myserver.com:443

        # Test with longer timeout for slow networks
        vibectl setup-proxy test --timeout 30

        # Test insecure local server
        vibectl setup-proxy test vibectl-server-insecure://localhost:50051
    """
    try:
        # Use configured URL if none provided
        if not server_url:
            config = Config()
            server_url = config.get("proxy.server_url")

            if not server_url:
                console_manager.print_error(
                    "No proxy server URL provided and none configured. "
                    "Please provide a URL or configure proxy first."
                )
                sys.exit(1)

            console_manager.print(f"Testing configured proxy: {server_url}")
        else:
            console_manager.print(f"Testing proxy: {server_url}")

        # Test connection
        result = await check_proxy_connection(server_url, timeout_seconds=timeout)

        if isinstance(result, Error):
            console_manager.print_error(f"Connection failed: {result.error}")
            sys.exit(1)

        # Show successful connection details
        data = result.data
        if data:
            console_manager.print_success("✓ Connection successful!")

            info_table = Table(title="Server Information")
            info_table.add_column("Property")
            info_table.add_column("Value", style="green")

            info_table.add_row("Server Name", data["server_name"])
            info_table.add_row("Version", data["version"])
            info_table.add_row("Supported Models", ", ".join(data["supported_models"]))

            console_manager.safe_print(console_manager.console, info_table)

    except Exception as e:
        handle_exception(e)


@setup_proxy_group.command(name="status")
def proxy_status() -> None:
    """Show current proxy configuration status.

    Displays:
    - Whether proxy mode is enabled or disabled
    - Configured server URL (if any)
    - Connection settings (timeout, retry attempts)
    - Current operational mode

    This command is useful for:
    - Verifying your current configuration
    - Troubleshooting connection issues
    - Confirming changes after configuration updates
    """
    show_proxy_status()


@setup_proxy_group.command(name="disable")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def disable_proxy_cmd(yes: bool) -> None:
    """Disable proxy mode and switch back to direct LLM calls.

    This command will:
    1. Turn off proxy mode in the configuration
    2. Clear the stored server URL
    3. Reset connection settings to defaults
    4. Switch back to making direct API calls to LLM providers

    After disabling proxy mode, vibectl will use your locally configured
    API keys to make direct calls to OpenAI, Anthropic, and other providers.

    Examples:
        # Disable with confirmation prompt
        vibectl setup-proxy disable

        # Disable without confirmation (useful for scripts)
        vibectl setup-proxy disable --yes
    """
    try:
        if not yes:
            config = Config()
            enabled = config.get("proxy.enabled", False)

            if not enabled:
                console_manager.print_note("Proxy is already disabled.")
                return

            if not click.confirm("Disable proxy and switch to direct LLM calls?"):
                console_manager.print_note("Operation cancelled.")
                return

        result = disable_proxy()

        if isinstance(result, Error):
            console_manager.print_error(f"Failed to disable proxy: {result.error}")
            sys.exit(1)

        console_manager.print_success("✓ Proxy disabled. Switched to direct LLM calls.")
        show_proxy_status()

    except Exception as e:
        handle_exception(e)


@setup_proxy_group.command(name="url")
@click.argument("host")
@click.argument("port", type=int)
@click.option("--jwt-token", "-j", help="JWT authentication token for the server")
@click.option(
    "--insecure", is_flag=True, help="Use insecure connection (HTTP instead of HTTPS)"
)
def build_url(host: str, port: int, jwt_token: str | None, insecure: bool) -> None:
    """Build a properly formatted proxy server URL.

    This is a utility command to help construct valid proxy URLs with JWT
    authentication.

    Examples:
        vibectl setup-proxy url llm-server.example.com 443
        vibectl setup-proxy url localhost 8080 --jwt-token eyJ0eXAiOiJKV1Q... --insecure
    """
    try:
        url = build_proxy_url(host, port, jwt_token)

        if insecure:
            # Replace vibectl-server:// with vibectl-server-insecure://
            url = url.replace("vibectl-server://", "vibectl-server-insecure://")

        console_manager.print(f"Generated proxy URL: {url}")

        # Show example usage
        console_manager.print("\nExample usage:")
        console_manager.print(f"  vibectl setup-proxy configure {url}")

    except Exception as e:
        handle_exception(e)
