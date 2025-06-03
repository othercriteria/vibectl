"""
Shared prompt utilities and formatting functions.

This module contains common prompt utilities that are used across multiple
prompt modules to avoid duplication and ensure consistency.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from datetime import datetime
from typing import Any

from vibectl.config import Config
from vibectl.schema import LLMAction
from vibectl.types import (
    Examples,
    Fragment,
    MLExampleItem,
    PromptFragments,
    SystemFragments,
    UserFragments,
)


def format_ml_examples(
    examples: list[MLExampleItem],
    request_label: str = "Request",
    action_schema: type[LLMAction] | None = None,  # Schema for validation
) -> str:
    """Formats a list of Memory, Request, and Output examples into a string.

    Args:
        examples: A list of tuples, where each tuple contains:
                  (memory_context: str, request_text: str, output_action: dict).
                  The output_action is a dict representing the JSON action.
        request_label: The label to use for the request/predicate part.
        action_schema: Optional Pydantic model to validate the output_action against.

    Returns:
        str: A string containing all formatted examples.
    """
    import json
    import logging

    logger = logging.getLogger(__name__)

    formatted_str = ""
    for i, (memory, request, output_action_item) in enumerate(examples):
        if action_schema:
            try:
                action_schema.model_validate(output_action_item)
            except Exception as e:  # Catch Pydantic ValidationError and others
                logger.warning(
                    f"Example {i + 1} (Request: '{request}') has an "
                    "invalid 'output_action' against schema "
                    f"{action_schema.__name__}: {e}"
                    f"Action details: {output_action_item}"
                )

        formatted_str += f"Memory: {memory}\n"
        formatted_str += f"{request_label}: {request}\n"
        formatted_str += (
            f"Output:\n{json.dumps({'action': output_action_item}, indent=2)}\n\n"
        )
    return formatted_str.strip()


def format_examples(examples: list[tuple[str, str]]) -> str:
    """Format a list of input/output examples into a consistent string format.

    Args:
        examples: List of tuples where each tuple contains (input_text, output_text)

    Returns:
        str: Formatted examples string
    """
    formatted_examples = "Example inputs and outputs:\\n\\n"
    for input_text, output_text in examples:
        formatted_examples += f'Input: "{input_text}"\\n'
        formatted_examples += f"Output:\\n{output_text}\\n\\n"
    return formatted_examples.rstrip()


def create_planning_prompt(
    command: str,
    description: str,
    examples: Examples,
    schema_definition: str | None = None,
) -> PromptFragments:
    """Create standard planning prompt fragments for kubectl commands.

    This prompt assumes the kubectl command verb (get, describe, delete, etc.)
    is already determined by the context. The LLM's task is to interpret the
    natural language request to identify the target resource(s) and arguments,
    and format the response as JSON according to the provided schema.

    Args:
        command: The kubectl command verb (get, describe, etc.) used for context.
        description: Description of the overall goal (e.g., "getting resources").
        examples: List of tuples where each tuple contains:
                  (natural_language_target_description, expected_json_output_dict)
        schema_definition: JSON schema definition string.
                           Must be provided for structured JSON output.

    Returns:
        PromptFragments: System fragments and base user fragments.
                         Caller adds memory and request fragments.
    """
    import json

    if not schema_definition:
        raise ValueError(
            "schema_definition must be provided for create_planning_prompt"
        )

    system_fragments: SystemFragments = SystemFragments([])
    user_fragments: UserFragments = UserFragments(
        []
    )  # Base user fragments, caller adds dynamic ones

    # System: Core task description
    system_fragments.append(
        Fragment(f"""You are planning arguments for the 'kubectl {command}' command,
which is used for {description}.

Given a natural language request describing the target resource(s), determine the
appropriate arguments *following* 'kubectl {command}'.

The kubectl command '{command}' is implied by the context of this planning task.

Focus on extracting resource names, types, namespaces, selectors, and flags
from the request to populate the 'commands' field of the 'COMMAND' action.""")
    )

    system_fragments.append(
        Fragment(f"""
