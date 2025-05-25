"""
Execution module for intelligent edit functionality.

This module provides the core intelligent editing workflow:
1. Fetches the target resource using kubectl get
2. Summarizes resource into natural language
3. Invokes editor with natural language summary
4. Detects changes between original and edited summaries
5. Uses LLM to analyze edits and generate appropriate patch
6. Updates memory with patch generation context
7. Applies the generated patch to the resource
8. Summarizes the result to user
"""

import difflib

import click
import yaml

from vibectl.command_handler import handle_command_output
from vibectl.config import Config
from vibectl.k8s_utils import run_kubectl
from vibectl.logutil import logger
from vibectl.memory import get_memory, update_memory
from vibectl.model_adapter import get_model_adapter
from vibectl.prompts.edit import (
    get_patch_generation_prompt,
    get_resource_summarization_prompt,
    patch_summary_prompt,
    plan_edit_scope,
)
from vibectl.schema import EditResourceScopeResponse, LLMPlannerResponse
from vibectl.types import (
    ActionType,
    Error,
    OutputFlags,
    Result,
    Success,
    UserFragments,
)
from vibectl.utils import console_manager


def _generate_summary_diff(original_summary: str, edited_summary: str) -> str:
    """Generate a unified diff between original and edited summaries.

    Args:
        original_summary: The original natural language summary
        edited_summary: The user-edited summary

    Returns:
        A unified diff string, or empty string if no changes
    """
    original_lines = original_summary.splitlines(keepends=True)
    edited_lines = edited_summary.splitlines(keepends=True)

    diff_lines = list(
        difflib.unified_diff(
            original_lines,
            edited_lines,
            fromfile="original",
            tofile="edited",
            lineterm="",
        )
    )

    return "".join(diff_lines)


async def run_intelligent_edit_workflow(
    resource: str,
    args: tuple[str, ...],
    output_flags: OutputFlags,
    config: Config,
    edit_context: str | None = None,
) -> Result:
    """Execute the intelligent edit workflow for a Kubernetes resource.

    Args:
        resource: The resource type/name to edit (e.g., "deployment/nginx")
        args: Additional arguments for kubectl
        output_flags: Output configuration flags
        config: Configuration instance
        edit_context: Optional context about what aspects to focus on during editing

    Returns:
        Result object with the outcome of the operation
    """
    logger.info(f"Starting intelligent edit workflow for {resource}")
    if edit_context:
        logger.info(f"Edit context: {edit_context}")

    # Step 1: Fetch the current resource
    logger.info("Fetching current resource configuration")
    fetch_result = await _fetch_resource(resource, args, config)
    if isinstance(fetch_result, Error):
        return fetch_result

    resource_yaml = fetch_result.data
    if not resource_yaml:
        return Error("Failed to fetch resource: empty response")

    # Step 2: Summarize resource to natural language
    logger.info("Summarizing resource to natural language")
    summary_result = await _summarize_resource(
        resource_yaml, output_flags, config, edit_context
    )
    if isinstance(summary_result, Error):
        return summary_result

    original_summary = summary_result.data
    if not original_summary:
        return Error("Failed to generate resource summary")

    # Step 3: Open editor with the summary
    logger.info("Opening editor for user to make changes")
    edit_result = _invoke_editor(original_summary)
    if isinstance(edit_result, Error):
        return edit_result

    edited_summary = edit_result.data
    if not edited_summary:
        return Error("Failed to get edited content")

    # Step 4: Generate diff to check for changes and prepare for patch generation
    logger.info("Generating diff between original and edited summaries")
    summary_diff = _generate_summary_diff(original_summary, edited_summary)

    if not summary_diff:
        console_manager.print_note("No changes made to the resource")
        return Success(message="No changes made")

    # Step 5: Generate patch from the diff
    logger.info("Generating patch from summary changes")
    patch_result = await _generate_patch_from_changes(
        resource=resource,
        args=args,
        original_summary=original_summary,
        summary_diff=summary_diff,
        original_yaml=resource_yaml,
        output_flags=output_flags,
        config=config,
    )
    if isinstance(patch_result, Error):
        return patch_result

    patch_commands = patch_result.data
    if not patch_commands:
        return Error("Failed to generate patch commands")

    # Step 6: Update memory with patch generation context
    logger.info("Updating memory with patch generation context")
    patch_context = (
        f"Generated patch commands for {resource}: {' '.join(patch_commands)}\n\n"
        f"Summary changes:\n{summary_diff}"
    )
    patch_memory_metrics = await update_memory(
        command_message=f"Generated patch for {resource} {' '.join(args)}",
        command_output=patch_context,
        vibe_output="",
        model_name=output_flags.model_name,
    )

    # Display metrics for the patch memory update call
    if patch_memory_metrics and output_flags.show_metrics:
        console_manager.print_metrics(
            latency_ms=patch_memory_metrics.latency_ms,
            tokens_in=patch_memory_metrics.token_input,
            tokens_out=patch_memory_metrics.token_output,
            source="LLM Memory Update (Patch Context)",
            total_duration=patch_memory_metrics.total_processing_duration_ms,
        )

    # Step 7: Apply the patch
    logger.info("Applying generated patch")
    apply_result = await _apply_patch(patch_commands, output_flags, config)
    if isinstance(apply_result, Error):
        return apply_result

    # Step 8: Update memory with the operation
    memory_metrics = await update_memory(
        command_message=f"Intelligent edit: {resource} {' '.join(args)}",
        command_output=apply_result.data or "Successfully applied intelligent edit",
        vibe_output="",
        model_name=output_flags.model_name,
    )

    # Display metrics for the memory update call
    if memory_metrics and output_flags.show_metrics:
        console_manager.print_metrics(
            latency_ms=memory_metrics.latency_ms,
            tokens_in=memory_metrics.token_input,
            tokens_out=memory_metrics.token_output,
            source="LLM Memory Update (Operation Result)",
            total_duration=memory_metrics.total_processing_duration_ms,
        )

    console_manager.print_success(f"Successfully edited {resource}")
    return Success(
        message=f"Intelligent edit completed for {resource}",
    )


