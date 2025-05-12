| Key               | Type                | Default  | Description                   |
|-------------------|---------------------|----------|-------------------------------|
| kubeconfig        | string or null      | null     | Path to kubeconfig file. If null, the default kubectl config is used. |
| kubectl_command   | string              | kubectl  | Command to use for kubectl.   |
| theme             | string              | dark     | Theme for terminal output.    |
| show_raw_output   | boolean             | false    | Whether to show raw kubectl output. |
| show_vibe         | boolean             | true     | Whether to show vibe output.  |
| show_kubectl      | boolean             | false    | Whether to show kubectl commands when they are executed. |
| model             | string              | claude-3.7-sonnet | LLM model to use.    |
| show_metrics      | boolean             | false    | Show LLM metrics (latency, tokens). |
| memory_enabled    | boolean             | true     | Whether to enable memory context. |
| memory_max_chars  | integer             | 500      | Maximum characters for memory context preview. |
| warn_no_output    | boolean             | true     | Whether to warn when no output will be shown. |
| colored_output    | boolean             | true     | Whether to use colored output. |
| model_keys        | object              | {}       | API keys for LLM models.      |
| model_key_files   | object              | {}       | Paths to files containing API keys. |
| intermediate_port_range | string or null | null    | Port range for traffic monitoring proxy in port-forward commands (format: "start-end", e.g. "10000-11000"). When set, enables detailed traffic monitoring. |
| show_memory       | boolean             | false    | Show memory content before each auto/semiauto iteration. |
| show_iterations   | boolean             | false    | Show iteration count and limit in auto/semiauto mode. |
| warn_no_proxy     | boolean             | true     | Show warning when `intermediate_port_range` is not set and proxy is needed. |
| log_level         | string              | WARNING  | Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL). |
| live_display_max_lines | integer        | 20       | Default number of lines for interactive live displays (`watch`, `follow`). |
| live_display_wrap_text | boolean        | true     | Default for wrapping text in interactive live displays. |
| live_display_stream_buffer_max_lines | integer | 100000   | Max lines held in memory for live display stream buffer. |
| live_display_default_filter_regex | string or null | null | Default regex filter applied to interactive live displays. |
| live_display_save_dir | string          | .        | Default directory to save output from interactive live displays. |

**Notes:**

- The `memory` and `custom_instructions` keys exist in the configuration schema but do not have default values defined directly in `vibectl/config.py`. They are primarily managed through the `vibectl memory` and `vibectl instructions` subcommands, respectively. See the main README for usage of these commands.
- Model names and API keys are handled specially. See [Model API Key Management](MODEL_KEYS.md) for details.
