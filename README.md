# vibectl

A vibes-based alternative to kubectl for interacting with Kubernetes clusters. Make
your cluster management more intuitive and fun!

## Features

- 🌟 Vibes-based interaction with Kubernetes clusters
- 🚀 Intuitive commands that just feel right
- 🎯 Simplified cluster management
- 🔍 Smart context awareness
- ✨ AI-powered summaries of cluster state
- 🧠 Natural language resource queries
- 🎨 Theme support with multiple visual styles
- 📊 Intelligent output formatting for different resource types
- 🧠 Context-aware memory between commands

## Requirements

- Python 3.10+
- [Flake](https://flake.build)
- Anthropic API key (for Claude models)

## Installation

1. Install [Flake](https://flake.build)
2. Clone and set up:
   ```zsh
   git clone https://github.com/othercriteria/vibectl.git
   cd vibectl
   flake develop
   ```
3. Configure your Anthropic API key:
   ```zsh
   export ANTHROPIC_API_KEY=your-api-key
   ```

The development environment will automatically:
- Create and activate a Python virtual environment
- Install all dependencies including development tools
- Set up the Anthropic LLM provider

## Usage

Basic commands with AI-powered summaries:

```zsh
# Display version and configuration
vibectl version
vibectl config show

# Get cluster information
vibectl cluster-info                              # Show cluster info with insights
vibectl cluster-info dump                         # Detailed cluster information
vibectl cluster-info vibe how healthy is my control plane  # Natural language query

# Get resources
vibectl get pods                                    # List pods with summary
vibectl get vibe show me pods with high restarts   # Natural language query

# Create resources
vibectl create -f manifest.yaml                     # Create from file
vibectl create vibe an nginx pod with 3 replicas   # Natural language creation

# Describe resources
vibectl describe deployment my-app                  # Get detailed info
vibectl describe vibe tell me about the nginx pods  # Natural language query

# View logs
vibectl logs pod/my-pod                            # Get pod logs
vibectl logs vibe show errors from frontend pods   # Natural language query

# Direct kubectl access
vibectl just get pods                              # Pass directly to kubectl
```

### Memory

vibectl maintains context between command invocations with its memory feature:

```zsh
# View current memory
vibectl memory show

# Manually set memory content
vibectl memory set "Running backend deployment in staging namespace"

# Edit memory in your preferred editor
vibectl memory set --edit

# Clear memory content
vibectl memory clear

# Control memory updates
vibectl memory disable      # Stop updating memory
vibectl memory enable       # Resume memory updates
vibectl memory freeze       # Alias for disable
vibectl memory unfreeze     # Alias for enable

# One-time memory control flags
vibectl get pods --freeze-memory     # Don't update memory for this command
vibectl get pods --unfreeze-memory   # Allow memory update for this command
```

Memory helps vibectl understand context from previous commands, enabling references
like "the namespace I mentioned earlier" without repeating information.

Future memory enhancements:
- Selective memory by namespace or context
- Memory visualization and insights
- Memory export/import for sharing context
- Memory search capabilities
- Persistence of memory across different terminals/sessions
- Memory organization by clusters and contexts

### Configuration

```zsh
# Set a custom kubeconfig file
vibectl config set kubeconfig /path/to/kubeconfig

# Use a different LLM model (default: claude-3.7-sonnet)
vibectl config set llm_model your-preferred-model

# Always show raw kubectl output
vibectl config set show_raw_output true

# Always show vibe output
vibectl config set show_vibe true

# Suppress warning when no output is enabled
vibectl config set suppress_output_warning true

# Set visual theme
vibectl theme set dark
```

### Custom Instructions

You can customize how vibectl generates responses by setting custom instructions
that will be included in all vibe prompts:

```zsh
# Set custom instructions
vibectl instructions set "Use a ton of emojis! 😁"

# Set multiline instructions
echo "Redact the last 3 octets of IPs.
Focus on security issues." | vibectl instructions set

# View current instructions
vibectl instructions show

# Clear instructions
vibectl instructions clear
```

Typical use cases for custom instructions:
- Style preferences: "Use a ton of emojis! 😁"
- Security requirements: "Redact the last 3 octets of IPs."
- Focus areas: "Focus on security issues."
- Output customization: "Be extremely concise."

### Theme Management

The tool supports multiple visual themes for the console output:

```zsh
# List available themes
vibectl theme list

# Set a theme
vibectl theme set <theme-name>
```

Available themes:
- `default` - Standard theme with clean, subtle colors
- `dark` - Enhanced contrast for dark backgrounds
- `light` - Enhanced readability for light backgrounds
- `accessible` - Designed for improved accessibility

Theme changes are persisted in your configuration and apply to all vibectl commands.

### Output Behavior

By default, vibectl will show:
- Raw output when `--show-raw-output` or `--raw` flag is used
- Vibe summaries when `--show-vibe` flag is used (enabled by default)

When neither raw output nor vibe output is enabled, a warning will be displayed
but no output will be shown. This behavior respects user choices rather than
guessing intent.

If you wish to suppress the warning for no enabled outputs, you can set:
```zsh
vibectl config set suppress_output_warning true
```

All output settings can be controlled using:
- Command-line flags: `--show-raw-output` / `--no-show-raw-output` and `--show-vibe` / `--no-show-vibe`
- Configuration: `vibectl config set show_raw_output true|false` and `vibectl config set show_vibe true|false`

### Output Formatting

Commands provide AI-powered summaries using rich text formatting:
- Resource names and counts in **bold**
- Healthy/good status in green
- Warnings in yellow
- Errors in red
- Kubernetes concepts in blue
- Timing information in *italics*

Example:
```
[bold]3 pods[/bold] in [blue]default namespace[/blue], all [green]Running[/green]
[bold]nginx-pod[/bold] [italic]running for 2 days[/italic]
[yellow]Warning: 2 pods have high restart counts[/yellow]
```

The tool intelligently processes different output types:
- Log outputs with special handling for recent entries
- YAML resources with section-aware formatting
- JSON with smart object and array truncation
- Plain text with balanced truncation when needed

### Natural Language Support

The `vibe` subcommand supports natural language for all operations:

```zsh
# Find resources
vibectl get vibe show me pods in kube-system
vibectl get vibe find pods with high restart counts

# Create resources
vibectl create vibe a redis pod with persistent storage
vibectl create vibe a deployment with 3 nginx replicas

# Describe resources
vibectl describe vibe tell me about the nginx pods
vibectl describe vibe what's wrong with the database

# View logs
vibectl logs vibe show me recent errors
vibectl logs vibe what's happening in the api pods
```

## Project Structure

For a comprehensive overview of the project's structure and organization, please see
[STRUCTURE.md](STRUCTURE.md). This documentation is maintained according to our
[project structure rules](.cursor/rules/project-structure.mdc) to ensure it stays
up-to-date and accurate.

## Development

This project uses [Flake](https://flake.build) for development environment
management. The environment is automatically set up when you run `flake develop`.

### Running Tests

```zsh
pytest
```

### Code Quality

The project uses pre-commit hooks for code quality, configured in
`.pre-commit-config.yaml`. These run automatically on commit and include:
- Ruff format for code formatting (replaces Black)
- Ruff check for linting and error detection (replaces Flake8)
- Ruff check --fix for import sorting (replaces isort)
- MyPy for type checking

Configuration for Ruff is managed in the `pyproject.toml` file under the
`[tool.ruff]` section.

### Cursor Rules

The project uses Cursor rules (`.mdc` files in `.cursor/rules/`) to maintain
consistent development practices. For details on these rules, including their
purpose and implementation, see [RULES.md](RULES.md).

Our rules system covers:
- Code quality and style enforcement
- Test organization and coverage requirements
- Documentation standards
- Build system conventions
- Commit automation

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file
for details.
