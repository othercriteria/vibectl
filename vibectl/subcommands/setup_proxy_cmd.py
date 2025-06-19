"""
Setup proxy command for configuring client proxy usage.

This module provides functionality to configure vibectl clients to use
a central LLM proxy server for model requests.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import asyncclick as click
import grpc
from rich.panel import Panel
from rich.table import Table

from vibectl.config import Config, build_proxy_url, parse_proxy_url
from vibectl.console import console_manager
from vibectl.logutil import logger
from vibectl.proto import (
    llm_proxy_pb2,  # type: ignore[import-not-found]
    llm_proxy_pb2_grpc,  # type: ignore[import-not-found]
)
from vibectl.types import Error, ExecutionMode, Result, Success, execution_mode_from_cli
from vibectl.utils import handle_exception


def validate_proxy_url(url: str) -> tuple[bool, str | None]:
    """Validate a proxy URL format.

    Args:
        url: The URL to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not url or not url.strip():
        return False, "Proxy URL cannot be empty"

    # Use the stripped URL for parsing
    url = url.strip()

    try:
        # First do basic URL parsing
        parsed = urlparse(url)

        # Check scheme
        valid_schemes = ["vibectl-server", "vibectl-server-insecure"]
        if parsed.scheme not in valid_schemes:
            return (
                False,
                "Invalid URL scheme. Must be one of: vibectl-server://, vibectl-server-insecure://",
            )

        # Check hostname
        if not parsed.hostname:
            return False, "URL must include a hostname"

        # Check port (default to 50051 if not specified)
        port = parsed.port or 50051
        if not (1 <= port <= 65535):
            return False, f"Invalid port {port}. Must be between 1 and 65535"

        # Use parse_proxy_url for detailed validation (tests expect this to be called)
        proxy_config = parse_proxy_url(url)
        if proxy_config is None:
            return False, "Invalid proxy URL format"

        return True, None

    except Exception as e:
        return False, f"URL validation failed: {e}"