async def _fetch_resource(
    resource: str, args: tuple[str, ...], config: Config
) -> Result:
    """Fetch the current resource configuration as YAML."""
    try:
        # Build kubectl get command
        kubectl_args = ["get", resource, *args, "-o", "yaml"]

        result = run_kubectl(kubectl_args, config=config)
        if isinstance(result, Error):
            return Error(
                error=f"Failed to fetch resource {resource}: {result.error}",
                original_exit_code=result.original_exit_code,
            )

        return Success(data=result.data)
    except Exception as e:
        logger.error(f"Error fetching resource {resource}: {e}")
        return Error(error=f"Failed to fetch resource: {e}")


async def _summarize_resource(
    resource_yaml: str,
    output_flags: OutputFlags,
    config: Config,
    edit_context: str | None = None,
) -> Result:
    """Convert resource YAML to natural language summary."""
    try:
        # Parse YAML to get basic info
        resource_data = yaml.safe_load(resource_yaml)
        resource_kind = resource_data.get("kind", "Unknown")
        resource_name = resource_data.get("metadata", {}).get("name", "unknown")

        prompt_fragments = get_resource_summarization_prompt(
            resource_yaml=resource_yaml,
            resource_kind=resource_kind,
            resource_name=resource_name,
            edit_context=edit_context,
        )
        system_fragments, user_fragments = prompt_fragments

        # Get model adapter and process
        model_adapter = get_model_adapter(config)
        model_name = output_flags.model_name
        model = model_adapter.get_model(model_name)

        # Get response text and metrics - no response_model since we expect plain text
        llm_response_text, metrics = await model_adapter.execute_and_log_metrics(
            model=model,
            system_fragments=system_fragments,
            user_fragments=user_fragments,
            response_model=None,  # Plain text response, not JSON
        )

        # Display metrics for the summarization call
        if metrics and output_flags.show_metrics:
            console_manager.print_metrics(
                latency_ms=metrics.latency_ms,
                tokens_in=metrics.token_input,
                tokens_out=metrics.token_output,
                source="LLM Resource Summarization",
                total_duration=metrics.total_processing_duration_ms,
            )

        if not llm_response_text or llm_response_text.strip() == "":
            return Error("LLM returned empty response for resource summarization")

        # Return the plain text summary directly
        return Success(data=llm_response_text.strip(), metrics=metrics)

    except Exception as e:
        logger.error(f"Error summarizing resource: {e}")
        return Error(error=f"Failed to summarize resource: {e}")


