"""
Execution module for intelligent apply functionality.

This module provides the core intelligent apply workflow:
1. Initial scoping and intent extraction using LLM
2. File discovery and validation
3. Manifest summarization and operation memory building
4. Correction/generation loop for invalid sources
5. Final command planning and execution
"""

import asyncio
import glob
import tempfile
import uuid
from json import JSONDecodeError
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from vibectl.command_handler import handle_command_output
from vibectl.config import Config
from vibectl.k8s_utils import run_kubectl, run_kubectl_with_yaml
from vibectl.logutil import logger
from vibectl.model_adapter import ModelAdapter, get_model_adapter
from vibectl.prompts.apply import (
    _LLM_FINAL_APPLY_PLAN_RESPONSE_SCHEMA_JSON,
    apply_output_prompt,
    correct_apply_manifest_prompt_fragments,
    plan_apply_filescope_prompt_fragments,
    plan_final_apply_command_prompt_fragments,
    summarize_apply_manifest_prompt_fragments,
)
from vibectl.schema import (
    ApplyFileScopeResponse,
    CommandAction,
    LLMFinalApplyPlanResponse,
)
from vibectl.types import Error, OutputFlags, Result, Success


async def validate_manifest_content(
    content: str, file_path: Path, cfg: Config
) -> Result:
    """Validate manifest content. Returns Success if valid, Error otherwise."""
    try:
        if not content.strip() or content.strip().startswith("#"):
            logger.debug(
                f"File {file_path} is empty, whitespace-only, or comment-only."
            )
            return Error(
                error=(
                    f"empty_file: File {file_path} is empty, whitespace-only, "
                    "or comment-only."
                )
            )

        list(yaml.safe_load_all(content))
    except yaml.YAMLError as e:
        logger.warning(f"YAML syntax error in {file_path}: {e}")
        return Error(
            error=f"yaml_syntax_error: YAML syntax error in {file_path}: {e}",
            exception=e,
        )
    except Exception as e:
        logger.warning(f"Error loading YAML from {file_path}: {e}")
        return Error(
            error=f"load_error: Error loading YAML from {file_path}: {e}",
            exception=e,
        )

    kubectl_args = ["apply", "-f", "-", "--dry-run=server"]
    kubectl_result = await asyncio.to_thread(
        run_kubectl_with_yaml,
        args=kubectl_args,
        yaml_content=content,
        config=cfg,
    )

    if isinstance(kubectl_result, Success):
        logger.debug(f"Server-side dry-run successful for {file_path}")
        return Success(
            message=(
                f"valid: Manifest {file_path} is valid "
                "(server-side dry-run successful)."
            ),
            data={"file_path": str(file_path), "content": content},
        )
    else:
        if (
            isinstance(kubectl_result, Error)
            and isinstance(kubectl_result.exception, FileNotFoundError)
            and "kubectl not found" in kubectl_result.error
        ):
            return kubectl_result

        error_msg = kubectl_result.error or "Unknown dry-run error"
        logger.warning(f"Server-side dry-run failed for {file_path}: {error_msg}")
        error = Error(
            f"dry_run_error: Server-side dry-run failed for {file_path}: {error_msg}"
        )
        if kubectl_result.exception:
            error.exception = kubectl_result.exception
        return error


