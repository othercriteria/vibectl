# vibectl

A vibes-based alternative to kubectl for interacting with Kubernetes clusters. Make
your cluster management more intuitive and fun!

## Features

- 🌟 LLM-powered Kubernetes interaction with natural language support
- 🧠 Memory-aware contextual operations across commands
- 🚀 Intuitive commands that simplify common Kubernetes tasks
- 🎯 Streamlined cluster management workflows
- 🎮 **NEW:** Semi-autonomous mode with iterative feedback
- 🔍 Context-aware command suggestions
- ✨ AI-powered cluster state analysis and summaries
- 🎨 Theme support with configurable visual styles
- 📊 Resource-specific smart output formatting
- 🐒 Chaos-monkey simulation for resilience testing

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
   export ANTHROPIC_API_KEY=your-api-key

   # For OpenAI
   export OPENAI_API_KEY=your-api-key

   # Using vibectl config (more permanent)
   vibectl config set model_keys.anthropic your-api-key

   # Using key files (more secure)
   echo "your-api-key" > ~/.config/vibectl/keys/anthropic
   chmod 600 ~/.config/vibectl/keys/anthropic
   vibectl config set model_key_files.anthropic ~/.config/vibectl/keys/anthropic
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

```text
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

When run without arguments, `vibectl vibe` uses memory context to determine what to do next. If no memory exists, it begins with discovery commands:

```text
Command: vibectl vibe

Planning: Need to understand the cluster context first
Action: kubectl cluster-info
Confirmation: [Y/n]

Updated Memory: "We are working with a Kubernetes cluster running version 1.25.4
with control plane at https://cluster.example.com. Next, we should understand
what namespaces and workloads are available."
```

### Semi-Autonomous Mode with `vibectl semiauto`

The `vibectl semiauto` command provides an interactive, iterative approach to cluster management with more control than full autonomous mode:

```zsh
# Start a semi-autonomous session
vibectl semiauto

# Start with specific context
vibectl memory set "Working in staging namespace" && vibectl semiauto
```

The `semiauto` command is ideal when you want a more controlled, step-by-step approach:

1. It suggests commands based on memory context
2. You confirm, reject, or modify each suggestion
3. Memory updates after each iteration
4. The session continues until you explicitly exit

#### Interactive Options

For each suggested command, you have multiple response options:

- `[Y]es` - Execute the command as suggested
- `[N]o` - Skip this command without updating memory
- `yes [A]nd` - Execute command and add more context to memory
- `no [B]ut` - Skip command and provide alternate direction
- `[E]xit` - End the semiauto session

#### Example Session

```text
❯ vibectl memory set "We're working in 'sandbox' namespace. Tear down any existing demos."
Memory set

❯ vibectl semiauto
Note: Starting vibectl semiauto session
Note: Commands will require confirmation.
Note: --- Iteration 1 ---
🔄 Planning next steps based on memory context...
Note: Planning to run: kubectl delete all --all -n sandbox
Note:
[Y]es, [N]o, yes [A]nd, no [B]ut, or [E]xit? (y/n/a/b/e) b

Warning: Command cancelled
Note: Enter additional information for memory:
Memory update: Take a quick look first, and do specific deletions.
🔄 Updating memory...

Note: --- Iteration 2 ---
🔄 Planning next steps based on memory context...
Note: Planning to run: kubectl get pods,deployments,services -n sandbox
Note:
[Y]es, [N]o, yes [A]nd, no [B]ut, or [E]xit? (y/n/a/b/e) y

✨ Vibe check:
🚀 1 pod running in sandbox namespace 🟢
🏭 nginx-demo deployment is healthy (1/1) with age: 73m 🌱
🔌 nginx-demo service available at 10.43.43.113:80 as ClusterIP type 🌐

Note: --- Iteration 3 ---
🔄 Planning next steps based on memory context...
Note: Planning to run: kubectl delete deployment,service nginx-demo -n sandbox
Note:
[Y]es, [N]o, yes [A]nd, no [B]ut, or [E]xit? (y/n/a/b/e) y

✅ Successfully deleted resources in sandbox namespace
```

### Other Common Commands

```zsh
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

# Use a different LLM model
vibectl config set model claude-3.7-sonnet  # Default Anthropic model
vibectl config set model claude-3.5-sonnet  # Smaller Anthropic model
vibectl config set model gpt-4o             # OpenAI model
vibectl config set model ollama:llama3:latest  # Local Ollama model (or just llama3 if that's the alias)

# ⚠️ **Ollama Model String Requirements:**
# The model string must match the name or alias as shown in `llm models`.
# For example, if `llm models` shows `Ollama: tinyllama:latest (aliases: tinyllama)`, you can use `tinyllama` (the alias) or the full name.
# vibectl now accepts providerless model aliases (like `tinyllama`) as valid model values for compatibility with llm-ollama. This is a recent change and may be revisited for stricter validation in the future.
# If you get an 'Unknown model' error, run `llm models` and use one of the listed names/aliases.

