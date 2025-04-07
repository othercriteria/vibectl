"""
Output processor for vibectl.

Provides utilities for processing command output for LLM input,
handling token limits, and preparing data for AI processing.
"""

import json
import re
import textwrap
from typing import Any, TypeVar

import yaml

T = TypeVar("T")


class OutputProcessor:
    """Process output from kubectl for different display modes."""

    def __init__(self, max_chars: int = 2000, llm_max_chars: int = 200):
        """Initialize processor with max character limits."""
        self.max_chars = max_chars
        self.llm_max_chars = llm_max_chars
        self.important_keys = {
            "name",
            "status",
            "kind",
            "apiVersion",
            "metadata",
            "details",
            "nested",
            "level1",
            "level2",
            "level3",
            "clientVersion",
            "serverVersion",
            "gitVersion",
            "platform",
        }

    def _truncate_json_object(self, obj: Any, max_depth: int = 3) -> Any:
        """Recursively truncate a JSON object to a maximum depth."""
        if not isinstance(obj, dict | list) or max_depth <= 0:
            return obj

        if isinstance(obj, dict):
            return {
                k: self._truncate_json_object(v, max_depth - 1) for k, v in obj.items()
            }
        elif isinstance(obj, list):
            if len(obj) <= 10:
                return [self._truncate_json_object(item, max_depth - 1) for item in obj]
            else:
                # If list is too long, keep first and last few items
                first_items = [
                    self._truncate_json_object(item, max_depth - 1) for item in obj[:5]
                ]
                last_items = [
                    self._truncate_json_object(item, max_depth - 1) for item in obj[-5:]
                ]
                truncated_item = {"...": f"{len(obj) - 10} more items..."}
                return [*first_items, truncated_item, *last_items]

    def process_for_llm(self, output: str) -> tuple[str, bool]:
        """Process output for LLM input, truncating if necessary."""
        if len(output) <= self.max_chars:
            return output, False

        # If output is too long, truncate it
        first_chunk_size = self.llm_max_chars // 2
        last_chunk_size = self.llm_max_chars // 2

        first_chunk = output[:first_chunk_size]
        last_chunk = output[-last_chunk_size:]

        return f"{first_chunk}\n[...truncated...]\n{last_chunk}", True

    def process_logs(self, output: str) -> tuple[str, bool]:
        """Process log output.

        Args:
            output: Log output to process

        Returns:
            Tuple of (processed output, whether truncation occurred)
        """
        if len(output) <= self.max_chars:
            return output, False

        # For logs, we want to preserve more recent logs
        lines = output.split("\n")
        if len(lines) <= 100:
            return output, False

        # Keep first and last lines with more emphasis on recent logs
        first_chunk = "\n".join(lines[:40])
        last_chunk = "\n".join(lines[-60:])
        truncated = f"{first_chunk}\n[...truncated...]\n{last_chunk}"

        return truncated, True

    def process_json(self, output: str) -> tuple[str, bool]:
        """Process JSON output.

        Args:
            output: JSON output to process

        Returns:
            Tuple of (processed output, whether truncation occurred)
        """
        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            return output, False

        if len(output) <= self.max_chars:
            return output, False

        # Check how deeply nested the object is
        max_depth = self._find_max_depth(data)
        if max_depth > 3:
            # If very nested, truncate more aggressively
            truncated_data = self._truncate_json_object(data, max_depth=2)
        else:
            # Otherwise normal truncation
            truncated_data = self._truncate_json_object(data)

        # Convert back to JSON
        truncated_output = json.dumps(truncated_data, indent=2)
        return truncated_output, True

    def format_kubernetes_resource(self, output: str) -> str:
        """Format a Kubernetes resource output."""
        # Add some processing specific to Kubernetes resources
        return output

    def detect_output_type(self, output: str) -> str:
        """Detect the type of output."""
        # Try to determine if output is JSON
        try:
            json.loads(output)
            return "json"
        except json.JSONDecodeError:
            pass

        # Check for YAML markers
        if "apiVersion:" in output or "kind:" in output:
            return "yaml"

        # Check for log-like format
        log_pattern = r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"
        if re.search(log_pattern, output):
            return "logs"

        # Default to text
        return "text"

    def truncate_yaml_status(self, sections: dict[str, str]) -> dict[str, str]:
        """Truncate YAML status sections which are often very verbose.

        Args:
            sections: Dictionary of YAML sections

        Returns:
            Dictionary with status section potentially truncated
        """
        result = sections.copy()

        # If there's a status section, truncate it more aggressively
        if "status" in result and len(result["status"]) > 500:
            lines = result["status"].split("\n")
            if len(lines) > 10:
                # Keep first few lines and last few lines
                result["status"] = (
                    "\n".join(lines[:5])
                    + "\n...[status truncated]...\n"
                    + "\n".join(lines[-5:])
                )

        return result

    def extract_yaml_sections(self, yaml_output: str) -> dict[str, str]:
        """Extract sections from YAML output.

        Args:
            yaml_output: YAML output string

        Returns:
            Dictionary of sections, where each key is a top-level key and
            the value is the YAML content for that section.
        """
        sections = {}
        try:
            # Try to parse the YAML
            data = yaml.safe_load(yaml_output)
            if data is None:
                # Return a default section if the YAML is empty
                return {"content": yaml_output.strip()}

            # Handle non-dictionary data or empty dictionaries
            if not isinstance(data, dict) or not data:
                return {"content": yaml_output.strip()}

            # For typical Kubernetes resources, extract sections
            for key, value in data.items():
                # Convert back to YAML for consistent handling
                sections[key] = yaml.dump(value, default_flow_style=False)

        except yaml.YAMLError:
            # If parsing fails, handle the output as a single section
            return {"content": yaml_output.strip()}

        # If we couldn't extract sections, treat the whole output as one section
        if not sections:
            sections = {"content": yaml_output.strip()}

        return sections

    def process_auto(self, output: str) -> tuple[str, bool]:
        """Process output based on auto-detection of type.

        Args:
            output: Output to process

        Returns:
            Tuple of (processed output, whether truncation occurred)
        """
        # Detect output type
        output_type = self.detect_output_type(output)

        # Use match statement to handle different output types (Python 3.10+)
        match output_type:
            case "json":
                return self.process_json(output)
            case "yaml":
                return self.process_yaml(output)
            case "logs":
                return self.process_logs(output)
            case _:  # Default case
                return self.process_for_llm(output)

    def process_output_for_vibe(self, output: str) -> tuple[str, bool]:
        """Process output for vibe, truncating if necessary."""
        output_type = self.detect_output_type(output)

        if output_type == "json":
            return self.process_json(output)
        elif output_type == "yaml":
            sections = self.extract_yaml_sections(output)

            # Check if we need to truncate
            if len(output) > self.max_chars // 2:  # More aggressive threshold
                # Use a smaller threshold for each section
                section_count = max(1, len(sections))  # Ensure we don't divide by zero
                section_threshold = max(
                    50, self.max_chars // (4 * section_count)
                )  # More aggressive

                # Start with status truncation
                sections = self.truncate_yaml_status(sections)

                # Truncate other sections too
                truncated = False
                result_yaml = ""
                for key, value in sections.items():
                    if len(value) > section_threshold:
                        truncated = True
                        value = self.truncate_string(value, section_threshold)

                    result_yaml += f"{key}:\n{textwrap.indent(value, '  ')}\n\n"

                return result_yaml.strip(), truncated

            # No truncation needed
            result_yaml = ""
            for key, value in sections.items():
                result_yaml += f"{key}:\n{textwrap.indent(value, '  ')}\n\n"

            return result_yaml.strip(), False

        # Default to log processing
        return self.process_logs(output)

    def truncate_string(self, text: str, max_length: int) -> str:
        """Truncate a string to a maximum length, preserving start and end.

        Args:
            text: The string to truncate
            max_length: Maximum length of the result

        Returns:
            Truncated string that keeps content from beginning and end
        """
        if len(text) <= max_length:
            return text

        # Keep half from beginning and half from end
        half_length = (max_length - 5) // 2  # 5 chars for "..."
        return f"{text[:half_length]}...\n{text[-half_length:]}"

    def _find_max_depth(self, obj: Any, current_depth: int = 0) -> int:
        """Find the maximum depth of a nested data structure."""
        if isinstance(obj, dict):
            if not obj:  # empty dict
                return current_depth
            return max(
                self._find_max_depth(value, current_depth + 1) for value in obj.values()
            )
        elif isinstance(obj, list):
            if not obj:  # empty list
                return current_depth
            return max(
                (self._find_max_depth(item, current_depth + 1) for item in obj),
                default=current_depth,
            )
        else:
            return current_depth

    def process_yaml(self, output: str) -> tuple[str, bool]:
        """Process YAML output.

        Args:
            output: YAML output to process

        Returns:
            Tuple of (processed output, whether truncation occurred)
        """
        # For YAML, we need to handle sections and truncation
        sections = self.extract_yaml_sections(output)

        # Check if we need to truncate
        if len(output) > self.max_chars:
            # Use a smaller threshold for each section
            section_count = max(1, len(sections))  # Ensure we don't divide by zero
            section_threshold = max(100, self.max_chars // (2 * section_count))

            # Truncate status section first
            sections = self.truncate_yaml_status(sections)

            # If there are still too many sections, truncate more
            truncated = False
            result_yaml = ""
            for key, value in sections.items():
                if len(value) > section_threshold:
                    truncated = True
                    if key == "status":
                        # Status sections can be heavily truncated
                        lines = value.split("\n")
                        if len(lines) > 10:
                            value = (
                                "\n".join(lines[:5]) + "\n...\n" + "\n".join(lines[-5:])
                            )
                    else:
                        # Other sections use standard truncation
                        value = self.truncate_string(value, section_threshold)

                result_yaml += f"{key}:\n{textwrap.indent(value, '  ')}\n\n"

            return result_yaml.strip(), truncated

        # No truncation needed
        result_yaml = ""
        for key, value in sections.items():
            result_yaml += f"{key}:\n{textwrap.indent(value, '  ')}\n\n"

        return result_yaml.strip(), False


# Create global instance for easy import
output_processor = OutputProcessor()
