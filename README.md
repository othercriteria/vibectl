# vibectl

A vibes-based alternative to kubectl for interacting with Kubernetes clusters. Make
your cluster management more intuitive and fun!

## Features

- 🌟 Vibes-based interaction with Kubernetes clusters
- 🧠 Memory-aware autonomous Kubernetes operations
- 🚀 Intuitive commands that just feel right
- 🎯 Simplified cluster management
- 🔍 Smart context awareness
- ✨ AI-powered summaries of cluster state
- 🧠 Natural language resource queries
- 🎨 Theme support with multiple visual styles
- 📊 Intelligent output formatting for different resource types

## Requirements

- Python 3.10+
- kubectl command-line tool installed and in your PATH
- API key for your chosen LLM provider:
  - Anthropic API key (for Claude models, default)
  - OpenAI API key (for GPT models)
  - Ollama (for local models, no API key required)

## Installation

### Option 1: Standard Pip Installation (Non-NixOS users)

1. Install using pip:
   ```zsh
   pip install vibectl
   ```

2. Install the LLM provider for your chosen model:
   ```zsh
   # For Anthropic (Claude) models (default)
   pip install llm-anthropic
   llm install llm-anthropic

   # For OpenAI models
   pip install llm-openai
   llm install llm-openai

   # For Ollama (local models)
   pip install llm-ollama
   llm install llm-ollama
   ```

3. Configure your API key (using one of these methods):
   ```zsh
   # For Anthropic (default model)
   export VIBECTL_ANTHROPIC_API_KEY=your-api-key

   # For OpenAI
   export VIBECTL_OPENAI_API_KEY=your-api-key

   # Using config (more permanent)
   vibectl config set model_keys.anthropic your-api-key

   # Using key files (more secure)
   echo "your-api-key" > ~/.anthropic-key
   chmod 600 ~/.anthropic-key
   vibectl config set model_key_files.anthropic ~/.anthropic-key
   ```

See [Model API Key Management](docs/MODEL_KEYS.md) for more detailed configuration options.

### Option 2: Development Installation with Flake (NixOS users)

1. Install [Flake](https://flake.build)
2. Clone and set up:
   ```zsh
   git clone https://github.com/othercriteria/vibectl.git
   cd vibectl
   flake develop
   ```
3. Configure your API key for your chosen model (see above)

The development environment will automatically:
- Create and activate a Python virtual environment
- Install all dependencies including development tools
- Set up the Anthropic LLM provider

## Usage

### Autonomous Mode with `vibectl vibe`

The `vibectl vibe` command is a powerful, memory-aware tool that can autonomously
plan and execute Kubernetes operations:

```zsh
# Use with a specific request
vibectl vibe "create a deployment for our frontend app"

# Use without arguments - autonomous mode based on memory context
vibectl vibe

# Continue working on a previous task
vibectl vibe "continue setting up the database system"
```

The `vibe` command works by:
1. Understanding your cluster context from memory
2. Planning appropriate actions
3. Executing kubectl commands with your confirmation
4. Updating memory with results
5. Planning next steps

#### Example Flow with Memory

```
Memory: "We are working in `foo` namespace. We have created deployment `bar`.
We need to create a service for `bar`."

Command: vibectl vibe "keep working on the bar system"

Planning: Need to create a service for the bar deployment
Action: kubectl create service clusterip bar-service --tcp=80:8080
Confirmation: [Y/n]

Updated Memory: "We are working in the `foo` namespace. We have created
deployment `bar` with service `bar-service`. We don't know if it is alive yet."
```

#### No-Argument Mode

When run without arguments, `vibectl vibe` uses memory context to determine what
to do next. If no memory exists, it begins with discovery commands:

```
Command: vibectl vibe

Planning: Need to understand the cluster context first
Action: kubectl cluster-info
Confirmation: [Y/n]

Updated Memory: "We are working with a Kubernetes cluster running version 1.25.4
with control plane at https://cluster.example.com. Next, we should understand
what namespaces and workloads are available."
```

### Other Common Commands

```zsh
# Display version and configuration
vibectl version
vibectl config show

# Basic operations with AI-powered summaries
vibectl get pods                                  # List pods with summary
vibectl describe deployment my-app                # Get detailed info
vibectl logs pod/my-pod                          # Get pod logs
vibectl scale deployment/nginx --replicas=3      # Scale a deployment

# Natural language commands
vibectl get vibe show me pods with high restarts
vibectl create vibe an nginx pod with 3 replicas
vibectl delete vibe remove all failed pods
vibectl describe vibe what's wrong with the database

# Direct kubectl access
vibectl just get pods                            # Pass directly to kubectl
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
```

Memory helps vibectl understand context from previous commands, enabling references
like "the namespace I mentioned earlier" without repeating information. This is
especially powerful with the autonomous `vibectl vibe` command.

### Configuration

```zsh
# Set a custom kubeconfig file
vibectl config set kubeconfig /path/to/kubeconfig

# Use a different LLM model (default: claude-3.7-sonnet)
vibectl config set model claude-3.7-sonnet  # Default
vibectl config set model gpt-4              # OpenAI
vibectl config set model ollama:llama3      # Local Ollama

# Configure API keys (multiple methods available)
vibectl config set model_keys.anthropic your-api-key
vibectl config set model_key_files.openai /path/to/key-file

# Control output display
vibectl config set show_raw_output true    # Always show raw kubectl output
vibectl config set show_kubectl true       # Show kubectl commands being executed

# Set visual theme
vibectl theme set dark
```

For detailed API key management options, see [Model API Key Management](docs/MODEL_KEYS.md).

### Custom Instructions

You can customize how vibectl generates responses by setting custom instructions
that will be included in all vibe prompts:

```zsh
# Set custom instructions
vibectl instructions set "Use a ton of emojis! 😁"

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

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file
for details.
