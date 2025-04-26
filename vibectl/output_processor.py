"""
Output processor for vibectl.

Provides utilities for processing command output for LLM input,
handling token limits, and preparing data for AI processing.
"""

import json
import logging
import re
from typing import Any

import yaml

from . import truncation_logic as tl

# Import the new type and logic module
from .types import InvalidOutput, Output, Truncation, YamlSections

logger = logging.getLogger(__name__)


class OutputProcessor:
    """Process output from kubectl for different display modes."""

    def __init__(self, max_chars: int = 2000, llm_max_chars: int = 200):
        """Initialize processor with max character limits."""
        self.max_chars = max_chars
        self.llm_max_chars = llm_max_chars

    def process_logs(self, output: str, budget: int | None = None) -> Truncation:
        """Process log output, preserving recent logs if truncated.

        Args:
            output: Log output to process.
            budget: Optional character budget. If None, uses self.max_chars.

        Returns:
            A Truncation object containing the original and processed output.
        """
        char_budget = budget if budget is not None else self.max_chars
        original_length = len(output)

        if original_length <= char_budget:
            return Truncation(original=output, truncated=output)

        lines = output.splitlines()
        num_lines = len(lines)
        if num_lines == 0:
            return Truncation(original=output, truncated="")

        # Estimate initial max_lines based on budget and average line length
        # Add 1 to avoid division by zero for empty output/lines
        avg_line_len = original_length / num_lines if num_lines > 0 else 1
        # Estimate lines needed, add buffer (e.g., 20%) for marker overhead etc.
        estimated_lines_needed = (
            int((char_budget / avg_line_len) * 0.8) if avg_line_len > 0 else 100
        )
        current_max_lines = min(
            num_lines, max(10, estimated_lines_needed)
        )  # Ensure at least 10 lines try

        final_truncated = ""
        max_iterations = 5  # Safety break (N806)
        buffer_factor = 0.95  # Aim slightly under budget (N806)

        for _ in range(max_iterations):
            truncated_by_lines = tl._truncate_logs_by_lines(
                output, max_lines=current_max_lines
            )
            current_length = len(truncated_by_lines)

            if current_length <= char_budget:
                final_truncated = truncated_by_lines
                break  # Success!
            else:
                # Reduce lines proportionally based on overshoot
                # Avoid reducing lines too aggressively if overshoot is small
                reduction_factor = (char_budget * buffer_factor) / current_length
                current_max_lines = max(1, int(current_max_lines * reduction_factor))
        else:
            # Loop finished without success (max_iterations reached)
            # Fallback: use the last attempt or simple string truncation
            if not final_truncated:
                # Last attempt might still be over budget, so final truncate needed
                final_truncated = tl.truncate_string(truncated_by_lines, char_budget)

        # Ensure the final result absolutely respects the budget
        if len(final_truncated) > char_budget:
            final_truncated = tl.truncate_string(final_truncated, char_budget)

        return Truncation(original=output, truncated=final_truncated)

    def process_json(self, output: str, budget: int | None = None) -> Truncation:
        """Process JSON output, truncating if necessary.

        Args:
            output: JSON output string to process.
            budget: Optional character budget. If None, uses self.max_chars.

        Returns:
            A Truncation object containing the original and processed JSON string.
        """
        char_budget = budget if budget is not None else self.max_chars
        original_output = output  # Keep original for fallback
        try:
            # Basic validation
            data = json.loads(output)
        except json.JSONDecodeError:
            # If it's not valid JSON, treat as plain text using the provided budget
            truncated_output = tl.truncate_string(output, char_budget)
            return Truncation(
                original=output, truncated=truncated_output, original_type="text"
            )

        original_length = len(output)
        if original_length <= char_budget:
            # Return original if valid JSON and within limits
            return Truncation(original=output, truncated=output, original_type="json")

        # Basic Truncation: Use json_like_object truncation first
        # Estimate depth based on budget - very rough heuristic
        estimated_depth = 5 if char_budget > 1000 else 3
        estimated_list_len = 20 if char_budget > 1000 else 10

        truncated_data = tl.truncate_json_like_object(
            data, max_depth=estimated_depth, max_list_len=estimated_list_len
        )

        try:
            # Attempt to serialize the structurally truncated data
            truncated_output = json.dumps(
                truncated_data, indent=2
            )  # Pretty print slightly
        except (TypeError, OverflowError) as e:
            # Fallback 1: If serialization fails on truncated data, string
            # truncate the *original*
            logger.warning(
                f"JSON serialization failed after structural truncation ({e}), "
                "falling back to string truncation."
            )
            truncated_output = tl.truncate_string(original_output, char_budget)
            # Type remains json because original input was valid JSON
            return Truncation(
                original=original_output,
                truncated=truncated_output,
                original_type="json",
            )

        # Final check: if still over budget, apply string truncation
        if len(truncated_output) > char_budget:
            # Fallback 2: String truncate the serialized (but still too long) output
            truncated_output = tl.truncate_string(truncated_output, char_budget)

        # Return the truncated JSON
        return Truncation(
            original=original_output, truncated=truncated_output, original_type="json"
        )

    def format_kubernetes_resource(self, output: str) -> str:
        """Format a Kubernetes resource output (Placeholder)."""
        # TODO: Add specific formatting/highlighting for K8s resources if needed
        return output

    def validate_output_type(self, output: Any) -> Output:
        """Validate and detect the type of output (json, yaml, logs, text).

        Returns:
            Truncation: If the output is valid and its type is detected.
                        The truncated field is initially the same as original.
            InvalidOutput: If the input is fundamentally invalid (e.g., not a string).
        """
        if not isinstance(output, str):
            # Handle non-string types gracefully
            try:
                output_str = str(output)
                # Treat converted non-strings as plain text for now
                return Truncation(
                    original=output_str, truncated=output_str, original_type="text"
                )
            except Exception as e:
                # If conversion to string fails, it's truly invalid
                return InvalidOutput(
                    original=output,
                    reason=f"Input could not be converted to string: {e}",
                )

        # Handle empty or whitespace-only strings as text
        if not output or output.isspace():
            return Truncation(original=output, truncated=output, original_type="text")

        # 1. Try JSON first
        try:
            json.loads(output)
            return Truncation(original=output, truncated=output, original_type="json")
        except json.JSONDecodeError:
            pass  # Not JSON, proceed

        # 2. Check for log-like format (Moved before YAML)
        log_pattern = r"^\s*\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[-+]\d{2}:?\d{2})?\b"  # noqa: E501
        lines_to_check = output.splitlines()
        num_lines_to_check = len(lines_to_check)
        if num_lines_to_check > 0:
            lines_to_scan = lines_to_check[:10]  # Scan up to 10 lines
            log_lines_count = sum(
                1 for line in lines_to_scan if re.match(log_pattern, line)
            )
            # Consider logs if: >= 2 lines match OR (only 1 line exists and it matches)
            is_likely_log = log_lines_count >= 2 or (
                num_lines_to_check == 1 and log_lines_count == 1
            )
            if is_likely_log:
                logger.debug("Classifying as logs based on timestamp pattern.")
                return Truncation(
                    original=output, truncated=output, original_type="logs"
                )

        # 3. Try YAML (Moved after Log Check)
        try:
            logger.debug(
                f"Attempting YAML parse for output starting with: {output[:50]}..."
            )
            # Don't immediately convert to list, check the generator first
            yaml_generator = yaml.safe_load_all(output)
            try:
                first_doc = next(yaml_generator)
                # If we got here, at least one document exists
                docs = [first_doc, *list(yaml_generator)]  # RUF005
            except StopIteration:
                # Generator was empty
                docs = []
            except yaml.YAMLError as e:  # Catch parse errors during iteration too
                logger.debug(f"YAML parse during iteration failed: {e}")
                raise  # Re-raise to be caught by outer block

            logger.debug(
                f"YAML parse result (type: <class 'list'>, "
                f"len: {len(docs)} if isinstance(docs, list) else 'N/A')"
            )
            if docs:  # If parsing yielded something
                logger.debug(f"First doc type: {type(docs[0])}")
                # Check for explicit YAML markers even if parsed as a single string

                if len(docs) == 1 and isinstance(docs[0], str):
                    # Parsed as a single string -> Treat as TEXT
                    logger.debug("Parsed as single string, classifying as TEXT.")
                    return Truncation(
                        original=output, truncated=output, original_type="text"
                    )
                else:
                    # Multiple docs OR single complex doc (dict/list/etc.) -> YAML
                    logger.debug(
                        "Classifying as YAML based on multiple docs or complex "
                        "first doc."
                    )
                    return Truncation(
                        original=output, truncated=output, original_type="yaml"
                    )
            else:
                # Empty parse result, and doesn't start with --- -> TEXT
                logger.debug(
                    "YAML parse resulted in empty list and no markers, "
                    "classifying as TEXT."
                )
                return Truncation(
                    original=output, truncated=output, original_type="text"
                )  # Treat as text
        except yaml.YAMLError as e:
            logger.debug(f"YAML parse failed: {e}")
            pass  # Not valid YAML, proceed

        # 4. Default to text
        return Truncation(original=output, truncated=output, original_type="text")

    def _truncate_yaml_section_content(self, content: str, threshold: int) -> str:
        """Helper to truncate content within a YAML section."""
        if len(content) <= threshold:
            return content
        # Use standard string truncation for section content
        return tl.truncate_string(content, threshold)

    def _process_yaml_internal(
        self,
        output: str,
        char_limit: int,  # Parameter for overall limit and fallback truncation
    ) -> Truncation:
        """Internal logic to process YAML output, truncating sections based on budget.

        1. Extract sections from the first document.
        2. Calculate initial total length and section lengths.
        3. If total length exceeds char_limit:
           a. Calculate a 'fair share' budget per section.
           b. Identify sections exceeding their fair share.
           c. Apply secondary, more aggressive truncation ONLY to over-budget sections.
              (Currently uses simple string truncation on the section's YAML string).
           d. Reconstruct YAML from potentially truncated sections.
        4. Apply a final string truncation if the reconstructed YAML still
            exceeds char_limit.
        """
        # If we reach here, initial parsing succeeded (or will be attempted)
        if not output or output.isspace():
            return Truncation(original=output, truncated="", original_type="yaml")

        original_length = len(output)
        if original_length <= char_limit:
            # Return original content, ensuring type is yaml since initial parse passed
            return Truncation(original=output, truncated=output, original_type="yaml")

        # Needs truncation - Apply Budget Logic
        initial_sections = self.extract_yaml_sections(output)
        num_sections = len(initial_sections)
        if num_sections == 0:  # Should not happen if parse succeeded and not empty
            # Fallback to string truncation, but preserve original_type as yaml
            # Ensure the type is explicitly set here.
            logger.debug(
                "No YAML sections extracted, falling back to string truncation "
                "with type 'yaml'."
            )
            return Truncation(
                original=output,
                truncated=tl.truncate_string(output, char_limit),
                original_type="yaml",
            )

        # Estimate initial total length (including reconstruction overhead)
        current_sections = initial_sections.copy()
        reconstructed_yaml = self._reconstruct_yaml(current_sections)
        current_total_length = len(reconstructed_yaml)

        if current_total_length > char_limit:
            logger.debug(
                f"YAML needs budget truncation: {current_total_length} > {char_limit}"
            )
            # Calculate fair share (simple division for now)
            # Subtract overhead estimate for key names, newlines etc. from usable budget
            estimated_overhead = tl._calculate_yaml_overhead(num_sections)
            usable_budget = max(0, char_limit - estimated_overhead)
            fair_share = usable_budget // num_sections if num_sections > 0 else 0
            logger.debug(
                f"Budget: {char_limit}, Overhead: {estimated_overhead}, "
                f"Usable: {usable_budget}, Fair Share: {fair_share}"
            )

            # Apply secondary truncation to over-budget sections
            sections_to_reconstruct = {}
            for key, section_content in current_sections.items():
                section_len = len(section_content)

                if (
                    section_len > fair_share * 1.2 and fair_share > 0
                ):  # Only truncate if fair share > 0
                    logger.debug(
                        f"Applying secondary truncation to section '{key}': "
                        f"{section_len} > {fair_share}"
                    )
                    # Simple approach: Truncate the entire section string
                    truncated_section = tl.truncate_string(section_content, fair_share)

                    # Ensure subsequent document sections retain their separator
                    # after truncation.
                    is_subsequent_doc = key.startswith("document_")
                    missing_separator = not truncated_section.strip().startswith(
                        "--- \n"
                    )
                    # Check content validity carefully
                    is_valid_content = (
                        truncated_section.strip() and "..." not in truncated_section
                    )

                    if is_subsequent_doc and missing_separator and is_valid_content:
                        # Check if it looks like a fragment that lost its separator
                        # Avoid adding separator to completely empty/marker strings
                        logger.debug(f"Prepending --- to truncated section {key}")
                        # Combine with newline
                        truncated_section = f"---\n{truncated_section.lstrip()}"
                    sections_to_reconstruct[key] = truncated_section
                else:
                    sections_to_reconstruct[key] = section_content  # Keep as is

            # Reconstruct YAML from potentially truncated sections
            reconstructed_yaml = self._reconstruct_yaml(sections_to_reconstruct)

        # Final check: Apply simple string truncation if still over budget
        if len(reconstructed_yaml) > char_limit:
            logger.debug(
                f"Final YAML truncation needed: "
                f"{len(reconstructed_yaml)} > {char_limit}"
            )
            final_truncated_yaml = tl.truncate_string(reconstructed_yaml, char_limit)
        else:
            final_truncated_yaml = reconstructed_yaml

        # Ensure the type is 'yaml' since the initial parse succeeded
        return Truncation(
            original=output,
            truncated=final_truncated_yaml,
            original_type="yaml",  # Force 'yaml' if initial parse was ok
        )

    def extract_yaml_sections(self, yaml_output: str) -> YamlSections:
        """Extract sections from YAML output based on top-level keys of the
        first document, treating subsequent documents as whole sections."""
        sections: YamlSections = {}
        try:
            # Use safe_load_all for multi-document YAML
            # Store the generator to avoid consuming it prematurely
            docs_generator = yaml.safe_load_all(yaml_output)
            # Convert to list to handle potential errors during loading
            documents = list(docs_generator)

            if not documents:
                # If parsing yields nothing, treat as single content section
                # (Handles empty strings, comment-only strings, etc.)
                logger.debug("YAML parse yielded no documents, treating as content.")
                return {"content": yaml_output.strip()}

            # Process the first document
            first_doc = documents[0]
            if isinstance(first_doc, dict):
                # Extract top-level keys as sections from the first dict
                for key, value in first_doc.items():
                    # Dump each section back to YAML string
                    # Ensure flow style is block and width is infinite to prevent
                    # wrapping
                    try:
                        sections[key] = yaml.dump(
                            {key: value},
                            default_flow_style=False,
                            width=float("inf"),
                            allow_unicode=True,  # Preserve unicode characters
                            sort_keys=False,
                        ).strip()
                    except yaml.YAMLError as dump_error:
                        logger.warning(f"Error dumping section '{key}': {dump_error}")
                        # Fallback: use a simple string representation
                        sections[key] = f"{key}: [Error dumping value]"
            elif first_doc is not None:
                # If first doc is not a dict (list, primitive, etc.), use it directly
                # if it's a string, otherwise dump it.
                logger.debug("First document is not a dict.")
                if isinstance(first_doc, str):
                    logger.debug("First document is string, using directly as content.")
                    sections["content"] = first_doc  # Use the string directly
                else:
                    # Dump non-string, non-dict first docs (e.g., list)
                    logger.debug("First document is not string, dumping as content.")
                    try:
                        sections["content"] = yaml.dump(
                            first_doc,
                            default_flow_style=False,
                            explicit_start=True,  # Add --- for lists etc.
                            width=float("inf"),
                            allow_unicode=True,
                            sort_keys=False,
                        ).strip()
                    except yaml.YAMLError as dump_error:
                        # Log error dumping non-dict/non-string first doc
                        logger.warning(
                            f"Error dumping non-dict/non-string first "
                            f"document: {dump_error}"
                        )
                        sections["content"] = "[Error dumping first document]"
            # If first_doc is None (e.g., `---`), skip adding it explicitly.

            # Handle multi-document case: add subsequent docs as separate sections
            if len(documents) > 1:
                for i, doc_data in enumerate(documents[1:], start=2):
                    doc_key = f"document_{i}"
                    try:
                        # Dump subsequent documents completely, adding --- separator
                        doc_yaml = yaml.dump(
                            doc_data,
                            default_flow_style=False,
                            explicit_start=True,
                            width=float("inf"),
                            allow_unicode=True,
                            sort_keys=False,
                        )
                        sections[doc_key] = doc_yaml.strip()
                    except yaml.YAMLError as dump_error:
                        logger.warning(f"Error dumping document {i}: {dump_error}")
                        sections[doc_key] = f"---\n[Error dumping document {i}]"

        except yaml.YAMLError as load_error:
            # If initial safe_load_all fails, treat the whole output as a single
            # 'content' section
            logger.warning(
                f"Initial YAML load error ({load_error}), "
                f"falling back to content section."
            )
            # Ensure we strip whitespace from the original output here
            return {"content": yaml_output.strip()}

        # Handle the case where processing resulted in no sections
        # (e.g., only None docs).
        if not sections:
            logger.debug(
                "Processing resulted in no sections, returning original content."
            )
            return {"content": yaml_output.strip()}

        return sections

    def _reconstruct_yaml(self, sections: YamlSections) -> str:
        """Reconstruct YAML string from sections dictionary."""
        # Simpler reconstruction: Assume extract_yaml_sections returns
        # well-formatted YAML strings for each section (including keys)
        # and just join them.
        reconstructed_parts = [value_str.strip() for value_str in sections.values()]
        # Use double newline for better separation between top-level keys/docs
        return "\n\n".join(reconstructed_parts).strip()

    # New public method using standard limits
    def process_yaml(self, output: str, budget: int | None = None) -> Truncation:
        """Process YAML output, truncating sections if necessary (standard limits)."""
        char_budget = budget if budget is not None else self.max_chars
        return self._process_yaml_internal(
            output,
            char_limit=char_budget,  # Use provided or standard limit
        )

    # Renamed from process_auto to reflect general purpose, added budget
    def process_auto(self, output: Any, budget: int | None = None) -> Truncation:
        """Process output automatically, detecting type and truncating if necessary.

        Args:
            output: The output data (string or object).
            budget: Optional character budget. Defaults to self.max_chars.

        Returns:
            A Truncation object containing the original and processed output.
        """
        # Determine effective budget
        effective_budget = budget if budget is not None else self.max_chars

        # 1. Validate and Detect Type
        validation_result = self.validate_output_type(output)

        if isinstance(validation_result, InvalidOutput):
            # Fallback for fundamentally invalid input: treat as text, truncate
            original_str = str(validation_result.original)
            truncated = tl.truncate_string(
                original_str, effective_budget
            )  # Use effective_budget
            return Truncation(
                original=original_str, truncated=truncated, original_type="text"
            )

        # We have a valid Truncation object from validation
        # No truncation needed if already within effective_budget limit
        if len(validation_result.original) <= effective_budget:
            # Type was already set by validate_output_type
            return validation_result

        # Truncation needed, delegate based on detected type using effective_budget
        match validation_result.original_type:
            case "json":
                # Use process_json with effective_budget
                result = self.process_json(
                    validation_result.original, budget=effective_budget
                )
                # Ensure original_type is preserved
                return Truncation(
                    original=validation_result.original,
                    truncated=result.truncated,
                    original_type="json",
                )
            case "yaml":
                # Use process_yaml with effective_budget
                result = self.process_yaml(
                    validation_result.original, budget=effective_budget
                )
                # Ensure original_type is preserved
                return Truncation(
                    original=validation_result.original,
                    truncated=result.truncated,
                    original_type="yaml",
                )
            case "logs":
                # Use the logs processor with effective_budget
                result = self.process_logs(
                    validation_result.original, budget=effective_budget
                )
                return Truncation(
                    original=validation_result.original,
                    truncated=result.truncated,
                    original_type="logs",
                )
            case _:  # Default case (text)
                # Use standard string truncation with effective_budget
                truncated = tl.truncate_string(
                    validation_result.original, effective_budget
                )
                return Truncation(
                    original=validation_result.original,
                    truncated=truncated,
                    original_type="text",
                )


# Create global instance for easy import and potential state sharing later
output_processor = OutputProcessor()
