# Configuration Reference

This document describes all available configuration options for vibectl. Configuration uses a hierarchical structure organized into logical sections.

## Client Configuration

### Memory Content (Top-level)

| Key               | Type                | Default  | Description                   |
|-------------------|---------------------|----------|-------------------------------|
| memory_content    | string or null      | null     | Auto-managed memory content from `vibectl memory` commands. |

### Core Settings

| Key                    | Type                | Default  | Description                   |
|------------------------|---------------------|----------|-------------------------------|
| core.kubeconfig        | string or null      | null     | Path to kubeconfig file. If null, the default kubectl config is used. |
| core.kubectl_command   | string              | kubectl  | Command to use for kubectl operations. |

### Display Settings

| Key                         | Type                | Default    | Description                   |
|-----------------------------|---------------------|------------|-------------------------------|
| display.theme               | string              | default    | Theme for terminal output. Valid values: default, dark, light, accessible. |
| display.show_raw_output     | boolean             | false      | Whether to show raw kubectl output. |
| display.show_vibe           | boolean             | true       | Whether to show vibe (LLM) output. |
| display.show_kubectl        | boolean             | false      | Whether to show kubectl commands when they are executed. |
| display.show_memory         | boolean             | true       | Show memory content before each auto/semiauto iteration. |
| display.show_iterations     | boolean             | true       | Show iteration count and limit in auto/semiauto mode. |
| display.show_metrics        | string              | none       | Show LLM metrics. Valid values: none, total, sub, all. |
| display.show_streaming      | boolean             | true       | Show intermediate streaming Vibe output. |

### LLM Settings

| Key                           | Type                | Default           | Description                   |
|-------------------------------|---------------------|-------------------|-------------------------------|
| llm.model                     | string              | claude-3.7-sonnet | LLM model to use. Validated against supported models. |
| llm.max_retries               | integer             | 2                 | Maximum retries for LLM calls. |
| llm.retry_delay_seconds       | float               | 1.0               | Delay between retries in seconds. |

### Provider Settings

| Key                           | Type                | Default  | Description                   |
|-------------------------------|---------------------|----------|-------------------------------|
| providers.openai.key          | string or null      | null     | OpenAI API key. Can be overridden by VIBECTL_OPENAI_API_KEY environment variable. |
| providers.openai.key_file     | string or null      | null     | Path to file containing OpenAI API key. Can be overridden by VIBECTL_OPENAI_API_KEY_FILE environment variable. |
| providers.anthropic.key       | string or null      | null     | Anthropic API key. Can be overridden by VIBECTL_ANTHROPIC_API_KEY environment variable. |
| providers.anthropic.key_file  | string or null      | null     | Path to file containing Anthropic API key. Can be overridden by VIBECTL_ANTHROPIC_API_KEY_FILE environment variable. |
| providers.ollama.key          | string or null      | null     | Ollama API key (if needed). Can be overridden by VIBECTL_OLLAMA_API_KEY environment variable. |
| providers.ollama.key_file     | string or null      | null     | Path to file containing Ollama API key (if needed). Can be overridden by VIBECTL_OLLAMA_API_KEY_FILE environment variable. |

### Memory Settings

| Key                  | Type                | Default  | Description                   |
|----------------------|---------------------|----------|-------------------------------|
| memory.enabled       | boolean             | true     | Whether to enable memory context. |
| memory.max_chars     | integer             | 500      | Maximum characters for memory context preview. |

### Warning Settings

| Key                     | Type                | Default  | Description                   |
|-------------------------|---------------------|----------|-------------------------------|
| warnings.warn_no_output | boolean             | true     | Whether to warn when no output will be shown. |
| warnings.warn_no_proxy  | boolean             | true     | Show warning when `intermediate_port_range` is not set and proxy is needed. |

### Live Display Settings

| Key                                      | Type                | Default  | Description                   |
|------------------------------------------|---------------------|----------|-------------------------------|
| live_display.max_lines                   | integer             | 20       | Default number of lines for interactive live displays (`watch`, `follow`). |
| live_display.wrap_text                   | boolean             | true     | Default for wrapping text in interactive live displays. |
| live_display.stream_buffer_max_lines     | integer             | 100000   | Max lines held in memory for live display stream buffer. |
| live_display.default_filter_regex        | string or null      | null     | Default regex filter applied to interactive live displays. |
| live_display.save_dir                    | string              | .        | Default directory to save output from interactive live displays. |

### Feature Settings