Your response MUST be a valid JSON object conforming to this schema:
```json
{schema_definition}
```

This means your output should have syntax that aligns with this:
{{
  "action": {{
    "action_type": "COMMAND",
    "commands": ["<arg1>", "<arg2>", ...],
    "yaml_manifest": "<yaml_string_if_applicable>",
    "allowed_exit_codes": [0]
    "explanation": "Optional string."
  }}
}}

Key fields within the nested "COMMAND" action object:
- `action_type`: MUST be "COMMAND".
- `commands`: List of string arguments *following* `kubectl {command}`. Include flags
  like `-n`, `-f -`, but *exclude* the command verb itself. **MUST be a JSON array
  of strings, e.g., ["pods", "-n", "kube-system"], NOT a single string like
  "pods -n kube-system" or '["pods", "-n", "kube-system"]' **.
- `yaml_manifest`: YAML content as a string (for actions like `create` that use stdin).
- `allowed_exit_codes`: Optional. List of integers representing allowed exit codes
  for the command (e.g., [0, 1] for diff). Defaults to [0] if not provided.
- `explanation`: Optional. A brief string explaining why this command was chosen.""")
    )

    # System: Formatted examples
    formatted_examples = (
        "Example inputs (natural language target descriptions) and "
        "expected JSON outputs (LLMPlannerResponse wrapping a CommandAction):\n"
    )
    formatted_examples += "\n".join(
        [
            f'- Target: "{req}" -> \n'
            f"Expected JSON output:\\n{json.dumps({'action': output}, indent=2)}"
            for req, output in examples
        ]
    )
    system_fragments.append(Fragment(formatted_examples))

    # Caller will add actual memory and request strings as separate user fragments.
    user_fragments.append(Fragment("Here's the request:"))

    return PromptFragments((system_fragments, user_fragments))


def create_summary_prompt(
    description: str,
    focus_points: list[str],
    example_format: list[str],
    config: Config | None = None,  # Add config for formatting fragments
    current_memory: str | None = None,  # New argument
) -> PromptFragments:
    """Create standard summary prompt fragments for kubectl command output.

    Args:
        description: Description of what to summarize
        focus_points: List of what to focus on in the summary
        example_format: List of lines showing the expected output format
        config: Optional Config instance to use.
        current_memory: Optional current memory string.

    Returns:
        PromptFragments: System fragments and base user fragments (excluding memory).
                         Caller adds memory fragment first if needed.
    """
    system_fragments: SystemFragments = SystemFragments([])
    user_fragments: UserFragments = UserFragments([])  # Base user fragments

    # Add memory context if provided and not empty
    if current_memory and current_memory.strip():
        system_fragments.append(fragment_memory_context(current_memory))

    # System: Core task description and focus points
    task_description = f"""Summarize kubectl output. {description}

Focus on:
{chr(10).join(f"- {point}" for point in focus_points)}"""
    system_fragments.append(Fragment(task_description))

    # Add formatting fragments from config
    formatting_fragments = get_formatting_fragments(config)
    # Destructure the PromptFragments tuple properly
    format_sys_fragments, format_user_fragments = formatting_fragments
    system_fragments.extend(format_sys_fragments)
    user_fragments.extend(format_user_fragments)

    # System: Example format section
    if example_format:
        examples_text = "Expected output format:\n" + "\n".join(example_format)
        system_fragments.append(Fragment(examples_text))

    # User: The actual output to summarize (with placeholder)
    user_fragments.append(Fragment("Here's the output:\n\n{output}"))

    return PromptFragments((system_fragments, user_fragments))


def get_formatting_fragments(
    config: Config | None = None,
) -> PromptFragments:
    """Get formatting instructions as fragments (system, user).

    Args:
        config: Optional Config instance to use. If not provided, creates a new one.

    Returns:
        PromptFragments: System fragments and user fragments (excluding memory).
                         Caller is responsible for adding memory context fragment.
    """
    system_fragments: SystemFragments = SystemFragments([])
    user_fragments: UserFragments = UserFragments([])

    cfg = config or Config()

    # System: Static Rich markup instructions
    system_fragments.append(
        Fragment("""Format your response using rich.Console() markup syntax