async def discover_and_validate_files(
    file_selectors: list[str],
    cfg: Config,
) -> tuple[list[tuple[Path, str]], list[tuple[Path, str | None, str]]]:
    """Discovers files from selectors and validates them, returning pair of lists."""
    semantically_valid_manifests: list[tuple[Path, str]] = []  # path, content
    invalid_sources_to_correct: list[
        tuple[Path, str | None, str]
    ] = []  # path, content, error_reason
    processed_paths: set[Path] = set()

    for selector in file_selectors:
        # Expand globs first, then check if it's a file or directory
        # Use absolute paths to help with duplicate detection from different selectors
        try:
            path_selector = Path(selector).resolve()
        except OSError as e:  # Catch errors like file name too long
            logger.warning(f"Invalid path or selector '{selector}': {e}")
            # Treat as an unresolvable source directly without content
            invalid_sources_to_correct.append(
                (Path(selector), None, f"Invalid path: {e}")
            )
            continue

        selected_item_paths: list[Path] = []
        if "*" in selector or "?" in selector or "[" in selector:  # Basic glob check
            # Use glob.glob for potentially complex patterns, ensuring recursive
            # search if selector suggests it. For simplicity, let's assume
            # recursive for now if it's not clearly a file. Or, respect if
            # the glob pattern itself is recursive (e.g., ends with /**/*)
            is_recursive_glob = selector.endswith("**") or "**/*" in selector
            try:
                glob_results = glob.glob(
                    str(path_selector), recursive=is_recursive_glob
                )  # Use resolved path for glob
                for p_str in glob_results:
                    p = Path(p_str).resolve()
                    if p.is_file():
                        selected_item_paths.append(p)
                    elif (
                        p.is_dir()
                    ):  # If glob matches a directory, add its files recursively
                        for sub_p_str in glob.glob(str(p / "**" / "*"), recursive=True):
                            sub_p = Path(sub_p_str).resolve()
                            if sub_p.is_file():
                                selected_item_paths.append(sub_p)
            except Exception as e:
                logger.warning(f"Error expanding glob pattern '{selector}': {e}")
                invalid_sources_to_correct.append(
                    (Path(selector), None, f"Glob expansion error: {e}")
                )
                continue
        elif path_selector.is_file():
            selected_item_paths.append(path_selector)
        elif path_selector.is_dir():
            # Recursively find all files in the directory
            for item in path_selector.rglob("*"):
                if item.is_file():
                    selected_item_paths.append(item.resolve())
        else:
            logger.warning(
                f"Selector '{selector}' (resolved to '{path_selector}') is not "
                "a file, directory, or valid glob. Skipping."
            )
            invalid_sources_to_correct.append(
                (path_selector, None, "Not a file or directory")
            )
            continue

        unique_new_paths = [p for p in selected_item_paths if p not in processed_paths]
        if not unique_new_paths:
            if selected_item_paths:  # If paths were found but already processed
                logger.debug(
                    f"All paths for selector '{selector}' already processed. "
                    "Skipping duplicate processing."
                )
            continue

        for file_path in unique_new_paths:
            if file_path in processed_paths:
                continue  # Should be caught by unique_new_paths, but as a safeguard
            processed_paths.add(file_path)

            logger.debug(f"Processing file: {file_path}")
            content: str | None = None
            try:
                content = file_path.read_text()
            except Exception as e:
                logger.warning(f"Failed to read file {file_path}: {e}")
                invalid_sources_to_correct.append((file_path, None, f"Read error: {e}"))
                continue

            # Check if the file is "definitely not a Kubernetes manifest"
            is_likely_kubernetes_yaml = (
                "apiVersion" in content
                and "kind" in content
                and (
                    file_path.suffix.lower() in [".yaml", ".yml"]
                    or any(
                        keyword in content
                        for keyword in ["metadata:", "spec:", "namespace:"]
                    )
                )
            )

            if not is_likely_kubernetes_yaml:
                # This file doesn't look like Kubernetes YAML, add it to invalid sources
                invalid_sources_to_correct.append(
                    (
                        file_path,
                        content,
                        "not_kubernetes: File doesn't appear to be a "
                        "Kubernetes manifest",
                    )
                )
                continue

            # Validate the manifest
            validation_result = await validate_manifest_content(content, file_path, cfg)

            if isinstance(validation_result, Success):
                semantically_valid_manifests.append((file_path, content))
                logger.debug(f"Validated manifest: {file_path}")
            else:
                invalid_sources_to_correct.append(
                    (file_path, content, validation_result.error)
                )
                logger.debug(
                    f"Invalid manifest: {file_path} - {validation_result.error}"
                )

    return semantically_valid_manifests, invalid_sources_to_correct


