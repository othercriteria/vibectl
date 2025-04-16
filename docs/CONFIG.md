| Key               | Type                | Default  | Description                   |
|-------------------|---------------------|----------|-------------------------------|
| kubeconfig        | string or null      | null     | Path to kubeconfig file. If null, the default kubectl config is used. |
| kubectl_command   | string              | kubectl  | Command to use for kubectl.   |
| theme             | string              | dark     | Theme for terminal output.    |
| use_emoji         | boolean             | true     | Whether to use emoji in output. |
| show_raw_output   | boolean             | false    | Whether to show raw kubectl output. |
| show_vibe         | boolean             | true     | Whether to show vibe output.  |
| show_kubectl      | boolean             | false    | Whether to show kubectl commands when they are executed. |
| model             | string              | claude-3.7-sonnet | LLM model to use.    |
| memory_enabled    | boolean             | true     | Whether to enable memory context. |
| memory_max_chars  | integer             | 500      | Maximum characters for memory context preview. |
| warn_no_output    | boolean             | true     | Whether to warn when no output will be shown. |
| colored_output    | boolean             | true     | Whether to use colored output. |
| model_keys        | object              | {}       | API keys for LLM models.      |
| model_key_files   | object              | {}       | Paths to files containing API keys. |
| intermediate_port_range | string or null | null    | Port range for traffic monitoring proxy in port-forward commands (format: "start-end", e.g. "10000-11000"). When set, enables detailed traffic monitoring. |
