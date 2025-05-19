import asyncio
import glob
import tempfile
import uuid
from json import JSONDecodeError
from pathlib import Path

import yaml
from pydantic import ValidationError

from vibectl.command_handler import (
    configure_output_flags,
    handle_command_output,
)
from vibectl.config import Config
from vibectl.execution.vibe import (
    handle_vibe_request,
)
from vibectl.k8s_utils import run_kubectl, run_kubectl_with_yaml
from vibectl.logutil import logger
from vibectl.memory import configure_memory_flags
from vibectl.model_adapter import get_model_adapter
from vibectl.prompt import (
    _LLM_FINAL_APPLY_PLAN_RESPONSE_SCHEMA_JSON,
    PLAN_APPLY_PROMPT,
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
from vibectl.types import (
    Error,
    OutputFlags,
    Result,
    Success,
)


async def _validate_manifest_content(
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


async def _discover_and_validate_files(
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

            # Determine file type for more specific logging before validation
            file_type = "unknown"
            suffix = file_path.suffix.lower()
            if suffix in [".yaml", ".yml"]:
                file_type = "YAML"
            elif suffix == ".json":
                file_type = "JSON"
            elif suffix == ".txt":  # Could be a natural language description
                file_type = "text"
            logger.info(f"Validating {file_type} file: {file_path}")

            validation_result = await _validate_manifest_content(
                content, file_path, cfg
            )

            if isinstance(validation_result, Success):
                if validation_result.data and isinstance(validation_result.data, dict):
                    semantically_valid_manifests.append((file_path, content))
                    logger.info(
                        f"File {file_path} is valid: {validation_result.message}"
                    )
                else:
                    # TODO: should this case happen?
                    logger.error(
                        f"Validation returned Success for {file_path} but data "
                        "field is missing or invalid."
                    )
                    invalid_sources_to_correct.append(
                        (
                            file_path,
                            content,
                            "internal_error: Invalid Success object from validation "
                            f"for {file_path}",
                        )
                    )

            elif isinstance(validation_result, Error):
                error_full_message = validation_result.error
                # Extract the status code prefix (e.g., "empty_file:")
                status_code_prefix = error_full_message.split(":", 1)[0]

                if status_code_prefix == "kubectl_not_found":
                    logger.error(
                        "kubectl not found. Aborting intelligent apply. "
                        f"Error: {error_full_message}"
                    )
                    invalid_sources_to_correct.append(
                        (
                            file_path,
                            content,
                            f"CRITICAL: {error_full_message}",
                        )
                    )
                else:
                    invalid_sources_to_correct.append(
                        (
                            file_path,
                            content,
                            error_full_message,
                        )
                    )
                    logger.warning(
                        f"File {file_path} is invalid or not a K8s manifest. "
                        f"Reason: {error_full_message}"
                    )
            # No explicit else needed as validation_result must be Success or Error

    return semantically_valid_manifests, invalid_sources_to_correct


async def _execute_planned_commands(
    planned_commands: list[CommandAction],
    cfg: Config,
    output_flags: OutputFlags,
    # We might need a different summary prompt for the final apply output
    # vs. intermediate ones. For now, reusing apply_output_prompt, but this
    # could be a parameter.
) -> Result:
    """Executes a list of planned kubectl commands, handling output and errors."""
    overall_success = True
    final_results_summary = ""
    final_metrics = None

    for i, planned_cmd_response in enumerate(planned_commands):
        commands_to_log = planned_cmd_response.commands
        if commands_to_log is None:  # Should not happen if action_type is COMMAND
            commands_to_log = ["<no commands specified>"]

        full_kubectl_command_list = ["apply"] + (
            planned_cmd_response.commands if planned_cmd_response.commands else []
        )

        logger.info(
            f"Executing planned command {i + 1}/{len(planned_commands)}: "
            f"{' '.join(full_kubectl_command_list)}"
        )
        logger.debug(
            f"Planned command details: {planned_cmd_response.model_dump_json(indent=2)}"
        )

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
        if (
            not full_kubectl_command_list or len(full_kubectl_command_list) == 1
        ):  # Only contains "apply"
            logger.error(
                "Planned command list is effectively empty after prepending 'apply'. "
                f"Original: {planned_cmd_response.commands}"
            )
            final_results_summary += "Error: Planned command list effectively empty.\n"
            overall_success = False
            continue

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

        if planned_cmd_response.yaml_manifest and uses_stdin:
            logger.debug(
                f"Executing command {' '.join(full_kubectl_command_list)} "
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
                    f"{' '.join(full_kubectl_command_list)} but the command "
                    "does not use '-f -'. The manifest will be ignored."
                )

            logger.debug(
                f"Executing command {' '.join(full_kubectl_command_list)} without "
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
                f"{' '.join(full_kubectl_command_list)}. Error: {kubectl_result.error}"
            )
            final_results_summary += (
                f"Failed: {' '.join(full_kubectl_command_list)}\n"
                f"Error: {kubectl_result.error}\n"
            )
            overall_success = False
            if kubectl_result.metrics:
                final_metrics = kubectl_result.metrics  # Or aggregate them
            continue

        # Process output of successful command
        summary_result = await asyncio.to_thread(
            handle_command_output,
            output=kubectl_result,  # Success[str]
            output_flags=output_flags,
            summary_prompt_func=apply_output_prompt,
        )

        if isinstance(summary_result, Error):
            logger.error(
                "Error summarizing output for command: "
                f"{' '.join(full_kubectl_command_list)}. Error: {summary_result.error}"
            )
            summary_output = (
                kubectl_result.data if isinstance(kubectl_result, Success) else "N/A"
            )
            final_results_summary += (
                f"Succeeded: {' '.join(full_kubectl_command_list)}\n"
                f"Summary Error: {summary_result.error}\n"
                f"Output:\n{summary_output}\n"
            )
            # Command itself succeeded, so overall_success
            # might still be true depending on policy
            if summary_result.metrics:
                final_metrics = summary_result.metrics  # Or aggregate
        elif isinstance(summary_result, Success):
            logger.info(
                "Successfully executed and summarized: "
                f"{' '.join(full_kubectl_command_list)}"
            )
            final_results_summary += (
                f"Succeeded: {' '.join(full_kubectl_command_list)}\n"
                f"Summary:\n{summary_result.message}\n"
            )
            if summary_result.metrics:
                final_metrics = summary_result.metrics  # Or aggregate

    if overall_success:
        return Success(
            message=f"Final Apply Operation Summary:\n{final_results_summary.strip()}",
            metrics=final_metrics,
        )
    else:
        return Error(
            error="One or more planned apply commands failed. "
            f"Full Log:\n{final_results_summary.strip()}",
            metrics=final_metrics,
        )


async def _run_intelligent_apply_workflow(
    request: str, cfg: Config, output_flags: OutputFlags
) -> Result:
    """Runs the full intelligent apply workflow, from scoping to execution."""
    logger.info("Starting intelligent apply workflow...")
    metrics = None  # Initialize metrics for this workflow

    corrected_temp_manifest_paths: list[Path] = []
    unresolvable_sources: list[tuple[Path, str]] = []

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

        response_text, metrics = await asyncio.to_thread(
            model_adapter.execute_and_log_metrics,
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
        ) = await _discover_and_validate_files(
            file_selectors=llm_scoped_files,
            cfg=cfg,
        )
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
        for p, _ in semantically_valid_manifests:
            logger.debug(f"  - Valid: {p}")
        logger.info(
            "Invalid/non-manifest sources to correct/generate: "
            f"{len(invalid_sources_to_correct)}"
        )
        for p, content, reason in invalid_sources_to_correct:
            content_excerpt = (
                (content[:50] + "..." if content and len(content) > 50 else content)
                if content
                else "N/A"
            )
            logger.debug(
                f"  - Invalid: {p} (Content: {content_excerpt}, "
                f"Reason: {reason[:100]}{'...' if len(reason) > 100 else ''})"
            )

        # Step 3: Summarize Valid Manifests & Build Operation Memory (LLM)
        logger.info(
            "Starting Step 3: Summarize Valid Manifests & Build Operation Memory"
        )
        apply_operation_memory = ""
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
                summary_text, summary_metrics = await asyncio.to_thread(
                    model_adapter.execute_and_log_metrics,
                    model=llm_for_corrections_and_summaries,
                    system_fragments=summary_system_frags,
                    user_fragments=summary_user_frags,
                    response_model=None,
                )
                metrics = summary_metrics  # type: ignore

                if not summary_text or summary_text.strip() == "":
                    logger.warning(
                        f"LLM returned empty summary for {file_path}. "
                        "Skipping update to operation memory."
                    )
                    continue

                logger.debug(f"LLM summary for {file_path}:\\n{summary_text}")
                apply_operation_memory += (
                    f"Summary for {file_path}:\\n{summary_text}\\n\\n"
                    f"--------------------\\n"
                )
                logger.info(f"Updated operation memory after summarizing {file_path}")

            except Exception as e_summary:
                logger.error(
                    f"Error summarizing manifest {file_path}: {e_summary}",
                    exc_info=True,
                )
                invalid_sources_to_correct.append(
                    (
                        file_path,
                        manifest_content,
                        f"summary_error_during_step3: {e_summary}",
                    )
                )
        logger.info("Finished summarizing valid manifests.")
        if apply_operation_memory:
            logger.debug(
                f"Current Operation Memory after Step 3:\\n{apply_operation_memory}"
            )
        else:
            logger.info(
                "Operation memory is empty after Step 3 (no valid manifests or "
                "all summaries failed)."
            )

        # Step 4: Correction/Generation Loop for Invalid Sources (LLM)
        logger.info("Starting Step 4: Correction/Generation Loop for Invalid Sources")
        max_correction_retries = cfg.get_typed("max_correction_retries", 1)

        for (
            original_path,
            original_content,
            error_reason_full,
        ) in invalid_sources_to_correct:
            # Skip if critical error like kubectl not found, already handled
            # by returning early
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
                    apply_operation_memory
                    if apply_operation_memory
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
                    ) = await asyncio.to_thread(
                        model_adapter.execute_and_log_metrics,
                        model=llm_for_corrections_and_summaries,
                        system_fragments=correction_system_frags,
                        user_fragments=correction_user_frags,
                        response_model=None,  # Expecting raw YAML string
                    )
                    metrics = correction_metrics  # type: ignore

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

                    logger.debug(
                        f"LLM proposed YAML for {original_path} "
                        f"(attempt {attempt + 1}):\n{proposed_yaml_str[:500]}..."
                    )

                    # Validate the proposed YAML
                    temp_correction_path = (
                        temp_dir_path
                        / f"corrected_{original_path.name}_{uuid.uuid4().hex[:8]}.yaml"
                    )
                    validation_result = await _validate_manifest_content(
                        proposed_yaml_str, temp_correction_path, cfg
                    )

                    if isinstance(validation_result, Success):
                        # The message from Success already indicates validity and path.
                        # The data field in Success contains
                        # {"file_path": str, "content": str}
                        # We use the proposed_yaml_str here for writing.
                        temp_correction_path.write_text(proposed_yaml_str)
                        corrected_temp_manifest_paths.append(temp_correction_path)
                        logger.info(
                            "Successfully corrected/generated and validated manifest "
                            f"for {original_path}, saved to {temp_correction_path}. "
                            f"Details: {validation_result.message}"
                        )

                        logger.info(
                            "Summarizing newly corrected manifest: "
                            f"{temp_correction_path}"
                        )
                        current_op_mem_for_summary = (
                            apply_operation_memory
                            if apply_operation_memory
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
                            ) = await asyncio.to_thread(
                                model_adapter.execute_and_log_metrics,
                                model=llm_for_corrections_and_summaries,
                                system_fragments=new_summary_system_frags,
                                user_fragments=new_summary_user_frags,
                                response_model=None,
                            )
                            metrics = new_summary_metrics  # type: ignore
                            if new_summary_text and new_summary_text.strip():
                                apply_operation_memory += (
                                    f"Summary for newly corrected {original_path} "
                                    f"(as {temp_correction_path.name}):\\n"
                                    f"{new_summary_text}\\n\\n"
                                    f"--------------------\\n"
                                )
                                logger.info(
                                    f"Updated operation memory after summarizing "
                                    f"corrected manifest {temp_correction_path.name}"
                                )
                            else:
                                logger.warning(
                                    "LLM returned empty summary for corrected "
                                    f"manifest {temp_correction_path.name}."
                                )
                        except Exception as e_new_summary:
                            logger.error(
                                "Error summarizing corrected manifest "
                                f"{temp_correction_path.name}: {e_new_summary}",
                                exc_info=True,
                            )
                            # Continue, as main correction was successful

                        corrected_successfully = True
                        break  # Break from retry loop for this source
                    else:  # It must be an Error object
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
                    error_reason_full = (
                        f"correction_exception: {e_correction}"  # Update error reason
                    )
                    if attempt == max_correction_retries:
                        unresolvable_sources.append(
                            (
                                original_path,
                                f"Exception during correction for {original_path} "
                                f"after {max_correction_retries + 1} attempts. "
                                f"Last error: {error_reason_full}",
                            )
                        )
                    # Continue to next retry or next file

            if not corrected_successfully and not any(
                u_path == original_path for u_path, _ in unresolvable_sources
            ):
                # If loop finished without success and it wasn't added
                # to unresolvable for other reasons (like empty LLM output)
                unresolvable_sources.append(
                    (
                        original_path,
                        f"Correction attempts failed for {original_path}. "
                        f"Last reason: {error_reason_full}",
                    )
                )

        logger.info("Finished Step 4: Correction/Generation Loop.")
        logger.info(
            f"Total corrected/generated manifests: {len(corrected_temp_manifest_paths)}"
        )
        for p in corrected_temp_manifest_paths:
            logger.debug(f"  - Corrected/Generated: {p}")
        logger.info(
            f"Total unresolvable sources after Step 4: {len(unresolvable_sources)}"
        )
        for p, reason in unresolvable_sources:
            logger.debug(
                f"  - Unresolvable: {p} (Reason: "
                f"{reason[:150]}{'...' if len(reason) > 150 else ''})"
            )
        if apply_operation_memory:
            logger.debug(
                f"Final Operation Memory after Step 4:\\n{apply_operation_memory}"
            )

        # Step 5: Plan Final kubectl apply Command(s) (LLM)
        logger.info("Starting Step 5: Plan Final kubectl apply Command(s)")

        valid_original_paths_str = [str(p) for p, _ in semantically_valid_manifests]
        corrected_paths_str = [str(p) for p in corrected_temp_manifest_paths]
        unresolvable_sources_str = [
            f"{p}: {reason}" for p, reason in unresolvable_sources
        ]

        current_op_mem_for_final_plan = (
            apply_operation_memory
            if apply_operation_memory
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

        try:
            response_from_adapter, final_plan_metrics = await asyncio.to_thread(
                model_adapter.execute_and_log_metrics,
                model=llm_for_corrections_and_summaries,
                system_fragments=final_plan_system_frags,
                user_fragments=final_plan_user_frags,
                response_model=LLMFinalApplyPlanResponse,
            )
            metrics = final_plan_metrics  # type: ignore

            # This will raise ValidationError or JSONDecodeError if parsing fails,
            # which will be caught by the except block below.
            final_plan_obj = LLMFinalApplyPlanResponse.model_validate_json(
                response_from_adapter
            )

            planned_final_commands = final_plan_obj.planned_commands
            logger.info(
                f"LLM planned {len(planned_final_commands)} final apply command(s)."
            )

            # Execute these commands
            execution_result = await _execute_planned_commands(
                planned_commands=planned_final_commands,
                cfg=cfg,
                output_flags=output_flags,
            )

            # Step 6: Cleanup and Reporting (Local) - to be implemented next
            # For now, the result of execution is the final result of intelligent apply.
            if isinstance(execution_result, Error):
                logger.error(
                    "Intelligent apply final execution failed: "
                    f"{execution_result.error}"
                )
            else:
                logger.info("Intelligent apply final execution completed.")
            # The metrics from execution_result should be the final ones now
            final_result_metrics = getattr(execution_result, "metrics", metrics)

            # Update the final return to reflect actual outcome
            if isinstance(execution_result, Success):
                return Success(
                    message=execution_result.message,
                    metrics=final_result_metrics,
                )
            else:  # Is Error
                error_message = getattr(
                    execution_result,
                    "error",
                    "Unknown error during final execution.",
                )
                return Error(
                    error="Intelligent apply failed during final execution: "
                    f"{error_message}",
                    metrics=final_result_metrics,
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
                metrics=metrics,
                exception=e_final_plan_parse,
            )
        except Exception as e_final_plan_general:
            logger.error(
                "Error during final apply planning or execution: "
                f"{e_final_plan_general}",
                exc_info=True,
            )
            return Error(
                error=f"Error in final apply stage: {e_final_plan_general}",
                metrics=metrics,
                exception=e_final_plan_general,
            )

    except (JSONDecodeError, ValidationError) as e_outer:
        logger.warning(
            "Failed to parse LLM file scope response as JSON "
            f"({type(e_outer).__name__}). "
            f"Response Text: {response_text[:500]}..."
        )
        return Error(
            error=f"Failed to parse LLM file scope response: {e_outer}",
            exception=e_outer,
            metrics=getattr(
                e_outer, "metrics", metrics
            ),  # metrics might not be updated if error is in first LLM call
        )
    except Exception as e_outer_general:
        logger.error(
            "An unexpected error occurred in intelligent apply workflow: "
            f"{e_outer_general}",
            exc_info=True,
        )
        error_metrics = getattr(e_outer_general, "metrics", None)
        # Try to get metrics if available, otherwise it might be None
        # from an earlier stage or a general Python error
        current_metrics_state = metrics if "metrics" in locals() else error_metrics

        return Error(
            error="An unexpected error occurred in intelligent apply workflow. "
            f"{e_outer_general}",
            exception=e_outer_general,
            metrics=current_metrics_state,
        )
    finally:
        if temp_dir_for_corrected_manifests:
            logger.info(
                "Cleaning up temporary directory: "
                f"{temp_dir_for_corrected_manifests.name}"
            )
            temp_dir_for_corrected_manifests.cleanup()


async def run_apply_command(
    args: tuple[str, ...],
    show_raw_output: bool | None,
    show_vibe: bool | None,
    show_kubectl: bool | None,
    model: str | None,
    freeze_memory: bool,
    unfreeze_memory: bool,
    show_metrics: bool | None,
) -> Result:
    """
    Implements the 'apply' subcommand logic, including logging and error handling.
    Returns a Result (Success or Error).
    """
    logger.info(f"Invoking 'apply' subcommand with args: {args}")
    configure_memory_flags(freeze_memory, unfreeze_memory)

    output_flags = configure_output_flags(
        show_raw_output=show_raw_output,
        show_vibe=show_vibe,
        model=model,
        show_kubectl=show_kubectl,
        show_metrics=show_metrics,
    )

    cfg = Config()

    if args[0] == "vibe":
        args = args[1:]
        if len(args) < 1:
            msg = (
                "Missing request after 'vibe' command. "
                "Please provide a natural language request, e.g.: "
                'vibectl apply vibe "server side new.yaml"'
            )
            return Error(error=msg)
        request = " ".join(args)
        logger.info(f"Planning how to: {request}")

        if cfg.get_typed("intelligent_apply", True):
            return await _run_intelligent_apply_workflow(request, cfg, output_flags)
        else:  # Not intelligent_apply
            logger.info("Using standard vibe request handler for apply.")
            # Ensure result is awaited if handle_vibe_request is async
            result_standard_vibe = await handle_vibe_request(
                request=request,
                command="apply",
                plan_prompt_func=lambda: PLAN_APPLY_PROMPT,
                summary_prompt_func=apply_output_prompt,
                output_flags=output_flags,
                yes=False,
            )

            if isinstance(result_standard_vibe, Error):
                logger.error(
                    f"Error from handle_vibe_request: {result_standard_vibe.error}"
                )
                return result_standard_vibe

            logger.info("Completed 'apply' subcommand for standard vibe request.")
            return result_standard_vibe

    else:
        cmd = ["apply", *args]

        kubectl_result_direct: Result = await asyncio.to_thread(
            run_kubectl,
            cmd=cmd,
            config=cfg,
        )

        if isinstance(kubectl_result_direct, Error):
            logger.error(
                f"Error running kubectl for direct apply: {kubectl_result_direct.error}"
            )
            return kubectl_result_direct

        result_direct_apply = await asyncio.to_thread(
            handle_command_output,
            output=kubectl_result_direct,
            output_flags=output_flags,
            summary_prompt_func=apply_output_prompt,
        )

        logger.info("Completed direct 'apply' subcommand execution.")
        return result_direct_apply