# Configure API keys (multiple methods available)
vibectl config set model_keys.anthropic your-api-key
vibectl config set model_key_files.openai ~/.config/vibectl/keys/openai

# Control output display
vibectl config set show_raw_output true    # Always show raw kubectl output
vibectl config set show_kubectl true       # Show kubectl commands being executed

# Set visual theme
vibectl theme set dark
vibectl theme set light
vibectl theme set system
```

For detailed API key management options, see [Model API Key Management](docs/MODEL_KEYS.md).

### Logging

vibectl now includes structured, configurable logging to improve observability and debugging.

- **Log Levels:** Control verbosity via config or environment variable:
  - `vibectl config set log_level INFO` (or DEBUG, WARNING, ERROR)
  - Or set `VIBECTL_LOG_LEVEL=DEBUG` in your environment
- **User-Facing Logs:**
  - Warnings and errors are surfaced to the user via the console (with color and style)
  - Info/debug logs are only shown in verbose/debug mode (future extension)
- **No Duplicate Messages:**
  - Normal operation only shows user-facing messages; verbose/debug mode can surface more logs
- **Extensible:**
  - Logging is designed for future support of file logging, JSON logs, etc.

Example:
```zsh
# Set log level to DEBUG for troubleshooting
export VIBECTL_LOG_LEVEL=DEBUG
vibectl get pods
```

You can also set the log level permanently in your config:
```zsh
vibectl config set log_level DEBUG
```

See warnings and errors directly in your terminal, while info/debug logs are available for advanced troubleshooting.

### Chaos Monkey Example

The chaos-monkey example demonstrates vibectl's capabilities for testing Kubernetes cluster resilience using the new `auto` subcommand:

```zsh
# Navigate to the example directory
cd examples/k8s-sandbox/chaos-monkey

# Set up the demo environment
./setup.sh

# Start the red vs. blue team scenario
./start-scenario.sh
```

The chaos-monkey example includes:
- Red team vs. blue team competitive scenario
- Containerized vibectl agents using `vibectl auto` for continuous operation
- Autonomous mode with memory-based decision making
- Metrics collection for performance evaluation
- Configurable disruption patterns and recovery strategies
- Real-time dashboard for monitoring the simulation

See the [examples/k8s-sandbox/chaos-monkey/README.md](examples/k8s-sandbox/chaos-monkey/README.md) file for detailed setup instructions and scenarios.

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

```text
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

Several testing options are available, optimized for different needs:

```zsh
# Run all tests with coverage
make test

# Run tests in parallel for faster feedback (no coverage)
make test-parallel

# Run fast tests only (for quick development feedback)
make test-fast

# Run tests with detailed coverage report
make test-coverage
```

See [tests/TESTING.md](tests/TESTING.md) for detailed information about test performance optimizations and best practices for writing efficient tests.

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

## Examples and Demos

- **Kubernetes CTF Sandbox**: Challenge-based learning environment for vibectl autonomy. See `examples/k8s-sandbox/ctf/README.md`.
- **Chaos Monkey**: Red/blue team competitive scenario for resilience testing. See `examples/k8s-sandbox/chaos-monkey/README.md`.
- **Bootstrap Demo**: Self-contained k3d (K3s in Docker) + Ollama environment, with vibectl configured to use the local LLM and automated demonstration of Kubernetes analysis. See `examples/k8s-sandbox/bootstrap/README.md`.
- **Kafka Throughput Demo**: Demonstrates vibectl tuning Kafka performance under synthetic load within a K3d environment. Includes adaptive producer load, consumer rate monitoring, and a web UI displaying key metrics, health status, and vibectl agent logs. See `examples/k8s-sandbox/kafka-throughput/README.md`.

## Development Workflow

- Use Git worktrees for all feature development. See `.cursor/rules/feature-worktrees.mdc` for the required workflow.

## Demos

This repository includes several demonstration environments in the `examples/` directory:

- **Bootstrap Demo (`examples/k8s-sandbox/bootstrap/`)**: Sets up a local K3d cluster with Ollama, demonstrating `vibectl` with local LLMs for cluster analysis.
- **CTF Demo (`examples/k8s-sandbox/ctf/`)**: A Capture The Flag style scenario where `vibectl` autonomously navigates and interacts within a Kubernetes sandbox.
- **Chaos Monkey Demo (`examples/k8s-sandbox/chaos-monkey/`)**: Features two `vibectl` agents (Red vs. Blue) competing in a Kubernetes environment, showcasing autonomous attack and defense strategies.
- **Kafka Throughput Demo (`examples/k8s-sandbox/kafka-throughput/`)**: Demonstrates `vibectl` autonomously tuning Kafka broker performance (heap, threads) based on real-time latency metrics from producer/consumer applications running within a K3d cluster.

Each demo has its own `README.md` and `STRUCTURE.md` with specific setup and usage instructions.

See [Development Workflow](STRUCTURE.md#development-workflow) in the `STRUCTURE.md` file for details on setting up a development environment, using Git worktrees, running tests, and contributing.