async def check_proxy_connection(
    url: str,
    timeout_seconds: int = 10,
    jwt_path: str | None = None,
    ca_bundle: str | None = None,
) -> Result:
    """Test a proxy server connection.

    Args:
        url: The proxy server URL to test
        timeout_seconds: Connection timeout in seconds (default: 10)
        jwt_path: Optional path to JWT token file (overrides config)
        ca_bundle: Optional path to CA bundle file (overrides config and environment)

    Returns:
        Result indicating success or failure with connection details
    """
    # Initialize channel variable at function scope for proper cleanup
    channel = None

    try:
        # Parse the proxy URL
        try:
            proxy_config = parse_proxy_url(url)
            if proxy_config is None:
                return Error(error="Invalid proxy URL format")
        except ValueError as e:
            return Error(error=f"Invalid proxy URL: {e}")

        # Get JWT token with precedence: jwt_path parameter > embedded in URL > config
        jwt_token = None
        if jwt_path:
            # Read JWT token from provided file path
            try:
                jwt_file = Path(jwt_path).expanduser()
                if jwt_file.exists() and jwt_file.is_file():
                    jwt_token = jwt_file.read_text().strip()
                else:
                    return Error(
                        error=f"JWT file not found or not accessible: {jwt_path}"
                    )
            except Exception as e:
                return Error(error=f"Failed to read JWT file {jwt_path}: {e}")
        else:
            # Fall back to embedded token or environment variable
            jwt_token = proxy_config.jwt_token or os.environ.get("VIBECTL_JWT_TOKEN")

        # Create gRPC channel directly
        if proxy_config.use_tls:
            # Get CA bundle path with precedence:
            # ca_bundle parameter > environment variable
            ca_bundle_path = ca_bundle or os.environ.get("VIBECTL_CA_BUNDLE")

            if ca_bundle_path:
                # Custom CA bundle TLS
                try:
                    with open(ca_bundle_path, "rb") as f:
                        ca_cert_data = f.read()
                    credentials = grpc.ssl_channel_credentials(
                        root_certificates=ca_cert_data
                    )
                    logger.debug(
                        "Creating secure channel with custom "
                        f"CA bundle ({ca_bundle_path}) for connection test "
                        f"using TLS 1.3+"
                    )
                except FileNotFoundError:
                    return Error(error=f"CA bundle file not found: {ca_bundle_path}")
                except Exception as e:
                    return Error(
                        error=f"Failed to read CA bundle file {ca_bundle_path}: {e}"
                    )
            else:
                # Production TLS with system trust store
                credentials = grpc.ssl_channel_credentials()
                logger.debug(
                    "Creating secure channel with system trust store "
                    "for connection test using TLS 1.3+"
                )

            # Configure TLS 1.3+ enforcement via gRPC channel options
            channel_options = [
                # Enforce TLS 1.3+ for enhanced security
                ("grpc.ssl_min_tls_version", "TLSv1_3"),
                ("grpc.ssl_max_tls_version", "TLSv1_3"),
                # Additional security options
                ("grpc.keepalive_time_ms", 30000),
                ("grpc.keepalive_timeout_ms", 5000),
                ("grpc.keepalive_permit_without_calls", True),
            ]

            channel = grpc.secure_channel(
                f"{proxy_config.host}:{proxy_config.port}",
                credentials,
                options=channel_options,
            )
        else:
            channel = grpc.insecure_channel(f"{proxy_config.host}:{proxy_config.port}")

        # Create stub
        stub = llm_proxy_pb2_grpc.VibectlLLMProxyStub(channel)

        # Create metadata for JWT token if provided
        metadata = []
        if jwt_token:
            metadata.append(("authorization", f"Bearer {jwt_token}"))

        # Create request
        request = llm_proxy_pb2.GetServerInfoRequest()  # type: ignore[attr-defined]

        # Make the call with timeout
        server_info = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None, lambda: stub.GetServerInfo(request, metadata=metadata)
            ),
            timeout=timeout_seconds,
        )

        # Extract server version and available models
        server_version = server_info.server_version
        available_models = [model.model_id for model in server_info.available_models]

        # Extract limits information
        limits = {
            "max_request_size": server_info.limits.max_input_length,
            "max_concurrent_requests": server_info.limits.max_concurrent_requests,
            "timeout_seconds": server_info.limits.request_timeout_seconds,
        }

        # Return the expected data structure format
        return Success(
            data={
                "version": server_version,
                "supported_models": available_models,
                "server_name": server_info.server_name,
                "limits": limits,
            }
        )

    except TimeoutError:
        return Error(error=f"Connection timeout after {timeout_seconds} seconds")
    except grpc.RpcError as e:
        # Handle specific gRPC error codes with expected messages
        if hasattr(e, "code"):
            if e.code() == grpc.StatusCode.UNAVAILABLE:
                details = e.details() if hasattr(e, "details") else ""
                return Error(
                    error=(
                        "Server unavailable at "
                        f"{proxy_config.host}:{proxy_config.port}. "
                        f"{details}"
                    ).strip()
                )
            elif e.code() == grpc.StatusCode.UNAUTHENTICATED:
                return Error(error="Server requires JWT authentication")
            elif e.code() == grpc.StatusCode.PERMISSION_DENIED:
                return Error(error="JWT token may be invalid or expired")
            elif e.code() == grpc.StatusCode.UNIMPLEMENTED:
                return Error(error="Server does not support the required service")
            else:
                details = e.details() if hasattr(e, "details") else str(e)
                error_msg = f"gRPC error ({e.code().name}): {details}"

                if (
                    proxy_config.use_tls
                    and details
                    and (
                        "CERTIFICATE_VERIFY_FAILED" in details
                        or "unable to get local issuer certificate" in details
                        or "certificate verify failed" in details.lower()
                    )
                ):
                    recovery_suggestions = """
                    This appears to be a private certificate authority (CA) setup.
                    To fix this issue, you need to provide a CA bundle file:
                    1. Use --ca-bundle flag: --ca-bundle /path/to/ca-bundle.crt
                    2. Set env variable: export VIBECTL_CA_BUNDLE=/path/to/ca-bundle.crt
                    3. Get the CA bundle from your server administrator
                    """
                    return Error(
                        error=error_msg,
                        recovery_suggestions=recovery_suggestions,
                    )

                return Error(error=error_msg)
        else:
            return Error(error=f"gRPC connection failed: {e}")
    except Exception as e:
        if "Failed to create gRPC stub" in str(e):
            return Error(error="Connection test failed: Failed to create gRPC stub")
        logger.exception("Unexpected error during proxy connection test")
        return Error(error=f"Connection test failed: {e}")
    finally:
        # Always clean up the channel in function-level finally block
        if channel:
            channel.close()


