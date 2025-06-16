"""
Setup proxy command for configuring client proxy usage.

This module provides functionality to configure vibectl clients to use
a central LLM proxy server for model requests.
"""

import asyncio
import os
import sys
from pathlib import Path
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
from vibectl.types import Error, Result, Success
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

        # Initialize config object for CA bundle and fallback JWT resolution
        config = Config()

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
            # Fall back to embedded token or config resolution
            jwt_token = proxy_config.jwt_token or config.get_jwt_token()

        # Create gRPC channel directly
        if proxy_config.use_tls:
            # Get CA bundle path with precedence:
            # ca_bundle parameter > environment > config
            ca_bundle_path = ca_bundle or config.get_ca_bundle_path()

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


def configure_proxy_settings(
    proxy_url: str, ca_bundle: str | None = None, jwt_path: str | None = None
) -> Result:
    """Configure proxy settings in the configuration.

    Args:
        proxy_url: The proxy server URL (without JWT token embedded)
        ca_bundle: Optional path to CA bundle file for TLS verification
        jwt_path: Optional path to JWT token file for authentication

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
            return Error(error="Invalid proxy URL format")

        # Validate CA bundle file if provided
        if ca_bundle:
            ca_bundle_path = Path(ca_bundle).expanduser()
            if not ca_bundle_path.exists():
                return Error(error=f"CA bundle file not found: {ca_bundle}")
            if not ca_bundle_path.is_file():
                return Error(error=f"CA bundle path is not a file: {ca_bundle}")

        # Validate JWT path if provided
        if jwt_path:
            jwt_file_path = Path(jwt_path).expanduser()
            if not jwt_file_path.exists():
                return Error(error=f"JWT file not found: {jwt_path}")
            if not jwt_file_path.is_file():
                return Error(error=f"JWT path is not a file: {jwt_path}")

        # Get configuration
        config = Config()

        # Clean URL: remove any embedded JWT token to store clean URL
        clean_url = proxy_url
        if proxy_config.jwt_token:
            # Rebuild URL without JWT token
            scheme = (
                "vibectl-server" if proxy_config.use_tls else "vibectl-server-insecure"
            )
            clean_url = f"{scheme}://{proxy_config.host}:{proxy_config.port}"

        # Set proxy configuration
        config.set("proxy.enabled", True)
        config.set("proxy.server_url", clean_url)

        # Set CA bundle path if provided
        if ca_bundle:
            config.set(
                "proxy.ca_bundle_path", str(Path(ca_bundle).expanduser().absolute())
            )

        # Set JWT path if provided
        if jwt_path:
            config.set("proxy.jwt_path", str(Path(jwt_path).expanduser().absolute()))

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

        # Reset to defaults - clear all proxy-related settings
        config.unset("proxy.timeout_seconds")
        config.unset("proxy.retry_attempts")
        config.unset("proxy.ca_bundle_path")
        config.unset("proxy.jwt_path")

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
        skip_tls_verify = config.get("proxy.skip_tls_verify", False)

        # Create status table
        table = Table(title="Proxy Configuration Status")
        table.add_column("Setting")
        table.add_column("Value", style="green" if enabled else "red")

        table.add_row("Enabled", str(enabled))

        if enabled and server_url:
            table.add_row("Server URL", redact_jwt_in_url(server_url))
            table.add_row("Timeout (seconds)", str(timeout))
            table.add_row("Retry attempts", str(retries))

            # Show CA bundle information - use explicit sources only
            env_ca_bundle = os.environ.get("VIBECTL_CA_BUNDLE")
            config_ca_bundle = config.get("proxy.ca_bundle_path")

            if env_ca_bundle:
                table.add_row("CA Bundle Path", f"{env_ca_bundle} (from environment)")
                ca_exists = Path(env_ca_bundle).exists()
                table.add_row(
                    "CA Bundle Status", "✓ Found" if ca_exists else "❌ Missing"
                )
            elif config_ca_bundle:
                table.add_row("CA Bundle Path", f"{config_ca_bundle} (from config)")
                ca_exists = Path(config_ca_bundle).exists()
                table.add_row(
                    "CA Bundle Status", "✓ Found" if ca_exists else "❌ Missing"
                )
            else:
                table.add_row("CA Bundle Path", "None (system trust store)")

            # Show JWT token configuration
            env_jwt_token = os.environ.get("VIBECTL_JWT_TOKEN")
            config_jwt_path = config.get("proxy.jwt_path")
            embedded_jwt = None
            try:
                proxy_config = parse_proxy_url(server_url)
                embedded_jwt = proxy_config.jwt_token
            except Exception:
                pass

            if env_jwt_token:
                table.add_row("JWT Token", "*** (from environment)")
            elif config_jwt_path:
                jwt_exists = Path(config_jwt_path).exists()
                table.add_row("JWT Token Path", f"{config_jwt_path} (from config)")
                table.add_row(
                    "JWT Token Status", "✓ Found" if jwt_exists else "❌ Missing"
                )
            elif embedded_jwt:
                table.add_row("JWT Token", "*** (embedded in URL)")
            else:
                table.add_row("JWT Token", "None (no authentication)")

            table.add_row("Skip TLS Verify", str(skip_tls_verify))
        else:
            table.add_row("Server URL", "Not configured")
            table.add_row("Mode", "Direct LLM calls")

        console_manager.safe_print(console_manager.console, table)

        if enabled and server_url:
            console_manager.print_success(
                "Proxy is enabled. LLM calls will be forwarded to "
                "the configured server."
            )

            # Show TLS configuration info
            if server_url.startswith("vibectl-server://"):
                env_ca_bundle = os.environ.get("VIBECTL_CA_BUNDLE")
                config_ca_bundle = config.get("proxy.ca_bundle_path")

                if env_ca_bundle or config_ca_bundle:
                    ca_source = "environment" if env_ca_bundle else "config"
                    ca_path = env_ca_bundle or config_ca_bundle
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
@click.argument("proxy_url")
@click.option("--no-test", is_flag=True, help="Skip connection test")
@click.option("--ca-bundle", help="Path to custom CA bundle file for TLS verification")
@click.option("--jwt-path", help="Path to JWT token file for authentication")
async def setup_proxy_configure(
    proxy_url: str, no_test: bool, ca_bundle: str | None, jwt_path: str | None
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

                    info_table = Table(title="Server Information")
                    info_table.add_column("Property")
                    info_table.add_column("Value", style="green")

                    info_table.add_row("Server Name", data["server_name"])
                    info_table.add_row("Version", data["version"])
                    info_table.add_row(
                        "Supported Models", ", ".join(data["supported_models"])
                    )
                    info_table.add_row(
                        "Max Request Size",
                        f"{data['limits']['max_request_size']} bytes",
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
        config_result = configure_proxy_settings(
            proxy_url, ca_bundle=final_ca_bundle, jwt_path=jwt_path
        )

        if isinstance(config_result, Error):
            console_manager.print_error(f"Configuration failed: {config_result.error}")
            sys.exit(1)

        console_manager.print_success("✓ Proxy configuration saved!")

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

            console_manager.print(
                f"Testing configured proxy: {redact_jwt_in_url(server_url)}"
            )
        else:
            console_manager.print(f"Testing proxy: {redact_jwt_in_url(server_url)}")

        # Test connection (use config-stored CA bundle if no explicit jwt_path provided)
        result = await check_proxy_connection(
            server_url, timeout_seconds=timeout, jwt_path=jwt_path
        )

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