async def summarize_manifests_and_build_memory(
    semantically_valid_manifests: list[tuple[Path, str]],
    model_adapter: ModelAdapter,
    llm_model: Any,
    invalid_sources_to_correct: list[tuple[Path, str | None, str]],
) -> tuple[str, list[tuple[Path, str | None, str]]]:
    """
    Summarize valid manifests and build operation memory.

    Returns:
        Tuple of (operation_memory_string, updated_invalid_sources_list)
    """
    apply_operation_memory = ""
    updated_invalid_sources = list(invalid_sources_to_correct)  # Copy the list

    for file_path, manifest_content in semantically_valid_manifests:
        logger.info(f"Summarizing manifest: {file_path}")

        current_op_mem_for_prompt = (
            apply_operation_memory
            if apply_operation_memory
            else "No prior summaries for this operation yet."
        )
        summary_system_frags, summary_user_frags = (
            summarize_apply_manifest_prompt_fragments(
                current_memory=current_op_mem_for_prompt,
                manifest_content=manifest_content,
            )
        )

        try:
            (
                summary_text,
                summary_metrics,
            ) = await model_adapter.execute_and_log_metrics(
                model=llm_model,
                system_fragments=summary_system_frags,
                user_fragments=summary_user_frags,
                response_model=None,
            )

            if not summary_text or summary_text.strip() == "":
                logger.warning(
                    f"LLM returned empty summary for {file_path}. "
                    "Skipping update to operation memory."
                )
                continue

            logger.debug(f"LLM summary for {file_path}:\n{summary_text}")
            apply_operation_memory += (
                f"Summary for {file_path}:\n{summary_text}\n\n--------------------\n"
            )
            logger.info(f"Updated operation memory after summarizing {file_path}")

        except Exception as e_summary:
            logger.error(
                f"Error summarizing manifest {file_path}: {e_summary}",
                exc_info=True,
            )
            updated_invalid_sources.append(
                (
                    file_path,
                    manifest_content,
                    f"summary_error_during_step3: {e_summary}",
                )
            )

    return apply_operation_memory, updated_invalid_sources