def disable_proxy() -> Result:
    """Disable proxy mode in the client configuration.

    Returns:
        Result indicating success or failure
    """
    try:
        config = Config()

        # Check current state to provide helpful feedback
        currently_enabled = config.is_proxy_enabled()
        if not currently_enabled:
            return Success(data="Proxy is already disabled")

        # Disable proxy by clearing the active profile (Config.set already saves)
        config.set_active_proxy_profile(None)

        return Success(data="Proxy disabled")

    except Exception as e:
        logger.exception("Failed to disable proxy")
        return Error(error=f"Failed to disable proxy: {e!s}", exception=e)


def show_proxy_status() -> None:
    """Show current proxy configuration status."""
    try:
        config = Config()

        # Get proxy configuration from profiles
        enabled = config.is_proxy_enabled()
        active_profile = config.get_active_proxy_profile()
        effective_config = config.get_effective_proxy_config()

        # Create status table
        table = Table(title="Proxy Configuration Status")
        table.add_column("Setting")
        table.add_column("Value", style="green" if enabled else "red")

        table.add_row("Enabled", str(enabled))

        if enabled and effective_config:
            server_url = effective_config.get("server_url")
            timeout = effective_config.get("timeout_seconds", 30)
            retries = effective_config.get("retry_attempts", 3)

            table.add_row("Active Profile", active_profile or "None")
            if server_url:
                table.add_row("Server URL", redact_jwt_in_url(server_url))
            table.add_row("Timeout (seconds)", str(timeout))
            table.add_row("Retry attempts", str(retries))

            # Show CA bundle information
            env_ca_bundle = os.environ.get("VIBECTL_CA_BUNDLE")
            profile_ca_bundle = effective_config.get("ca_bundle_path")

            if env_ca_bundle:
                table.add_row("CA Bundle Path", f"{env_ca_bundle} (from environment)")
                ca_exists = Path(env_ca_bundle).exists()
                table.add_row(
                    "CA Bundle Status", "✓ Found" if ca_exists else "❌ Missing"
                )
            elif profile_ca_bundle:
                table.add_row("CA Bundle Path", f"{profile_ca_bundle} (from profile)")
                ca_exists = Path(profile_ca_bundle).exists()
                table.add_row(
                    "CA Bundle Status", "✓ Found" if ca_exists else "❌ Missing"
                )
            else:
                table.add_row("CA Bundle Path", "None (system trust store)")

            # Show JWT token configuration
            env_jwt_token = os.environ.get("VIBECTL_JWT_TOKEN")
            profile_jwt_path = effective_config.get("jwt_path")
            embedded_jwt = None
            if server_url:
                try:
                    proxy_config = parse_proxy_url(server_url)
                    embedded_jwt = proxy_config.jwt_token
                except Exception:
                    pass

            if env_jwt_token:
                table.add_row("JWT Token", "*** (from environment)")
            elif profile_jwt_path:
                jwt_exists = Path(profile_jwt_path).exists()
                table.add_row("JWT Token Path", f"{profile_jwt_path} (from profile)")
                table.add_row(
                    "JWT Token Status", "✓ Found" if jwt_exists else "❌ Missing"
                )
            elif embedded_jwt:
                table.add_row("JWT Token", "*** (embedded in URL)")
            else:
                table.add_row("JWT Token", "None (no authentication)")

            # Show security settings
            security_config = effective_config.get("security", {})
            security_parts = []
            if security_config.get("sanitize_requests"):
                security_parts.append("Sanitization")
            if security_config.get("audit_logging"):
                security_parts.append("Audit")
            security_text = ", ".join(security_parts) if security_parts else "None"
            table.add_row("Security Features", security_text)
        else:
            table.add_row("Active Profile", "None")
            table.add_row("Server URL", "Not configured")
            table.add_row("Mode", "Direct LLM calls")

        console_manager.safe_print(console_manager.console, table)

        if enabled and effective_config and effective_config.get("server_url"):
            server_url = effective_config["server_url"]
            console_manager.print_success(
                "Proxy is enabled. LLM calls will be forwarded to "
                "the configured server."
            )

            # Show TLS configuration info
            if server_url.startswith("vibectl-server://"):
                env_ca_bundle = os.environ.get("VIBECTL_CA_BUNDLE")
                profile_ca_bundle = effective_config.get("ca_bundle_path")

                if env_ca_bundle or profile_ca_bundle:
                    ca_source = "environment" if env_ca_bundle else "profile"
                    ca_path = env_ca_bundle or profile_ca_bundle
                    console_manager.print_note(
                        "Using custom CA bundle for TLS verification: "
                        f"{ca_path} (from {ca_source})"
                    )
                else:
                    console_manager.print_note(
                        "Using system trust store for TLS verification"
                    )
            elif server_url.startswith("vibectl-server-insecure://"):
                console_manager.print_warning(
                    "Using insecure connection (no TLS). "
                    "Only use for local development."
                )
        else:
            console_manager.print_note(
                "Proxy is disabled. LLM calls will be made directly to providers."
            )

    except Exception as e:
        handle_exception(e)