def _invoke_editor(summary: str) -> Result:
    """Open editor with the summary for user editing."""
    try:
        # Add instructions at the top
        editor_content = f"""# Edit the configuration below using natural language.
# Save and close the editor to apply changes, or delete all content to cancel.

{summary}
"""

        edited_text = click.edit(editor_content)

        if edited_text is None:
            return Error("Editor was cancelled")

        # Remove the instruction header
        lines = edited_text.split("\n")
        content_started = False
        cleaned_lines = []

        for line in lines:
            if content_started:
                cleaned_lines.append(line)
            elif line.strip() and not line.strip().startswith("#"):
                content_started = True
                cleaned_lines.append(line)

        cleaned_summary = "\n".join(cleaned_lines).strip()

        if not cleaned_summary:
            return Error("Edit was cancelled (no content)")

        return Success(data=cleaned_summary)

    except Exception as e:
        logger.error(f"Error invoking editor: {e}")
        return Error(error=f"Failed to open editor: {e}")


async def _generate_patch_from_changes(
    resource: str,
    args: tuple[str, ...],
    original_summary: str,
    summary_diff: str,
    original_yaml: str,
    output_flags: OutputFlags,
    config: Config,
) -> Result:
    """Generate kubectl patch commands from summary diff.

    TODO: Investigate if we can remove original_summary parameter and rely only
    on summary_diff for better token efficiency. For now, keeping both for
    incremental testing.
    """
    try:
        prompt_fragments = get_patch_generation_prompt(
            resource=resource,
            args=args,
            original_summary=original_summary,
            summary_diff=summary_diff,
            original_yaml=original_yaml,
        )
        system_fragments, user_fragments = prompt_fragments

        # Get model adapter and process using existing patterns
        model_adapter = get_model_adapter(config)
        model_name = output_flags.model_name
        model = model_adapter.get_model(model_name)

        # Get response text and metrics using fragments
        llm_response_text, metrics = await model_adapter.execute_and_log_metrics(
            model=model,
            system_fragments=system_fragments,
            user_fragments=user_fragments,
            response_model=LLMPlannerResponse,
        )

        # Display metrics for the patch generation call
        if metrics and output_flags.show_metrics:
            console_manager.print_metrics(
                latency_ms=metrics.latency_ms,
                tokens_in=metrics.token_input,
                tokens_out=metrics.token_output,
                source="LLM Patch Generation",
                total_duration=metrics.total_processing_duration_ms,
            )

        if not llm_response_text or llm_response_text.strip() == "":
            return Error("LLM returned empty response for patch generation")

        # Parse the response
        response = LLMPlannerResponse.model_validate_json(llm_response_text)

        if not hasattr(response, "action") or response.action is None:
            return Error("LLM response missing action for patch generation")

        action = response.action
        if action.action_type != ActionType.COMMAND:
            # Handle non-COMMAND actions by showing them to the user
            if action.action_type == ActionType.ERROR:
                error_message = getattr(action, "message", "LLM provided error")
                logger.info(f"LLM returned patch generation error: {error_message}")
                console_manager.print_error(
                    f"LLM Patch Generation Error: {error_message}"
                )
                return Error(
                    error=f"LLM patch generation error: {error_message}",
                    metrics=metrics,
                )
            else:
                # Handle all other non-COMMAND action types
                logger.warning(
                    f"LLM returned unexpected action type: {action.action_type}"
                )
                return Error(
                    error=f"LLM returned unexpected action type '{action.action_type}' "
                    "instead of COMMAND for patch generation",
                    metrics=metrics,
                )

        # Extract the patch command
        commands = action.commands
        if not commands:
            return Error("No patch commands generated")

        return Success(data=commands, metrics=metrics)

    except Exception as e:
        logger.error(f"Error generating patch: {e}")
        return Error(error=f"Failed to generate patch: {e}")


async def _apply_patch(
    patch_commands: list[str], output_flags: OutputFlags, config: Config
) -> Result:
    """Apply the generated patch commands."""
    try:
        # Execute the patch
        kubectl_args = ["patch", *patch_commands, "--output=json"]
        kubectl_args_str = " ".join(kubectl_args)

        logger.info(f"Executing kubectl patch: {kubectl_args_str}")

        # Show the command if requested
        if output_flags.show_kubectl:
            console_manager.print_note(f"Running: {kubectl_args_str}")

        result = run_kubectl(kubectl_args, config=config)

        if isinstance(result, Error):
            return Error(
                error=f"Failed to apply patch: {result.error}",
                original_exit_code=result.original_exit_code,
            )

        # Process the output for display and capture the vibe output
        if output_flags.show_raw:
            console_manager.print(result.data or "")

        vibe_output = None
        if output_flags.show_vibe:
            # Use the existing output processing logic
            output_result = await handle_command_output(
                output=result,
                output_flags=output_flags,
                summary_prompt_func=patch_summary_prompt,
                command=kubectl_args_str,
            )
            # Capture the vibe output for memory updates
            if isinstance(output_result, Success):
                vibe_output = output_result.message
            elif isinstance(output_result, Error):
                # If vibe processing failed, use the raw output
                vibe_output = result.data

        # Return the captured vibe output in the data field for memory updates
        return Success(
            message="Patch applied successfully",
            data=vibe_output or result.data or "Patch applied successfully",
        )

    except Exception as e:
        logger.error(f"Error applying patch: {e}")
        return Error(error=f"Failed to apply patch: {e}")