async def correct_and_generate_manifests(
    invalid_sources_to_correct: list[tuple[Path, str | None, str]],
    apply_operation_memory: str,
    llm_remaining_request: str,
    model_adapter: ModelAdapter,
    llm_model: Any,
    cfg: Config,
    temp_dir_path: Path,
    max_correction_retries: int,
) -> tuple[list[Path], list[tuple[Path, str]], str]:
    """
    Correct and generate manifests for invalid sources.

    Returns:
        Tuple of (
            corrected_temp_manifest_paths,
            unresolvable_sources,
            updated_operation_memory,
        )
    """
    corrected_temp_manifest_paths: list[Path] = []
    unresolvable_sources: list[tuple[Path, str]] = []
    updated_operation_memory = apply_operation_memory

    for (
        original_path,
        original_content,
        error_reason_full,
    ) in invalid_sources_to_correct:
        # Skip if critical error like kubectl not found, already handled
        if (
            "CRITICAL:" in error_reason_full
            or "summary_error_during_step3:" in error_reason_full
        ):
            logger.warning(
                f"Skipping correction for {original_path} due to prior "
                f"critical/summary error: {error_reason_full}"
            )
            unresolvable_sources.append((original_path, error_reason_full))
            continue

        logger.info(
            f"Attempting to correct/generate manifest for: {original_path} "
            f"(Reason: {error_reason_full})"
        )
        corrected_successfully = False
        for attempt in range(max_correction_retries + 1):
            logger.debug(
                f"Correction attempt {attempt + 1}/{max_correction_retries + 1} "
                f"for {original_path}"
            )

            current_op_mem_for_prompt = (
                updated_operation_memory
                if updated_operation_memory
                else "No operation memory available yet."
            )
            original_content_for_prompt = (
                original_content
                if original_content is not None
                else "File content was not readable or applicable."
            )

            correction_system_frags, correction_user_frags = (
                correct_apply_manifest_prompt_fragments(
                    original_file_path=str(original_path),
                    original_file_content=original_content_for_prompt,
                    error_reason=error_reason_full,
                    current_operation_memory=current_op_mem_for_prompt,
                    remaining_user_request=llm_remaining_request,
                )
            )

            try:
                (
                    proposed_yaml_str,
                    correction_metrics,
                ) = await model_adapter.execute_and_log_metrics(
                    model=llm_model,
                    system_fragments=correction_system_frags,
                    user_fragments=correction_user_frags,
                    response_model=None,  # Expecting raw YAML string
                )

                if (
                    not proposed_yaml_str
                    or proposed_yaml_str.strip() == ""
                    or proposed_yaml_str.strip().startswith("#")
                ):
                    intent_to_retry = (
                        "Not retrying."
                        if attempt == max_correction_retries
                        else "Retrying..."
                    )
                    logger.warning(
                        f"LLM returned empty or comment-only YAML for "
                        f"{original_path} on attempt {attempt + 1}. "
                        f"{intent_to_retry}"
                    )
                    if attempt == max_correction_retries:
                        unresolvable_sources.append(
                            (
                                original_path,
                                "LLM provided no usable YAML after "
                                f"{max_correction_retries + 1} attempts. "
                                f"Last reason: {error_reason_full}",
                            )
                        )
                    continue  # To next retry or next file

                # Create a unique temp path for this correction attempt
                temp_correction_path = (
                    temp_dir_path
                    / f"corrected_{original_path.name}_{uuid.uuid4().hex[:8]}.yaml"
                )

                # Validate the proposed YAML using original_path for logging
                # to avoid referencing non-existent temp file in error messages
                validation_result = await validate_manifest_content(
                    proposed_yaml_str, original_path, cfg
                )

                if isinstance(validation_result, Success):
                    # Only write the file after successful validation
                    temp_correction_path.write_text(proposed_yaml_str)
                    corrected_temp_manifest_paths.append(temp_correction_path)
                    logger.info(
                        "Successfully corrected/generated and validated manifest "
                        f"for {original_path}, saved to {temp_correction_path}."
                    )

                    # Summarize newly corrected manifest with namespace-neutral prompt
                    current_op_mem_for_summary = (
                        updated_operation_memory
                        if updated_operation_memory
                        else "No prior summaries."
                    )
                    new_summary_system_frags, new_summary_user_frags = (
                        summarize_apply_manifest_prompt_fragments(
                            current_memory=current_op_mem_for_summary,
                            manifest_content=proposed_yaml_str,
                        )
                    )
                    try:
                        (
                            new_summary_text,
                            new_summary_metrics,
                        ) = await model_adapter.execute_and_log_metrics(
                            model=llm_model,
                            system_fragments=new_summary_system_frags,
                            user_fragments=new_summary_user_frags,
                            response_model=None,
                        )
                        if new_summary_text and new_summary_text.strip():
                            updated_operation_memory += (
                                f"Summary for newly corrected {original_path} "
                                f"(as {temp_correction_path.name}):\n"
                                f"{new_summary_text}\n\n"
                                f"--------------------\n"
                            )
                            logger.info(
                                f"Updated operation memory after summarizing "
                                f"corrected manifest {temp_correction_path.name}"
                            )
                    except Exception as e_new_summary:
                        logger.error(
                            "Error summarizing corrected manifest "
                            f"{temp_correction_path.name}: {e_new_summary}",
                            exc_info=True,
                        )

                    corrected_successfully = True
                    break  # Break from retry loop for this source
                else:  # Validation failed
                    validation_error_full_message = validation_result.error
                    logger.warning(
                        f"Proposed YAML for {original_path} failed validation "
                        f"on attempt {attempt + 1}: {validation_error_full_message}"
                    )
                    error_reason_full = validation_error_full_message
                    if attempt == max_correction_retries:
                        unresolvable_sources.append(
                            (
                                original_path,
                                "Failed to validate LLM output for "
                                f"{original_path} after "
                                f"{max_correction_retries + 1} attempts. "
                                f"Last error: {error_reason_full}",
                            )
                        )

            except Exception as e_correction:
                logger.error(
                    f"Error during correction/generation for {original_path} "
                    f"on attempt {attempt + 1}: {e_correction}",
                    exc_info=True,
                )
                error_reason_full = f"correction_exception: {e_correction}"
                if attempt == max_correction_retries:
                    unresolvable_sources.append(
                        (
                            original_path,
                            f"Exception during correction for {original_path} "
                            f"after {max_correction_retries + 1} attempts. "
                            f"Last error: {error_reason_full}",
                        )
                    )

        if not corrected_successfully and not any(
            u_path == original_path for u_path, _ in unresolvable_sources
        ):
            unresolvable_sources.append(
                (
                    original_path,
                    f"Correction attempts failed for {original_path}. "
                    f"Last reason: {error_reason_full}",
                )
            )

    return corrected_temp_manifest_paths, unresolvable_sources, updated_operation_memory


