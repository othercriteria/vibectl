"""
JSON schema definitions for prompt responses.

This module contains JSON schema constants that are used across multiple
prompt modules to ensure consistent structured responses from LLM interactions.
"""

import json

from vibectl.schema import EditResourceScopeResponse, LLMPlannerResponse

# Regenerate the shared JSON schema definition string from the Pydantic model
_SCHEMA_DEFINITION_JSON = json.dumps(LLMPlannerResponse.model_json_schema(), indent=2)
_EDIT_RESOURCESCOPE_SCHEMA_JSON = json.dumps(
    EditResourceScopeResponse.model_json_schema(), indent=2
)