| Key                               | Type                | Default  | Description                   |
|-----------------------------------|---------------------|----------|-------------------------------|
| features.intelligent_apply        | boolean             | true     | Enable intelligent apply features. |
| features.intelligent_edit         | boolean             | true     | Enable intelligent edit features. |
| features.max_correction_retries   | integer             | 1        | Maximum correction retries for intelligent features. |
| features.check_max_iterations     | integer             | 10       | Default max iterations for `vibectl check` command. |

### Networking Settings

| Key                                  | Type                | Default  | Description                   |
|--------------------------------------|---------------------|----------|-------------------------------|
| networking.intermediate_port_range   | string or null      | null     | Port range for traffic monitoring proxy in port-forward commands (format: "start-end", e.g. "10000-11000"). When set, enables detailed traffic monitoring. |

### Plugin Settings

| Key                   | Type                | Default  | Description                   |
|-----------------------|---------------------|----------|-------------------------------|
| plugins.precedence    | array               | []       | Plugin precedence order. Empty list means no explicit order. |

### Proxy Settings

| Key                         | Type                | Default  | Description                   |
|-----------------------------|---------------------|----------|-------------------------------|
| proxy.enabled               | boolean             | false    | Enable proxy mode for LLM calls. |
| proxy.server_url            | string or null      | null     | Server URL (format: vibectl-server://[token@]host:port or vibectl-server-insecure://[token@]host:port). |
| proxy.timeout_seconds       | integer             | 30       | Request timeout for proxy calls. Range: 1-300 seconds. |
| proxy.retry_attempts        | integer             | 3        | Number of retry attempts for failed proxy calls. Range: 0-10. |

### System Settings

| Key                           | Type                | Default  | Description                   |
|-------------------------------|---------------------|----------|-------------------------------|
| system.log_level              | string              | WARNING  | Log level. Valid values: DEBUG, INFO, WARNING, ERROR, CRITICAL. |
| system.custom_instructions    | string or null      | null     | Custom instructions for LLM interactions. Managed through `vibectl instructions` subcommand. |

## Server Configuration

The vibectl server component has its own separate configuration file and settings. These are managed through the `vibectl-server` command.

### Server Settings

| Key                    | Type                | Default                           | Description                   |
|------------------------|---------------------|-----------------------------------|-------------------------------|
| server.host            | string              | 0.0.0.0                          | Host to bind the gRPC server to. |
| server.port            | integer             | 50051                            | Port to bind the gRPC server to. |
| server.default_model   | string              | anthropic/claude-3-7-sonnet-latest | Default LLM model for server requests. If null, clients must specify model. |
| server.max_workers     | integer             | 10                               | Maximum number of worker threads for the server. |
| server.log_level       | string              | INFO                             | Server log level. Valid values: DEBUG, INFO, WARNING, ERROR, CRITICAL. |
| server.require_auth    | boolean             | false                            | Whether to require JWT authentication for all server requests. |

### JWT Authentication Settings

| Key                     | Type                | Default          | Description                   |
|-------------------------|---------------------|------------------|-------------------------------|
| jwt.secret_key          | string or null      | null             | JWT signing secret key. If null, will use environment variable or generate one. |
| jwt.secret_key_file     | string or null      | null             | Path to file containing JWT secret key. |
| jwt.algorithm           | string              | HS256            | JWT signing algorithm. |
| jwt.issuer              | string              | vibectl-server   | JWT issuer identifier. |
| jwt.expiration_days     | integer             | 30               | Default token expiration time in days. |

## Notes

- **Environment Variables**: API keys can be provided via environment variables (see Provider Settings for variable names).
- **File-based Keys**: API keys can also be read from files specified in the `key_file` settings.
- **Model Validation**: The `llm.model` setting is validated against supported models by the LLM interface.
- **Memory Management**: The `memory_content` key is auto-managed by `vibectl memory` commands.
- **Custom Instructions**: The `system.custom_instructions` key is primarily managed through the `vibectl instructions` subcommand.
- **Proxy URL Format**: When using proxy mode, URLs should follow the format `vibectl-server://[jwt-token@]host:port` for secure connections or `vibectl-server-insecure://[jwt-token@]host:port` for insecure connections.
- **Hierarchical Access**: All settings can be accessed using dotted notation (e.g., `display.theme`, `llm.model`).
- **Server Configuration**: Server configuration is separate from client configuration and managed through `vibectl-server init-config` and located in the server config directory.
- **JWT Secret Key**: The server JWT secret key can be provided via environment variable `VIBECTL_JWT_SECRET_KEY` or generated automatically.

For more information on model API key management, see [Model API Key Management](MODEL_KEYS.md).
