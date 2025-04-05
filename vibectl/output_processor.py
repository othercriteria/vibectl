"""
Output processor for vibectl.

Provides utilities for processing command output for LLM input,
handling token limits, and preparing data for AI processing.
"""

from typing import Dict, List, Tuple


class OutputProcessor:
    """Handles processing of command output for LLM input."""

    def __init__(self, max_token_limit: int = 10000, truncation_ratio: int = 3) -> None:
        """Initialize the output processor.

        Args:
            max_token_limit: Maximum number of tokens for LLM input
            truncation_ratio: Ratio for truncating output (beginning:end)
        """
        self.max_token_limit = max_token_limit
        self.truncation_ratio = truncation_ratio

    def process_for_llm(self, output: str) -> Tuple[str, bool]:
        """Process output to ensure it stays within token limits for LLM.

        Args:
            output: The raw output to process

        Returns:
            Tuple containing (processed_output, was_truncated)
        """
        # Check token count for LLM - using simple 4 chars per token approximation
        output_len = len(output)
        token_estimate = output_len / 4
        was_truncated = False

        if token_estimate > self.max_token_limit:
            # Take first and last portions, omitting middle
            chunk_size = int(
                self.max_token_limit / self.truncation_ratio * 4
            )  # Convert back to chars

            truncated_output = (
                f"{output[:chunk_size]}\n"
                f"[...truncated {output_len - 2 * chunk_size} characters...]\n"
                f"{output[-chunk_size:]}"
            )
            was_truncated = True
            return truncated_output, was_truncated

        return output, was_truncated

    def process_logs(self, logs: str) -> Tuple[str, bool]:
        """Process log output with specialized handling for logs format.

        This applies special handling for log outputs which may have
        timestamps, log levels, and other structured data.

        Args:
            logs: The raw log output to process

        Returns:
            Tuple containing (processed_logs, was_truncated)
        """
        # For logs, we want to preserve the most recent entries if truncation is needed
        # So we reverse the truncation ratio to favor recent logs
        original_ratio = self.truncation_ratio
        self.truncation_ratio = 5  # Favor recent logs more heavily
        output, was_truncated = self.process_for_llm(logs)
        self.truncation_ratio = original_ratio
        return output, was_truncated

    def format_kubernetes_resource(self, resource_type: str, resource_name: str) -> str:
        """Format a Kubernetes resource reference for prompts.

        Args:
            resource_type: The type of resource (pod, deployment, etc.)
            resource_name: The name of the resource

        Returns:
            Formatted string describing the resource
        """
        # Normalize resource type
        resource_type = resource_type.lower()
        # Make plural if singular
        if not resource_type.endswith("s"):
            if resource_type.endswith("y"):
                resource_type = resource_type[:-1] + "ies"
            else:
                resource_type = resource_type + "s"

        return f"{resource_type}/{resource_name}"

    @staticmethod
    def extract_yaml_sections(yaml_output: str) -> Dict[str, str]:
        """Extract and categorize sections from YAML output.

        Args:
            yaml_output: Raw YAML output from kubectl

        Returns:
            Dictionary of categorized sections
        """
        sections: Dict[str, List[str]] = {}
        current_section = "metadata"
        # Variable not used, removing it

        for line in yaml_output.split("\n"):
            if line.startswith("apiVersion:") or line.startswith("kind:"):
                current_section = "header"
                if current_section not in sections:
                    sections[current_section] = []
                sections[current_section].append(line)
            elif line.startswith("metadata:"):
                current_section = "metadata"
                if current_section not in sections:
                    sections[current_section] = []
                sections[current_section].append(line)
            elif line.startswith("spec:"):
                current_section = "spec"
                if current_section not in sections:
                    sections[current_section] = []
                sections[current_section].append(line)
            elif line.startswith("status:"):
                current_section = "status"
                if current_section not in sections:
                    sections[current_section] = []
                sections[current_section].append(line)
            else:
                if current_section not in sections:
                    sections[current_section] = []
                sections[current_section].append(line)

        # Convert lists to strings
        result: Dict[str, str] = {}
        for section, lines in sections.items():
            result[section] = "\n".join(lines)

        return result


# Create global instance for easy import
output_processor = OutputProcessor()