with matched closing tags:
- [bold]resource names and key fields[/bold] for emphasis
- [green]healthy states[/green] for positive states
- [yellow]warnings or potential issues[/yellow] for concerning states
- [red]errors or critical issues[/red] for problems
- [blue]namespaces and other Kubernetes concepts[/blue] for k8s terms
- [italic]timestamps and metadata[/italic] for timing information""")
    )

    # System: Custom instructions (less frequent change than memory)
    custom_instructions = cfg.get("system.custom_instructions")
    if custom_instructions:
        system_fragments.append(
            Fragment(f"Custom instructions:\n{custom_instructions}")
        )

    system_fragments.append(fragment_current_time())

    # User: Important notes including dynamic time (most frequent change)
    user_fragments.append(
        Fragment("""Important:
- Timestamps in the future relative to this are not anomalies
- Do NOT use markdown formatting (e.g., #, ##, *, -)
- Use plain text with rich.Console() markup only
- Skip any introductory phrases like "This output shows" or "I can see"
- Be direct and concise""")
    )

    return PromptFragments((system_fragments, user_fragments))


def fragment_concision(max_chars: int) -> Fragment:
    """Create a fragment instructing the LLM to be concise."""
    return Fragment(f"Be concise. Limit your response to {max_chars} characters.")


def fragment_current_time() -> Fragment:
    """Create a fragment with the current timestamp."""
    return Fragment(f"Current time is {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.")


def fragment_json_schema_instruction(
    schema_json: str, schema_name: str = "the provided"
) -> Fragment:
    """Creates a system fragment instructing the LLM to adhere to a JSON schema."""
    return Fragment(f"""
Your response MUST be a valid JSON object conforming to {schema_name} schema:
```json
{schema_json}
```
""")


def fragment_memory_context(current_memory: str) -> Fragment:
    """Create a fragment with memory context."""
    return Fragment(f"Previous Memory:\n{current_memory}")


# Memory assistant fragment used in memory operations
FRAGMENT_MEMORY_ASSISTANT: Fragment = Fragment("""
You are an AI agent maintaining memory state for a Kubernetes CLI tool.
The memory contains essential context to help you better assist with future requests.

Based on new information, update the memory to maintain the most relevant context.

IMPORTANT: Do NOT include any prefixes like \"Updated memory:\" or headings in
your response. Just provide the direct memory content itself with no additional
labels or headers.
""")


def with_planning_prompt_override(
    prompt_key: str,
) -> Callable[[Callable[..., PromptFragments]], Callable[..., PromptFragments]]:
    """Decorator for planning prompts (simple signature with config and current_memory).

    Use for prompts like apply_plan_prompt, patch_plan_prompt that follow the pattern:
    func(config: Config | None = None, current_memory: str | None = None) ->
      PromptFragments

    Args:
        prompt_key: The key to look for in plugin prompt mappings (e.g., "apply_plan")
    """

    def decorator(
        func: Callable[..., PromptFragments],
    ) -> Callable[..., PromptFragments]:
        def wrapper(*args: Any, **kwargs: Any) -> PromptFragments:
            # Extract config from args/kwargs
            config = None
            if "config" in kwargs:
                config = kwargs["config"]
            elif len(args) > 0 and hasattr(args[0], "get"):  # Duck typing for Config
                config = args[0]

            cfg = config or Config()

            # Try to get custom planning prompt from plugins
            try:
                from vibectl.plugins import PluginStore, PromptResolver

                plugin_store = PluginStore(cfg)
                resolver = PromptResolver(plugin_store, cfg)

                custom_mapping = resolver.get_prompt_mapping(prompt_key)
                if custom_mapping and custom_mapping.is_planning_prompt():
                    from vibectl.prompts.schemas import _SCHEMA_DEFINITION_JSON
                    from vibectl.types import Examples

                    examples = Examples(custom_mapping.get("examples") or [])

                    # Use explicit command from plugin mapping
                    command = custom_mapping.get("command") or "unknown"

                    return create_planning_prompt(
                        command=command,
                        description=custom_mapping.get("description"),
                        examples=examples,
                        schema_definition=_SCHEMA_DEFINITION_JSON,
                    )
            except Exception as e:
                from vibectl.logutil import logger

                logger.warning(
                    f"Failed to load plugin planning prompt for {prompt_key}: {e}"
                )

            # Fall back to original function
            return func(*args, **kwargs)

        return wrapper

    return decorator


def with_summary_prompt_override(
    prompt_key: str,
) -> Callable[[Callable[..., PromptFragments]], Callable[..., PromptFragments]]:
    """Decorator for summary prompts (simple signature with config and current_memory).

    Use for prompts like apply_output_prompt, patch_resource_prompt that follow
    the pattern:
    func(config: Config | None = None, current_memory: str | None = None) ->
      PromptFragments

    Args:
        prompt_key: The key to look for in plugin prompt mappings (e.g.,
                    "apply_resource_summary")
    """

    def decorator(
        func: Callable[..., PromptFragments],
    ) -> Callable[..., PromptFragments]:
        def wrapper(*args: Any, **kwargs: Any) -> PromptFragments:
            # Extract config and current_memory from args/kwargs
            config = None
            current_memory = None

            if "config" in kwargs:
                config = kwargs["config"]
            if "current_memory" in kwargs:
                current_memory = kwargs["current_memory"]
            elif len(args) > 0 and hasattr(args[0], "get"):  # Duck typing for Config
                config = args[0]

            cfg = config or Config()

            # Try to get custom summary prompt from plugins
            try:
                from vibectl.plugins import PluginStore, PromptResolver

                plugin_store = PluginStore(cfg)
                resolver = PromptResolver(plugin_store, cfg)

                custom_mapping = resolver.get_prompt_mapping(prompt_key)
                if custom_mapping and custom_mapping.is_summary_prompt():
                    return create_summary_prompt(
                        description=custom_mapping.get("description"),
                        focus_points=custom_mapping.get("focus_points") or [],
                        example_format=custom_mapping.get("example_format") or [],
                        config=cfg,
                        current_memory=current_memory,
                    )
            except Exception as e:
                from vibectl.logutil import logger

                logger.warning(
                    f"Failed to load plugin summary prompt for {prompt_key}: {e}"
                )

            # Fall back to original function
            return func(*args, **kwargs)

        return wrapper

    return decorator


def with_custom_prompt_override(prompt_key: str) -> Callable:
    """
    Decorator for complex prompt functions that need custom plugin handling.

    Unlike the simple planning/summary decorators, this decorator:
    1. Looks up the plugin mapping for the given prompt_key
    2. Passes the custom_mapping (or None) as the first argument to the
       decorated function
    3. Lets the function handle both custom and default logic internally

    This is useful for prompt functions that need to do custom processing with
    plugin data (like building custom schemas, examples, etc.) rather than
    simple text replacement.

    Args:
        prompt_key: The prompt key to look up in plugins (e.g., "apply_filescope")

    Returns:
        Decorator function that injects custom_mapping as first argument
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Import here to avoid circular imports
            from vibectl.plugins import PluginStore, PromptResolver

            # Get custom mapping from plugins
            plugin_store = PluginStore()
            resolver = PromptResolver(plugin_store)
            custom_mapping = resolver.get_prompt_mapping(prompt_key)

            # Call the original function with custom_mapping as first argument
            # Functions can use getattr(custom_mapping, "field", default) or
            # check if None
            return func(custom_mapping, *args, **kwargs)

        return wrapper

    return decorator
