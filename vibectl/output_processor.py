"""
Output processor for vibectl.

Provides utilities for processing command output for LLM input,
handling token limits, and preparing data for AI processing.
"""

import json
import re
import textwrap
from typing import Any, Tuple

import yaml

# Import the new type and logic module
from .types import Truncation, YamlSections
from . import truncation_logic as tl


class OutputProcessor:
    """Process output from kubectl for different display modes."""

    def __init__(self, max_chars: int = 2000, llm_max_chars: int = 200):
        """Initialize processor with max character limits."""
        self.max_chars = max_chars
        self.llm_max_chars = llm_max_chars

    def process_for_llm(self, output: str) -> Truncation:
        """Process plain text output for LLM input, truncating if necessary.

        Args:
            output: Text output to process.

        Returns:
            A Truncation object containing the original and processed output.
        """
        if len(output) <= self.llm_max_chars:
            return Truncation(original=output, truncated=output)

        # Use the dedicated string truncation function for LLM context
        truncated_output = tl.truncate_string(output, self.llm_max_chars)
        return Truncation(original=output, truncated=truncated_output)

    def process_logs(self, output: str) -> Truncation:
        """Process log output, preserving recent logs if truncated.

        Args:
            output: Log output to process.

        Returns:
            A Truncation object containing the original and processed output.
        """
        original_length = len(output)
        if original_length <= self.max_chars:
            return Truncation(original=output, truncated=output)

        lines = output.splitlines() # Use splitlines to handle different line endings
        num_lines = len(lines)
        # Define how many lines to keep from start/end
        # Keep more from the end for logs (e.g., 60%), less from start (e.g., 40%)
        # Ensure minimum lines kept if total lines are few but content is long
        max_lines = 100 # Arbitrary limit for when to start truncating lines
        if num_lines <= max_lines:
             # Still truncate char length if too long but few lines
             truncated_output = tl.truncate_string(output, self.max_chars)
             return Truncation(original=output, truncated=truncated_output)

        end_lines_count = min(num_lines -1, 60) # Keep up to 60 lines from the end
        start_lines_count = min(num_lines - end_lines_count, 40) # Keep up to 40 from the start

        # Ensure we don't overlap or miss lines if counts are large relative to num_lines
        if start_lines_count + end_lines_count >= num_lines:
             # Should not happen with current logic, but safeguard
             start_lines_count = num_lines // 2
             end_lines_count = num_lines - start_lines_count

        first_chunk = "\n".join(lines[:start_lines_count])
        last_chunk = "\n".join(lines[num_lines - end_lines_count:])

        # Apply line-based truncation
        lines_truncated_count = num_lines - start_lines_count - end_lines_count
        marker = f"[... {lines_truncated_count} lines truncated ...]" if lines_truncated_count > 0 else ""
        truncated_by_lines = f"{first_chunk}\n{marker}\n{last_chunk}" if marker else f"{first_chunk}\n{last_chunk}"

        # Check if the result (after line truncation) is within char limits
        if len(truncated_by_lines) <= self.max_chars:
            final_truncated = truncated_by_lines
        else:
            # If still too long by chars, truncate the combined string using the standard method.
            # The truncation logic will handle the marker if it's part of the kept sections.
            final_truncated = tl.truncate_string(truncated_by_lines, self.max_chars)

        # Final check to ensure max_chars is strictly enforced (should be redundant if tl.truncate_string works)
        if len(final_truncated) > self.max_chars:
            final_truncated = tl.truncate_string(final_truncated, self.max_chars)

        return Truncation(original=output, truncated=final_truncated)

    def process_json(self, output: str) -> Truncation:
        """Process JSON output, truncating if necessary.

        Args:
            output: JSON output string to process.

        Returns:
            A Truncation object containing the original and processed JSON string.
        """
        try:
            # Basic validation
            json.loads(output)
        except json.JSONDecodeError:
            # If it's not valid JSON, treat as plain text using LLM limits
            return self.process_for_llm(output)

        original_length = len(output)
        if original_length <= self.max_chars:
            # Return original if valid JSON and within limits
            return Truncation(original=output, truncated=output)

        # Perform basic string truncation
        truncated_output = tl.truncate_string(output, self.max_chars)

        # Return the truncated JSON
        return Truncation(original=output, truncated=truncated_output)

    def format_kubernetes_resource(self, output: str) -> str:
        """Format a Kubernetes resource output (Placeholder)."""
        # TODO: Add specific formatting/highlighting for K8s resources if needed
        return output

    def detect_output_type(self, output: Any) -> str:
        """Detect the type of output (json, yaml, logs, text)."""
        if not isinstance(output, str):
            return "text"

        # 1. Try JSON first (covers simple types and objects/arrays)
        try:
            json.loads(output)
            return "json"
        except json.JSONDecodeError:
            pass # Not JSON, proceed to other checks

        # 2. Try YAML directly (duck-typing)
        try:
            docs = list(yaml.safe_load_all(output)) # Check if parsable and get docs
            # print(f"DEBUG: docs = {docs}, input_len={len(output)}") # Comment out debug print
            if not docs: # Handle empty case like "---" or ""
                 pass # Treat as non-YAML for now
            else:
                # Consider it YAML if first doc is complex OR there are multiple docs
                first_doc_is_complex = isinstance(docs[0], (dict, list))
                is_multidoc = len(docs) > 1

                if first_doc_is_complex or is_multidoc:
                     return "yaml"
        except yaml.YAMLError:
            pass # Not valid YAML

        # 3. Check for log-like format (Allow leading whitespace)
        log_pattern = r"^\s*\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[-+]\d{2}:?\d{2})?\b"
        for line in output.splitlines()[:5]:
            if re.match(log_pattern, line):
                return "logs"

        # 4. Default to text
        return "text"

    def _truncate_yaml_section_content(self, content: str, threshold: int) -> str:
        """Helper to truncate content within a YAML section."""
        if len(content) <= threshold:
             return content
        # Use standard string truncation for section content
        return tl.truncate_string(content, threshold)

    def _process_yaml_internal(
        self,
        output: str,
        char_limit: int, # Parameter for overall limit and fallback truncation
    ) -> Truncation:
        """Internal logic to process YAML output, truncating sections if necessary."""
        try:
            # Quick check if valid YAML before extensive processing
            list(yaml.safe_load_all(output))
        except yaml.YAMLError:
            # If invalid YAML, treat as plain text (using LLM limits)
            # Note: Using self.llm_max_chars for fallback, consistent with process_for_llm
            return Truncation(original=output, truncated=tl.truncate_string(output, self.llm_max_chars))

        original_length = len(output)
        if original_length <= char_limit:
            return Truncation(original=output, truncated=output)

        # Simplified: Perform basic string truncation using the provided char_limit
        final_truncated_yaml = tl.truncate_string(output, char_limit)

        return Truncation(
            original=output,
            truncated=final_truncated_yaml
        )

    def process_auto(self, output: Any) -> Truncation:
        """Process output based on auto-detected type, returning Truncation."""
        # Handle non-string inputs safely
        if not isinstance(output, str):
            output_str = str(output)
            return Truncation(original=output_str, truncated=output_str)

        output_type = self.detect_output_type(output)

        # Delegate to the specific processing method
        match output_type:
            case "json":
                return self.process_json(output)
            case "yaml":
                return self._process_yaml_internal(output, self.max_chars)
            case "logs":
                return self.process_logs(output)
            case _:  # Default case (text)
                # Use process_for_llm limits for generic text
                return self.process_for_llm(output)

    def extract_yaml_sections(self, yaml_output: str) -> YamlSections:
        """Extract sections from YAML output based on top-level keys."""
        sections: YamlSections = {}
        try:
            # Use safe_load_all for multi-document YAML, process first doc mainly
            documents = list(yaml.safe_load_all(yaml_output))
            if not documents:
                return {"content": yaml_output.strip()}

            data = documents[0] # Focus on the first document

            if data is None:
                return {"content": yaml_output.strip()}

            if not isinstance(data, dict) or not data:
                # If not a dict or empty, dump the first doc back as content
                 # Use block style, explicit start marker for clarity
                # Check for string with explicit tag
                if isinstance(data, str) and "!!str" in yaml_output:
                    return {"content": yaml_output.strip()}
                content_yaml = yaml.dump(data, default_flow_style=False, explicit_start=True)
                return {"content": content_yaml.strip()}

            # Extract top-level keys as sections
            for key, value in data.items():
                # Dump each section back to YAML string
                sections[key] = yaml.dump({key: value}, default_flow_style=False).strip()

            # Handle multi-document case: add subsequent docs as separate sections
            if len(documents) > 1:
                 for i, doc_data in enumerate(documents[1:], start=2):
                     doc_key = f"document_{i}"
                     doc_yaml = yaml.dump(doc_data, default_flow_style=False, explicit_start=True)
                     sections[doc_key] = doc_yaml.strip()

        except yaml.YAMLError:
            # If parsing fails, treat the whole output as a single 'content' section
            return {"content": yaml_output.strip()}

        return sections

    def _reconstruct_yaml(self, sections: YamlSections) -> str:
        """Reconstruct YAML string from sections dictionary."""
        # Simple concatenation, assuming keys are top-level
        # Ensure consistent spacing between sections
        reconstructed = []
        for key, value_str in sections.items():
            # If the value doesn't already represent a full key: value block, format it
            if not value_str.strip().startswith(f"{key}:"):
                 # Indent the value string correctly under the key
                 indented_value = textwrap.indent(value_str.strip(), '  ')
                 reconstructed.append(f"{key}\n{indented_value}")
            else:
                 # Value already contains the key (from dump({key: value}))
                 reconstructed.append(value_str.strip()) # Append as is

        # Join sections with double newline for readability
        return "\n\n".join(reconstructed).strip()

    # New public method using standard limits
    def process_yaml(self, output: str) -> Truncation:
        """Process YAML output, truncating sections if necessary (standard limits)."""
        return self._process_yaml_internal(
            output,
            char_limit=self.max_chars, # Standard overall limit
        )


# Create global instance for easy import and potential state sharing later
output_processor = OutputProcessor()