def redact_jwt_in_url(url: str) -> str:
    """Redact JWT token from URL for display purposes.

    Args:
        url: The URL to redact (e.g., vibectl-server://token@host:port)

    Returns:
        URL with JWT token redacted (e.g., vibectl-server://***@host:port)
    """
    if not url:
        return url

    try:
        parsed = urlparse(url)
        if parsed.username:
            # Replace the JWT token part with asterisks
            redacted_username = "***"
            # Reconstruct URL with redacted token
            if parsed.port:
                netloc = f"{redacted_username}@{parsed.hostname}:{parsed.port}"
            else:
                netloc = f"{redacted_username}@{parsed.hostname}"
            return f"{parsed.scheme}://{netloc}{parsed.path}"
    except Exception:
        # If parsing fails, just return original URL
        pass

    return url


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
@click.argument("profile_name")
@click.argument("proxy_url")
@click.option("--no-test", is_flag=True, help="Skip connection test")
@click.option("--ca-bundle", help="Path to custom CA bundle file for TLS verification")
@click.option("--jwt-path", help="Path to JWT token file for authentication")
@click.option("--enable-sanitization", is_flag=True, help="Enable request sanitization")
@click.option("--enable-audit-logging", is_flag=True, help="Enable audit logging")
@click.option(
    "--no-sanitization-warnings",
    is_flag=True,
    help="Disable warnings when sanitization occurs",
)
@click.option(
    "--activate", is_flag=True, help="Activate this profile after creating it"
)
@click.option(
    "--no-activate",
    is_flag=True,
    help="Don't activate this profile after creation (default behavior)",
)
async def setup_proxy_configure(
    profile_name: str,
    proxy_url: str,
    no_test: bool,
    ca_bundle: str | None,
    jwt_path: str | None,
    enable_sanitization: bool,
    enable_audit_logging: bool,
    no_sanitization_warnings: bool,
    activate: bool,
    no_activate: bool,
) -> None:
    """Configure proxy settings for LLM calls.

    PROXY_URL should be in the format:
    vibectl-server://[jwt-token@]host:port (secure, full certificate verification)
    vibectl-server-insecure://[jwt-token@]host:port (insecure, no TLS)

    Examples:
        # Basic secure connection (uses system trust store)
        vibectl setup-proxy configure vibectl-server://llm-server.example.com:443

        # Secure connection with JWT authentication
        vibectl setup-proxy configure vibectl-server://eyJ0eXAiOiJKV1Q...@llm-server.example.com:443

        # Configure with custom CA bundle, then test separately
        vibectl setup-proxy configure vibectl-server://token@host:443 \\
            --ca-bundle /path/to/ca-bundle.crt \\
            --jwt-path /path/to/client-token.jwt \\
            --no-test
        vibectl setup-proxy test

        # Insecure connection for local development
        vibectl setup-proxy configure vibectl-server-insecure://localhost:50051

    Connection Types:
        - vibectl-server://          : Full TLS with certificate verification
        - vibectl-server-insecure:// : No TLS encryption

    CA Bundle Options:
        For servers using private certificate authorities or self-signed certificates:

        # Explicit CA bundle file
        vibectl setup-proxy configure vibectl-server://host:443 \\
            --ca-bundle /etc/ssl/certs/company-ca.pem

        # Environment variable (overrides --ca-bundle flag)
        export VIBECTL_CA_BUNDLE=/etc/ssl/certs/company-ca.pem
        vibectl setup-proxy configure vibectl-server://host:443

    JWT Authentication:
        For production servers, use JWT tokens generated by the server admin.

        **Recommended approach (secure file-based):**
        # Server generates token file
        vibectl-server generate-token my-client --expires-in 30d \\
            --output client-token.jwt

        # Client uses JWT file path (more secure, easier to manage)
        vibectl setup-proxy configure vibectl-server://production.example.com:443 \\
            --jwt-path ./client-token.jwt

        **Alternative approach (embedded in URL):**
        # Client embeds token in URL (less secure, but still supported)
        vibectl setup-proxy configure \\
            vibectl-server://$(cat client-token.jwt)@production.example.com:443

    Recommended Workflow:
        For production deployments with custom CAs:

        # 1. Configure without testing (saves CA bundle path)
        vibectl setup-proxy configure vibectl-server://token@host:443 \\
            --ca-bundle /path/to/ca.pem --jwt-path /path/to/client-token.jwt --no-test

        # 2. Test connectivity separately
        vibectl setup-proxy test

        # 3. Verify configuration
        vibectl setup-proxy status

    The command will:
    1. Validate the URL format and CA bundle file (if provided)
    2. Test connection to the server (unless --no-test is specified)
    3. Save the configuration for future use
    4. Show server information and capabilities on successful connection
    """
    try:
        # Validate flag combinations
        if activate and no_activate:
            console_manager.print_error(
                "Cannot use both --activate and --no-activate flags together"
            )
            sys.exit(1)

        if activate and no_test:
            console_manager.print_error(
                "Cannot use --activate with --no-test. "
                "Proxy profiles should be tested before activation for security."
            )
            console_manager.print_note(
                "Either remove --no-test to test the connection, or remove "
                "--activate to configure without activating."
            )
            sys.exit(1)

        console_manager.print(f"Configuring proxy: {proxy_url}")

        # Check if we have a CA bundle from environment variable
        env_ca_bundle = os.environ.get("VIBECTL_CA_BUNDLE")
        final_ca_bundle = ca_bundle or env_ca_bundle

        if final_ca_bundle:
            console_manager.print(f"Using CA bundle: {final_ca_bundle}")
            # Validate CA bundle file
            ca_bundle_path = Path(final_ca_bundle).expanduser()
            if not ca_bundle_path.exists():
                console_manager.print_error(
                    f"CA bundle file not found: {final_ca_bundle}"
                )
                sys.exit(1)

        # Test connection if requested
        if not no_test:
            console_manager.print("Testing connection to proxy server...")

            test_result = await check_proxy_connection(
                proxy_url,
                timeout_seconds=30,
                jwt_path=jwt_path,
                ca_bundle=final_ca_bundle,
            )

            if isinstance(test_result, Error):
                console_manager.print_error(
                    f"Connection test failed: {test_result.error}"
                )

                if test_result.recovery_suggestions:
                    console_manager.print_note(test_result.recovery_suggestions)
                else:
                    console_manager.print_note(
                        "You can skip the connection test with --no-test if the "
                        "server is not running yet."
                    )
                sys.exit(1)

            # Show successful connection details
            if isinstance(test_result, Success):
                data = test_result.data
                if data:
                    console_manager.print_success("✓ Connection test successful!")
                    _print_server_info(data)

        # Configure proxy profile
        config = Config()

        # Create profile configuration
        profile_config: dict[str, Any] = {
            "server_url": proxy_url,
        }

        if final_ca_bundle:
            profile_config["ca_bundle_path"] = str(
                Path(final_ca_bundle).expanduser().absolute()
            )

        if jwt_path:
            profile_config["jwt_path"] = str(Path(jwt_path).expanduser().absolute())

        # Add security settings if specified
        if enable_sanitization or enable_audit_logging or no_sanitization_warnings:
            security_config: dict[str, bool] = {}
            if enable_sanitization:
                security_config["sanitize_requests"] = True
            if enable_audit_logging:
                security_config["audit_logging"] = True
            if no_sanitization_warnings:
                security_config["warn_sanitization"] = False
            profile_config["security"] = security_config

        # Save the profile
        config.set_proxy_profile(profile_name, profile_config)

        # Handle activation logic
        should_activate = False
        if activate:
            should_activate = True
        elif not no_activate:
            # Default behavior: activate the profile (legacy behavior)
            should_activate = True

        if should_activate:
            config.set_active_proxy_profile(profile_name)
            activation_message = "✓ Proxy profile activated!"
        else:
            activation_message = (
                "Profile created but not activated (use "
                "'vibectl setup-proxy set-active' to activate)"
            )

        # Configuration changes are already persisted by individual set* calls
        console_manager.print_success(
            f"✓ Proxy profile '{profile_name}' configured successfully"
        )
        console_manager.print_success(activation_message)

        if final_ca_bundle:
            console_manager.print_success(f"✓ CA bundle configured: {final_ca_bundle}")

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
@click.option("--jwt-path", help="Path to JWT token file for authentication")
async def test_proxy(
    server_url: str | None, timeout: int, jwt_path: str | None
) -> None:
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

        # Test a specific server with JWT authentication from file
        vibectl setup-proxy test vibectl-server://myserver.com:443 \\
            --jwt-path /path/to/token.jwt

        # Test with longer timeout for slow networks
        vibectl setup-proxy test --timeout 30

        # Test insecure local server
        vibectl setup-proxy test vibectl-server-insecure://localhost:50051
    """
    try:
        # Initialize variables
        ca_bundle_to_use = None
        jwt_path_to_use = jwt_path  # Use explicit jwt_path if provided

        # Use configured URL if none provided
        if not server_url:
            config = Config()
            effective_config = config.get_effective_proxy_config()

            if not effective_config or not effective_config.get("server_url"):
                console_manager.print_error(
                    "No proxy server URL provided and none configured. "
                    "Please provide a URL or configure proxy first."
                )
                sys.exit(1)

            server_url = effective_config["server_url"]
            if not server_url:
                console_manager.print_error(
                    "Active proxy profile has no server URL configured."
                )
                sys.exit(1)

            # Use profile's CA bundle if no explicit one provided
            if not ca_bundle_to_use:
                ca_bundle_to_use = effective_config.get("ca_bundle_path")

            # Use profile's JWT path if no explicit one provided
            if not jwt_path_to_use:
                jwt_path_to_use = effective_config.get("jwt_path")

            console_manager.print(
                f"Testing configured proxy: {redact_jwt_in_url(server_url)}"
            )
        else:
            console_manager.print(f"Testing proxy: {redact_jwt_in_url(server_url)}")

        # Test connection (use config-stored CA bundle if available)
        result = await check_proxy_connection(
            server_url,
            timeout_seconds=timeout,
            jwt_path=jwt_path_to_use,
            ca_bundle=ca_bundle_to_use,
        )

        if isinstance(result, Error):
            console_manager.print_error(f"Connection failed: {result.error}")
            sys.exit(1)

        # Show successful connection details
        data = result.data
        if data:
            console_manager.print_success("✓ Connection successful!")
            _print_server_info(data)

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
@click.option(
    "--mode",
    type=click.Choice(["manual", "auto", "semiauto"], case_sensitive=False),
    default=None,
    help=("Execution mode: manual (confirmations enabled); auto (no confirmations)"),
)
def disable_proxy_cmd(mode: str | None = None) -> None:
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
        vibectl setup-proxy disable --mode auto
    """
    try:
        exec_mode = execution_mode_from_cli(mode)
        if exec_mode is None:
            exec_mode = ExecutionMode.MANUAL

        skip_confirmation = exec_mode == ExecutionMode.AUTO

        if not skip_confirmation:
            config = Config()
            enabled = config.is_proxy_enabled()

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