async def execute_planned_commands(
    planned_commands: list[CommandAction],
    cfg: Config,
    output_flags: OutputFlags,
) -> Result:
    """Executes a list of planned kubectl commands, handling output and errors."""
    overall_success = True
    final_results_summary = ""
    final_metrics = None

    for i, planned_cmd_response in enumerate(planned_commands):
        logger.info(f"Executing planned command {i + 1}/{len(planned_commands)}")

        commands_to_log = planned_cmd_response.commands
        if commands_to_log is None:  # Should not happen if action_type is COMMAND
            commands_to_log = ["<no commands specified>"]

        if planned_cmd_response.action_type != "COMMAND":
            logger.warning(
                "Skipping non-COMMAND action type from plan: "
                f"{planned_cmd_response.action_type}"
            )
            final_results_summary += (
                f"Skipped planned action ({planned_cmd_response.action_type}).\n"
            )
            continue

        # Validate the constructed full command list
        if len(planned_cmd_response.commands) == 0:
            logger.error("Planned command list is empty.")
            final_results_summary += "Error: Planned command list is empty.\n"
            overall_success = False
            continue

        full_kubectl_command_list = [
            "apply",
            *planned_cmd_response.commands,
            "--output=json",
        ]

        logger.debug(
            f"Planned command details: {planned_cmd_response.model_dump_json(indent=2)}"
        )

        kubectl_result: Result
        uses_stdin = False
        if (
            "-f" in full_kubectl_command_list
            and full_kubectl_command_list.index("-f") + 1
            < len(full_kubectl_command_list)
            and full_kubectl_command_list[full_kubectl_command_list.index("-f") + 1]
            == "-"
        ):
            uses_stdin = True

        full_kubect_command_str = " ".join(full_kubectl_command_list)

        if planned_cmd_response.yaml_manifest and uses_stdin:
            logger.debug(
                f"Executing command {full_kubect_command_str} "
                "with YAML manifest via stdin."
            )
            kubectl_result = await asyncio.to_thread(
                run_kubectl_with_yaml,
                args=full_kubectl_command_list,
                yaml_content=planned_cmd_response.yaml_manifest,
                config=cfg,
                allowed_exit_codes=tuple(planned_cmd_response.allowed_exit_codes)
                if planned_cmd_response.allowed_exit_codes
                else (0,),
            )
        else:
            if planned_cmd_response.yaml_manifest and not uses_stdin:
                logger.warning(
                    "LLM provided a YAML manifest for command "
                    f"{full_kubect_command_str} but the command "
                    "does not use '-f -'. The manifest will be ignored."
                )

            logger.debug(
                f"Executing command {full_kubect_command_str} without "
                "direct YAML input."
            )
            kubectl_result = await asyncio.to_thread(
                run_kubectl,
                cmd=full_kubectl_command_list,
                config=cfg,
                allowed_exit_codes=tuple(planned_cmd_response.allowed_exit_codes)
                if planned_cmd_response.allowed_exit_codes
                else (0,),
            )

        if isinstance(kubectl_result, Error):
            logger.error(
                "Error executing planned command: "
                f"{full_kubect_command_str}. Error: {kubectl_result.error}"
            )
            final_results_summary += (
                f"Failed: {full_kubect_command_str}\nError: {kubectl_result.error}\n"
            )
            overall_success = False
            if kubectl_result.metrics:
                final_metrics = kubectl_result.metrics  # Or aggregate them
            continue

        # Process output of successful command
        summary_result = await handle_command_output(
            output=kubectl_result,  # Success[str]
            output_flags=output_flags,
            summary_prompt_func=apply_output_prompt,
            command=full_kubect_command_str,
        )

        if isinstance(summary_result, Success):
            summary_line = summary_result.data or "Command completed."
            final_results_summary += f"Success: {summary_line}\n"
        else:  # Error case
            error_line = (
                summary_result.error
                if isinstance(summary_result, Error)
                else "Unknown error"
            )
            final_results_summary += f"Error summarizing output: {error_line}\n"
            overall_success = False

        # Aggregate or update metrics
        if hasattr(summary_result, "metrics") and summary_result.metrics:
            final_metrics = summary_result.metrics  # Or aggregate them

    if overall_success:
        return Success(
            message="All planned commands executed successfully.",
            data=final_results_summary.strip(),
            metrics=final_metrics,
        )
    else:
        return Error(
            error="Some planned commands failed.",
            metrics=final_metrics,
        )


