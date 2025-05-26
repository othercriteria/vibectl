"""Test apply prompts module."""

from vibectl.config import Config
from vibectl.prompts.apply import PLAN_APPLY_PROMPT, apply_output_prompt


def test_plan_apply_prompt_structure() -> None:
    """Test that PLAN_APPLY_PROMPT has the expected structure."""
    assert isinstance(PLAN_APPLY_PROMPT, tuple)
    system_fragments, user_fragments = PLAN_APPLY_PROMPT

    # Check that we have system and user fragments
    assert system_fragments is not None
    assert user_fragments is not None

    # Convert to text to verify content - Fragment is just a string wrapper
    system_text = "\n".join(system_fragments)
    user_text = "\n".join(user_fragments)

    # Verify apply-specific content
    assert "kubectl apply" in system_text or "kubectl apply" in user_text
    assert "YAML" in system_text or "YAML" in user_text


def test_apply_output_prompt_with_defaults() -> None:
    """Test apply_output_prompt with default parameters."""
    result = apply_output_prompt()
    assert isinstance(result, tuple)

    system_fragments, user_fragments = result
    assert system_fragments is not None
    assert user_fragments is not None


def test_apply_output_prompt_with_config() -> None:
    """Test apply_output_prompt with config parameter."""
    config = Config()
    result = apply_output_prompt(config=config)
    assert isinstance(result, tuple)


def test_apply_output_prompt_with_memory() -> None:
    """Test apply_output_prompt with memory parameter."""
    memory = "Previous apply operations completed successfully"
    result = apply_output_prompt(current_memory=memory)
    assert isinstance(result, tuple)


def test_apply_output_prompt_with_config_and_memory() -> None:
    """Test apply_output_prompt with both config and memory parameters."""
    config = Config()
    memory = "Previous apply operations completed successfully"
    result = apply_output_prompt(config=config, current_memory=memory)
    assert isinstance(result, tuple)

    # Verify the prompt contains apply-specific content
    system_fragments, user_fragments = result
    all_text = "\n".join(system_fragments + user_fragments)
    assert "apply" in all_text.lower()
