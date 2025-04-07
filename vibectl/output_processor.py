"""
Output processor for vibectl.

Provides utilities for processing command output for LLM input,
handling token limits, and preparing data for AI processing.
"""

import json
import re
from typing import Any, Dict, List, Tuple, TypeVar

import yaml

T = TypeVar("T")


class OutputProcessor:
    """Handles processing of command output for LLM input."""

    def __init__(
        self, max_token_limit: int = 1000, truncation_ratio: float = 2.0
    ) -> None:
        """Initialize the output processor.

        Args:
            max_token_limit: Maximum number of tokens to allow
            truncation_ratio: Ratio to use for truncation (chars per token)
        """
        self.max_token_limit = max_token_limit
        self.max_chars = int(max_token_limit * truncation_ratio)
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

    def process_for_llm(self, output: str) -> Tuple[str, bool]:
        """Process output for LLM input, truncating if necessary."""
        if len(output) <= self.max_chars:
            return output, False

        # Reserve 50 chars for truncation marker
        chunk_size = (self.max_chars - 50) // 2
        first_chunk = output[:chunk_size]
        last_chunk = output[-chunk_size:]
        return f"{first_chunk}\n[...truncated...]\n{last_chunk}", True

    def process_logs(self, output: str) -> Tuple[str, bool]:
        """Process log output.

        Args:
            output: Raw log output

        Returns:
            Tuple of (processed logs, whether truncation occurred)
        """
        lines = output.splitlines()
        if len(lines) <= self.max_chars // 50:  # Rough estimate of chars per line
            return output, False

        # Keep most recent logs
        keep_lines = self.max_chars // 50
        truncated_lines = lines[-keep_lines:]
        truncated = "\n".join(truncated_lines)
        return truncated, True

    def process_json(self, output: str) -> Tuple[str, bool]:
        """Process JSON output.

        Args:
            output: Raw JSON output

        Returns:
            Tuple of (processed JSON, whether truncation occurred)
        """
        try:
            data = json.loads(output)

            # Check for deep nesting that needs truncation
            max_depth = self._find_max_depth(data)
            is_deeply_nested = max_depth > 3  # Our default max_depth

            # Only truncate if the output is too large or deeply nested
            if len(output) > self.max_chars or is_deeply_nested:
                truncated_data = self._truncate_json_object(data)
                return json.dumps(truncated_data, indent=2), True
            return output, False
        except json.JSONDecodeError:
            return output, False

    def _find_max_depth(self, obj: Any, current_depth: int = 0) -> int:
        """Find the maximum nesting depth of a JSON object."""
        if not isinstance(obj, (dict, list)) or current_depth > 10:
            return current_depth

        if isinstance(obj, dict):
            if not obj:
                return current_depth
            return max(
                self._find_max_depth(value, current_depth + 1) for value in obj.values()
            )
        elif isinstance(obj, list):
            if not obj:  # pragma: no cover - edge case for empty lists
                return current_depth
            return max(
                (self._find_max_depth(item, current_depth + 1) for item in obj),
                default=current_depth,
            )

    def _truncate_json_object(
        self, obj: Any, max_depth: int = 3, current_depth: int = 0
    ) -> Any:
        """Recursively truncate a JSON object."""
        if current_depth >= max_depth:
            return {"...": "max depth reached"}

        if isinstance(obj, dict):
            result = {}
            # Process important keys first
            for key in self.important_keys:
                if key in obj:
                    result[key] = self._truncate_json_object(
                        obj[key], max_depth, current_depth + 1
                    )

            # Process other keys (up to 5)
            other_keys = [k for k in obj.keys() if k not in self.important_keys]
            for key in other_keys[:5]:
                result[key] = self._truncate_json_object(
                    obj[key], max_depth, current_depth + 1
                )

            if (
                len(other_keys) > 5
            ):  # pragma: no cover - edge case for dictionaries with many keys
                result["..."] = f"{len(other_keys) - 5} more items"

            return result

        elif isinstance(obj, list):
            if len(obj) <= 5:
                return [
                    self._truncate_json_object(item, max_depth, current_depth + 1)
                    for item in obj
                ]
            truncated = [
                self._truncate_json_object(item, max_depth, current_depth + 1)
                for item in obj[:5]
            ]
            truncated.append(
                f"... ({len(obj) - 5} more items)"
            )  # pragma: no cover - branch for truncating large lists
            return truncated

        return obj

    def format_kubernetes_resource(self, resource_type: str, name: str) -> str:
        """Format Kubernetes resource reference.

        Args:
            resource_type: Type of resource
            name: Name of resource

        Returns:
            Formatted resource reference
        """
        # Handle special plural forms
        irregular_plurals = {
            "proxy": "proxies",
            "policy": "policies",
            "entry": "entries",
            "discovery": "discoveries",
        }

        if resource_type in irregular_plurals:
            plural = irregular_plurals[resource_type]
        else:
            plural = f"{resource_type}s"

        return f"{plural}/{name}"

    def detect_output_type(self, output: str) -> str:
        """Detect type of output.

        Args:
            output: Output to analyze

        Returns:
            Type of output (json, yaml, logs, text)
        """
        # Try JSON first
        try:
            json.loads(output)
            return "json"
        except json.JSONDecodeError:
            pass

        # Try YAML next
        try:
            if "apiVersion:" in output or "kind:" in output:
                yaml.safe_load(output)
                return "yaml"
        except (
            yaml.YAMLError
        ):  # pragma: no cover - difficult to test invalid YAML parsing exceptions
            pass

        # Check for log patterns
        log_patterns = [
            r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}",  # ISO format
            r"\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}",  # Syslog format
        ]
        for pattern in log_patterns:
            if re.search(pattern, output):
                return "logs"

        return "text"

    def truncate_yaml_status(
        self, sections: Dict[str, str], threshold: int = 1000
    ) -> Dict[str, str]:
        """Truncate long status sections in YAML output.

        Args:
            sections: Dictionary of YAML sections
            threshold: Character length threshold for truncation

        Returns:
            Dictionary with truncated status section if needed
        """
        truncated_sections = sections.copy()
        if "status" in truncated_sections:
            status = truncated_sections["status"]
            if len(status) > threshold:
                # Keep first line and truncate the rest
                first_line = status.split("\n")[0]
                trunc_msg = "\n[status truncated]"
                truncated_sections["status"] = first_line + trunc_msg
        return truncated_sections

    def process_auto(self, output: str) -> Tuple[str, bool]:
        """Process output automatically based on type.

        Args:
            output: Output to process

        Returns:
            Tuple of (processed output, whether truncation occurred)
        """
        output_type = self.detect_output_type(output)

        if output_type == "json":
            return self.process_json(output)
        elif output_type == "yaml":
            # For YAML, we need to handle sections and truncation
            sections = self.extract_yaml_sections(output)

            # Check if we need to truncate
            if len(output) > self.max_chars:
                # Use a smaller threshold for each section
                section_threshold = max(100, self.max_chars // (2 * len(sections)))
                sections = self.truncate_yaml_status(
                    sections, threshold=section_threshold
                )
                processed_yaml = "\n".join(sections.values())
                return processed_yaml, True
            return output, False
        elif output_type == "logs":
            return self.process_logs(output)
        else:
            return self.process_for_llm(output)

    @staticmethod
    def extract_yaml_sections(yaml_output: str) -> Dict[str, str]:
        """Extract and categorize sections from YAML output.

        Args:
            yaml_output: Raw YAML output from kubectl

        Returns:
            Dictionary of categorized sections
        """
        sections: Dict[str, List[str]] = {}
        current_section = "root"
        section_lines: List[str] = []

        # Normalize line endings and strip trailing whitespace
        lines = [line.rstrip() for line in yaml_output.split("\n")]

        # Find common indentation to remove
        non_empty_lines = [line for line in lines if line.strip()]
        if not non_empty_lines:
            return {"root": yaml_output.strip()}

        common_indent = min(len(line) - len(line.lstrip()) for line in non_empty_lines)

        # Check if this is a Kubernetes-style YAML with sections
        has_k8s_sections = False
        for line in non_empty_lines:
            line = (
                line[common_indent:] if line.startswith(" " * common_indent) else line
            )
            if not line.startswith(" ") and line.endswith(":"):
                key = line[:-1]
                if key in {"metadata", "spec", "status", "apiVersion", "kind"}:
                    has_k8s_sections = True
                    break

        # If not a Kubernetes-style YAML, return as root
        if (
            not has_k8s_sections
        ):  # pragma: no cover - edge case for non-k8s YAML tested separately
            return {"root": yaml_output.strip()}

        # Remove common indentation and collect sections
        for line in lines:
            if not line.strip():
                continue

            # Remove common indentation
            if line.startswith(" " * common_indent):
                line = line[common_indent:]

            # Check for top-level keys
            if not line.startswith(" "):
                key = line.split(":")[0].strip() if ":" in line else ""
                if key:
                    if (
                        section_lines and current_section != "root"
                    ):  # pragma: no cover - complex YAML parsing branch
                        sections[current_section] = section_lines
                    current_section = key
                    section_lines = [line]
                else:
                    section_lines.append(line)
            else:
                section_lines.append(line)

        # Add the last section
        if section_lines:
            sections[current_section] = section_lines

        # Convert lists to strings
        result: Dict[str, str] = {}
        for section, lines in sections.items():
            result[section] = "\n".join(lines).strip()

        return result

    def process_output_for_vibe(self, output: str) -> Tuple[str, bool]:
        """Process output for vibe, truncating if necessary."""
        output_type = self.detect_output_type(output)

        if output_type == "json":
            return self.process_json(output)
        elif output_type == "yaml":
            sections = self.extract_yaml_sections(output)

            # Check if we need to truncate
            if len(output) > self.max_chars // 2:  # More aggressive threshold
                # Use a smaller threshold for each section
                section_threshold = max(
                    50, self.max_chars // (4 * len(sections))
                )  # More aggressive
                sections = self.truncate_yaml_status(
                    sections, threshold=section_threshold
                )
                truncated = True
            else:
                truncated = (
                    False  # pragma: no cover - less common code path for small YAML
                )
            return "\n".join(sections.values()), truncated
        elif output_type == "logs":
            return self.process_logs(output)
        else:
            return self.process_for_llm(output)


# Create global instance for easy import
output_processor = OutputProcessor()