async def run_intelligent_vibe_edit_workflow(
    request: str,
    output_flags: OutputFlags,
    config: Config,
) -> Result:
    """Execute the intelligent edit workflow for a vibe request.

    This function:
    1. Uses LLM to understand the vibe request and identify target resource(s)
    2. Calls the intelligent edit workflow on each identified resource

    Args:
        request: The user's natural language request (e.g., "nginx deployment replicas")
        output_flags: Output configuration flags
        config: Configuration instance

    Returns:
        Result object with the outcome of the operation
    """
    logger.info(f"Starting intelligent vibe edit workflow for: {request}")

    # Step 1: Resource Scoping & Intent Extraction (LLM)
    logger.info("Step 1: Analyzing request for resource scoping")
    model_adapter = get_model_adapter(config=config)
    model_name = output_flags.model_name
    model = model_adapter.get_model(model_name)

    # Get memory context
    memory_context = get_memory(config)

    # Get resource scoping fragments
    system_fragments, user_fragments_base = plan_edit_scope(
        request, config=config, current_memory=memory_context
    )

    # Use the fragments as-is (memory is now handled in the prompt function)
    user_fragments = list(user_fragments_base)

    # Get LLM response for resource scoping
    try:
        response_text, metrics = await model_adapter.execute_and_log_metrics(
            model=model,
            system_fragments=system_fragments,
            user_fragments=UserFragments(user_fragments),
            response_model=EditResourceScopeResponse,
        )

        # Display metrics for the resource scoping call
        if metrics and output_flags.show_metrics:
            console_manager.print_metrics(
                latency_ms=metrics.latency_ms,
                tokens_in=metrics.token_input,
                tokens_out=metrics.token_output,
                source="LLM Resource Scoping",
                total_duration=metrics.total_processing_duration_ms,
            )

        if not response_text or response_text.strip() == "":
            return Error(
                error="LLM returned an empty response for resource scoping.",
                metrics=metrics,
            )

        logger.debug(f"Raw LLM response for resource scope: {response_text}")
        resource_scope_response = EditResourceScopeResponse.model_validate_json(
            response_text
        )

        llm_scoped_resources = resource_scope_response.resource_selectors
        llm_kubectl_args = resource_scope_response.kubectl_arguments
        llm_edit_context = resource_scope_response.edit_context

        logger.info(f"LLM Resource Selectors: {llm_scoped_resources}")
        logger.info(f"LLM Kubectl Arguments: {llm_kubectl_args}")
        logger.info(f"LLM Edit Context: {llm_edit_context}")

    except Exception as e:
        logger.error(f"Error during resource scoping: {e}")
        return Error(
            error=f"Failed to scope resources from request: {e}",
            metrics=getattr(e, "metrics", None),
        )

    # Step 2: Execute intelligent edit for each scoped resource
    if not llm_scoped_resources:
        return Error(
            error="No resources were identified in the request. "
            "Please specify a resource to edit "
            "(e.g., 'deployment nginx', 'service frontend')."
        )

    # For now, handle the first resource (could be extended to handle multiple)
    resource_selector = llm_scoped_resources[0]
    logger.info(f"Processing resource: {resource_selector}")

    kubectl_args = tuple(llm_kubectl_args)

    logger.info(
        f"Calling intelligent edit workflow for resource: {resource_selector}, "
        f"args: {kubectl_args}"
    )
    logger.info(f"Edit context: {llm_edit_context}")

    # Step 3: Use the existing intelligent edit workflow
    return await run_intelligent_edit_workflow(
        resource=resource_selector,
        args=kubectl_args,
        output_flags=output_flags,
        config=config,
        edit_context=llm_edit_context,
    )