async def plan_and_execute_final_commands(
    semantically_valid_manifests: list[tuple[Path, str]],
    corrected_temp_manifest_paths: list[Path],
    unresolvable_sources: list[tuple[Path, str]],
    updated_operation_memory: str,
    llm_remaining_request: str,
    model_adapter: ModelAdapter,
    llm_model: Any,
    cfg: Config,
    output_flags: OutputFlags,
) -> Result:
    """Plan and execute final kubectl apply commands based on discovered manifests."""
    logger.info("Starting Step 5: Plan Final kubectl apply Command(s)")

    # Prepare data for final planning prompt
    valid_original_paths_str = [str(p) for p, _ in semantically_valid_manifests]
    corrected_paths_str = [str(p) for p in corrected_temp_manifest_paths]
    unresolvable_sources_str = [f"{p}: {reason}" for p, reason in unresolvable_sources]

    current_op_mem_for_final_plan = (
        updated_operation_memory
        if updated_operation_memory
        else "No operation memory generated."
    )
    remaining_req_for_final_plan = (
        llm_remaining_request
        if llm_remaining_request
        else "No specific remaining user request context."
    )
    unresolvable_for_final_plan = (
        "\n".join(unresolvable_sources_str)
        if unresolvable_sources_str
        else "All sources were processed or resolved."
    )
    valid_originals_for_final_plan = (
        "\n".join(valid_original_paths_str) if valid_original_paths_str else "None"
    )
    corrected_temps_for_final_plan = (
        "\n".join(corrected_paths_str) if corrected_paths_str else "None"
    )

    # Generate final plan prompt
    final_plan_system_frags, final_plan_user_frags = (
        plan_final_apply_command_prompt_fragments(
            valid_original_manifest_paths=valid_originals_for_final_plan,
            corrected_temp_manifest_paths=corrected_temps_for_final_plan,
            remaining_user_request=remaining_req_for_final_plan,
            current_operation_memory=current_op_mem_for_final_plan,
            unresolvable_sources=unresolvable_for_final_plan,
            final_plan_schema_json=_LLM_FINAL_APPLY_PLAN_RESPONSE_SCHEMA_JSON,
        )
    )

    # Execute LLM call for final planning
    try:
        (
            response_from_adapter,
            final_plan_metrics,
        ) = await model_adapter.execute_and_log_metrics(
            model=llm_model,
            system_fragments=final_plan_system_frags,
            user_fragments=final_plan_user_frags,
            response_model=LLMFinalApplyPlanResponse,
        )

        final_plan_obj = LLMFinalApplyPlanResponse.model_validate_json(
            response_from_adapter
        )

        planned_final_commands = final_plan_obj.planned_commands
        logger.info(
            f"LLM planned {len(planned_final_commands)} final apply command(s)."
        )

        # Execute the planned commands
        execution_result = await execute_planned_commands(
            planned_commands=planned_final_commands,
            cfg=cfg,
            output_flags=output_flags,
        )

        if isinstance(execution_result, Error):
            logger.error(
                f"Intelligent apply final execution failed: {execution_result.error}"
            )
            return Error(
                error="Intelligent apply failed during final execution: "
                f"{execution_result.error}",
                metrics=getattr(execution_result, "metrics", final_plan_metrics),
            )
        else:
            logger.info("Intelligent apply final execution completed.")
            return Success(
                message=execution_result.message,
                metrics=getattr(execution_result, "metrics", final_plan_metrics),
            )

    except (
        yaml.YAMLError,
        ValidationError,
        JSONDecodeError,
    ) as e_final_plan_parse:
        response_content_for_log = (
            str(response_from_adapter)[:500]
            if "response_from_adapter" in locals()
            else "Response content unavailable for logging"
        )
        logger.error(
            "Failed to parse LLM final plan response: "
            f"{e_final_plan_parse}. Raw/intermediate response "
            f"(first 500 chars): '{response_content_for_log}...'"
        )
        return Error(
            error=f"Failed to parse LLM final plan: {e_final_plan_parse}",
            exception=e_final_plan_parse,
        )
    except Exception as e_final_plan_general:
        logger.error(
            f"Error during final apply planning or execution: {e_final_plan_general}",
            exc_info=True,
        )
        return Error(
            error=f"Error in final apply stage: {e_final_plan_general}",
            exception=e_final_plan_general,
        )