@setup_proxy_group.command("list")
def list_proxy_profiles() -> None:
    """List all configured proxy profiles."""
    try:
        config = Config()
        profiles = config.list_proxy_profiles()
        active_profile = config.get_active_proxy_profile()

        if not profiles:
            console_manager.print("No proxy profiles configured.")
            console_manager.print_note(
                "Create a profile with: "
                "vibectl setup-proxy configure <profile-name> <server-url>"
            )
            return

        table = Table(title="Proxy Profiles")
        table.add_column("Profile Name")
        table.add_column("Status")
        table.add_column("Server URL")
        table.add_column("Security")

        for profile_name in profiles:
            profile_config = config.get_proxy_profile(profile_name)
            if not profile_config:
                continue

            # Status column
            if profile_name == active_profile:
                status = "[green]●[/green] Active"
            else:
                status = "[dim]○[/dim] Inactive"

            # Server URL (redacted)
            server_url = profile_config.get("server_url", "N/A")
            server_url = redact_jwt_in_url(server_url)

            # Security settings
            security_info = profile_config.get("security", {})
            security_parts = []
            if security_info.get("sanitize_requests"):
                security_parts.append("Sanitization")
            if security_info.get("audit_logging"):
                security_parts.append("Audit")
            security_text = ", ".join(security_parts) if security_parts else "None"

            table.add_row(profile_name, status, server_url, security_text)

        console_manager.safe_print(console_manager.console, table)

        if active_profile:
            console_manager.print_success(f"Active profile: {active_profile}")
        else:
            console_manager.print_note("No active profile (proxy disabled)")

    except Exception as e:
        handle_exception(e)


