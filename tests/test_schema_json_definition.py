from vibectl.prompts.schemas import _SCHEMA_DEFINITION_JSON


def test_schema_definition_includes_presentation_hints() -> None:
    """Shared JSON schema string must mention presentation_hints field."""

    assert "presentation_hints" in _SCHEMA_DEFINITION_JSON