async def run_intelligent_apply_workflow(
    request: str, cfg: Config, output_flags: OutputFlags
) -> Result:
    """Runs the full intelligent apply workflow, from scoping to execution."""
    logger.info("Starting intelligent apply workflow...")
    metrics = None  # Initialize metrics for this workflow

    temp_dir_for_corrected_manifests = tempfile.TemporaryDirectory(
        prefix="vibectl-apply-"
    )
    temp_dir_path = Path(temp_dir_for_corrected_manifests.name)
    logger.info(f"Created temporary directory for corrected manifests: {temp_dir_path}")

    try:
        # Step 1: Initial Scoping & Intent Extraction (LLM)
        model_name = cfg.get_typed("model", "claude-3.7-sonnet")
        model_adapter = get_model_adapter(config=cfg)
        llm_for_corrections_and_summaries = model_adapter.get_model(model_name)

        system_fragments, user_fragments = plan_apply_filescope_prompt_fragments(
            request=request
        )

        response_text, metrics = await model_adapter.execute_and_log_metrics(
            model=llm_for_corrections_and_summaries,
            system_fragments=system_fragments,
            user_fragments=user_fragments,
            response_model=ApplyFileScopeResponse,
        )
        if not response_text or response_text.strip() == "":
            logger.error("LLM returned an empty response for file scoping.")
            return Error(
                error="LLM returned an empty response for file scoping.",
                metrics=metrics,
            )

        logger.debug(f"Raw LLM response for file scope: {response_text}")
        file_scope_response = ApplyFileScopeResponse.model_validate_json(response_text)
        llm_scoped_files = file_scope_response.file_selectors
        llm_remaining_request = file_scope_response.remaining_request_context
        logger.info(f"LLM File Scoped Selectors: {llm_scoped_files}")
        logger.info(f"LLM Remaining Request Context: {llm_remaining_request}")

        # Step 2: File Discovery & Initial Validation (Local)
        logger.info("Starting Step 2: File Discovery & Initial Validation")
        (
            semantically_valid_manifests,
            invalid_sources_to_correct,
        ) = await discover_and_validate_files(
            file_selectors=llm_scoped_files,
            cfg=cfg,
        )

        # Check for critical errors
        if any(
            "CRITICAL: kubectl not found" in reason
            for _, _, reason in invalid_sources_to_correct
        ):
            logger.error("Halting intelligent apply due to kubectl not being found.")
            critical_errors = [
                reason
                for _, _, reason in invalid_sources_to_correct
                if "CRITICAL:" in reason
            ]
            return Error(
                error=f"Critical setup error: {'; '.join(critical_errors)}",
                metrics=metrics,
            )

        logger.info(
            "Total files discovered and processed: "
            f"{len(semantically_valid_manifests) + len(invalid_sources_to_correct)}"
        )
        logger.info(
            f"Semantically valid manifests found: {len(semantically_valid_manifests)}"
        )
        logger.info(
            "Invalid/non-manifest sources to correct/generate: "
            f"{len(invalid_sources_to_correct)}"
        )

        # Step 3: Summarize Valid Manifests & Build Operation Memory (LLM)
        logger.info(
            "Starting Step 3: Summarize Valid Manifests & Build Operation Memory"
        )
        (
            apply_operation_memory,
            updated_invalid_sources,
        ) = await summarize_manifests_and_build_memory(
            semantically_valid_manifests,
            model_adapter,
            llm_for_corrections_and_summaries,
            invalid_sources_to_correct,
        )

        # Step 4: Correction/Generation Loop for Invalid Sources (LLM)
        logger.info("Starting Step 4: Correction/Generation Loop for Invalid Sources")
        max_correction_retries = cfg.get_typed("max_correction_retries", 1)

        (
            corrected_temp_manifest_paths,
            unresolvable_sources,
            updated_operation_memory,
        ) = await correct_and_generate_manifests(
            updated_invalid_sources,
            apply_operation_memory,
            llm_remaining_request,
            model_adapter,
            llm_for_corrections_and_summaries,
            cfg,
            temp_dir_path,
            max_correction_retries,
        )

        # Step 5: Plan Final kubectl apply Command(s) (LLM)
        return await plan_and_execute_final_commands(
            semantically_valid_manifests,
            corrected_temp_manifest_paths,
            unresolvable_sources,
            updated_operation_memory,
            llm_remaining_request,
            model_adapter,
            llm_for_corrections_and_summaries,
            cfg,
            output_flags,
        )

    except (JSONDecodeError, ValidationError) as e_scope_parse:
        response_snippet = response_text[:500] if "response_text" in locals() else "N/A"
        logger.warning(
            "Failed to parse LLM file scope response as JSON "
            f"({type(e_scope_parse).__name__}). "
            f"Response Text: {response_snippet}..."
        )
        return Error(
            error=f"Failed to parse LLM file scope response: {e_scope_parse}",
            exception=e_scope_parse,
            metrics=metrics,
        )
    except Exception as e_workflow:
        logger.error(
            f"An unexpected error occurred in intelligent apply workflow: {e_workflow}",
            exc_info=True,
        )
        return Error(
            error=(
                "An unexpected error occurred in intelligent apply workflow: "
                f"{e_workflow}"
            ),
            exception=e_workflow,
            metrics=metrics,
        )
    finally:
        logger.info(
            f"Cleaning up temporary directory: {temp_dir_for_corrected_manifests.name}"
        )
        temp_dir_for_corrected_manifests.cleanup()