@setup_proxy_group.command("set-active")
@click.argument("profile_name")
def set_active_profile(profile_name: str) -> None:
    """Set the active proxy profile."""
    try:
        config = Config()

        # Check if profile exists
        if not config.get_proxy_profile(profile_name):
            console_manager.print_error(f"Profile '{profile_name}' not found.")
            profiles = config.list_proxy_profiles()
            if profiles:
                console_manager.print_note(f"Available profiles: {', '.join(profiles)}")
            else:
                console_manager.print_note(
                    "No profiles configured. Create one with: "
                    "vibectl setup-proxy configure <profile-name> <server-url>"
                )
            sys.exit(1)

        # Set as active
        config.set_active_proxy_profile(profile_name)

        console_manager.print_success(f"✓ Activated proxy profile: {profile_name}")

        # Show the profile configuration
        show_proxy_status()

    except Exception as e:
        handle_exception(e)


@setup_proxy_group.command("remove")
@click.argument("profile_name")
@click.option(
    "--mode",
    type=click.Choice(["manual", "auto", "semiauto"], case_sensitive=False),
    default=None,
    help="Execution mode: manual (confirmations enabled); auto (no confirmations)",
)
def remove_profile(profile_name: str, mode: str | None = None) -> None:
    """Remove a proxy profile."""
    try:
        exec_mode = execution_mode_from_cli(mode)
        if exec_mode is None:
            exec_mode = ExecutionMode.MANUAL

        skip_confirmation = exec_mode == ExecutionMode.AUTO

        config = Config()

        # Check if profile exists
        if not config.get_proxy_profile(profile_name):
            console_manager.print_error(f"Profile '{profile_name}' not found.")
            return

        # Confirm removal unless in AUTO mode
        if not skip_confirmation:
            active_profile = config.get_active_proxy_profile()
            warning = f"Remove proxy profile '{profile_name}'?"
            if profile_name == active_profile:
                warning += "\n\nThis is the active profile - "
                warning += "removing it will disable proxy mode."

            if not click.confirm(warning):
                console_manager.print("Removal cancelled.")
                return

        # Remove the profile
        config.remove_proxy_profile(profile_name)

        console_manager.print_success(f"✓ Removed proxy profile: {profile_name}")

        # Show updated status
        active_profile = config.get_active_proxy_profile()
        if not active_profile:
            console_manager.print_note("Proxy mode is now disabled.")

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


def _print_server_info(data: dict[str, Any]) -> None:
    """Render and print a rich table with server information.

    Args:
        data: Mapping returned from ``check_proxy_connection`` containing
            keys ``server_name``, ``version``, ``supported_models`` and an
            optional ``limits`` mapping.
    """
    info_table = Table(title="Server Information")
    info_table.add_column("Property")
    info_table.add_column("Value", style="green")

    # Required fields
    info_table.add_row("Server Name", data.get("server_name", "<unknown>"))
    info_table.add_row("Version", data.get("version", "<unknown>"))
    supported = ", ".join(data.get("supported_models", [])) or "<none>"
    info_table.add_row("Supported Models", supported)

    # Optional limits section for completeness
    limits = data.get("limits")
    if limits:
        info_table.add_row(
            "Max Request Size", f"{limits.get('max_request_size', '?')} bytes"
        )
        info_table.add_row(
            "Max Concurrent Requests", str(limits.get("max_concurrent_requests", "?"))
        )
        info_table.add_row(
            "Server Timeout", f"{limits.get('timeout_seconds', '?')} seconds"
        )

    console_manager.safe_print(console_manager.console, info_table)
