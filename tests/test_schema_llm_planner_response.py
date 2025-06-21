import json

import pytest
from pydantic import ValidationError

from vibectl.schema import CommandAction, LLMPlannerResponse


def test_llm_planner_response_accepts_presentation_hints() -> None:
    """LLMPlannerResponse should round-trip when presentation_hints is provided."""

    cmd_action = CommandAction(commands=["get", "pods", "-n", "app"])
    original = LLMPlannerResponse(
        action=cmd_action,
        presentation_hints="Use bullet points for resource lists.",
    )

    json_str = original.model_dump_json()
    reconstructed = LLMPlannerResponse.model_validate_json(json_str)

    assert reconstructed.presentation_hints == original.presentation_hints
    assert reconstructed.action == original.action


def test_llm_planner_response_rejects_unknown_top_level_key() -> None:
    """Unknown top-level keys must raise a ValidationError (extra = 'forbid')."""

    invalid_json = json.dumps(
        {
            "action": {"action_type": "COMMAND", "commands": ["get", "pods"]},
            "foo": "bar",  # Unexpected key
        }
    )

    with pytest.raises(ValidationError):
        LLMPlannerResponse.model_validate_json(invalid_json)
