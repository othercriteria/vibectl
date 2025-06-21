# New test file to increase coverage for llm_interface and adapter helpers

from unittest.mock import patch

import pytest

from vibectl.config import Config
from vibectl.llm_interface import is_valid_llm_model_name
from vibectl.model_adapter import LLMModelAdapter


@pytest.mark.parametrize(
    "side_effect, expected_ok",
    [
        (ValueError("Unknown model foobar"), False),  # triggers unknown-model branch
        (RuntimeError("connection error"), True),  # non-name error branch
    ],
)
def test_is_valid_llm_model_name_branches(
    side_effect: Exception, expected_ok: bool
) -> None:
    """Ensure the helper correctly distinguishes name errors from other errors."""
    with patch("vibectl.llm_interface.llm.get_model", side_effect=side_effect):
        ok, _msg = is_valid_llm_model_name("dummy-model")
        assert ok is expected_ok


def test_adapter_key_message_helpers() -> None:
    """Verify the API-key helper message formatters return informative text."""
    adapter = LLMModelAdapter(config=Config())

    error_msg = adapter._format_api_key_message(
        provider="openai", model_name="gpt-3.5-turbo", is_error=True
    )
    assert "OPENAI_API_KEY" in error_msg
    assert "Failed to get model" in error_msg

    warn_msg = adapter._format_key_validation_message("anthropic")
    assert "Anthropic" in warn_msg
