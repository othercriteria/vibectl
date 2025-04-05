"""
Output processor for vibectl.

Provides utilities for processing command output for LLM input,
handling token limits, and preparing data for AI processing.
"""

import json
import re
from typing import Any, Dict, List, Match, Optional, Tuple, Union, TypeVar, cast

T = TypeVar('T')


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
        
    def process_json(self, json_str: str) -> Tuple[str, bool]:
        """Process JSON output with specialized handling for better structure.
        
        Args:
            json_str: The raw JSON string to process
            
        Returns:
            Tuple containing (processed_json, was_truncated)
        """
        try:
            # First try to parse as JSON
            data = json.loads(json_str)
            
            # For structured JSON, we can do more intelligent truncation
            # This function intelligently trims arrays and nested objects
            truncated_data = self._truncate_json_object(data)
            
            # Convert back to formatted JSON string
            formatted_json = json.dumps(truncated_data, indent=2)
            
            # If it's still too large, apply standard truncation
            return self.process_for_llm(formatted_json)
        except json.JSONDecodeError:
            # If it's not valid JSON, just use standard truncation
            return self.process_for_llm(json_str)
            
    def _truncate_json_object(self, obj: Union[Dict, List, str, int, float, bool, None], 
                              depth: int = 0, max_depth: int = 3) -> Union[Dict, List, str, int, float, bool, None]:
        """Recursively truncate a JSON object to fit token limits.
        
        Args:
            obj: The JSON object to truncate
            depth: Current recursion depth
            max_depth: Maximum depth to traverse before truncating
            
        Returns:
            Truncated JSON object
        """
        # Base case - return primitives as is
        if not isinstance(obj, (dict, list)) or depth > max_depth:
            return obj
            
        # Handle dictionaries
        if isinstance(obj, dict):
            result: Dict[str, Any] = {}
            for i, (key, value) in enumerate(obj.items()):
                # Keep important keys at any level
                is_important = any(k in key.lower() for k in ["name", "id", "status", "error"]) if isinstance(key, str) else False
                
                # Always keep keys with certain names or if we have few items
                if is_important or i < 10 or len(obj) < 20:
                    result[key] = self._truncate_json_object(value, depth + 1, max_depth)
                else:
                    # Once we hit 10 items, summarize the rest
                    result["..."] = f"{len(obj) - 10} more items truncated"
                    break
            return result
            
        # Handle lists
        if isinstance(obj, list):
            # If the list is small, keep it all
            if len(obj) < 10:
                return [self._truncate_json_object(item, depth + 1, max_depth) for item in obj]
                
            # Otherwise keep first and last few items
            first_items = [self._truncate_json_object(item, depth + 1, max_depth) for item in obj[:5]]
            last_items = [self._truncate_json_object(item, depth + 1, max_depth) for item in obj[-3:]]
            summary = [f"...{len(obj) - 8} items truncated..."]
            
            return first_items + summary + last_items
            
        # Should never reach here
        return obj

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
    
    def detect_output_type(self, output: str) -> str:
        """Detect the type of output for specialized processing.
        
        Args:
            output: The raw output string
            
        Returns:
            Output type: 'json', 'yaml', 'logs', or 'text'
        """
        # Try to detect JSON
        output_stripped = output.strip()
        if (output_stripped.startswith('{') and output_stripped.endswith('}')) or \
           (output_stripped.startswith('[') and output_stripped.endswith(']')):
            try:
                json.loads(output_stripped)
                return 'json'
            except json.JSONDecodeError:
                pass
                
        # Check for YAML indicators
        yaml_pattern = r'^(apiVersion:|kind:|metadata:|spec:|status:)'
        if re.search(yaml_pattern, output, re.MULTILINE):
            return 'yaml'
            
        # Check for log patterns (timestamps, log levels)
        log_pattern = r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}'
        if re.search(log_pattern, output, re.MULTILINE):
            return 'logs'
            
        # Default to text
        return 'text'
    
    def process_auto(self, output: str) -> Tuple[str, bool]:
        """Automatically detect output type and process accordingly.
        
        Args:
            output: The raw output to process
            
        Returns:
            Tuple containing (processed_output, was_truncated)
        """
        output_type = self.detect_output_type(output)
        
        if output_type == 'json':
            return self.process_json(output)
        elif output_type == 'logs':
            return self.process_logs(output)
        elif output_type == 'yaml':
            # Use YAML section extraction for YAML
            sections = self.extract_yaml_sections(output)
            if 'status' in sections and len(sections['status']) > 1000:
                # Truncate status section if it's large
                sections['status'] = sections['status'][:500] + "\n...[status truncated]...\n" + sections['status'][-500:]
            processed_yaml = "\n".join(sections.values())
            return self.process_for_llm(processed_yaml)
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
        current_section = "metadata"

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
