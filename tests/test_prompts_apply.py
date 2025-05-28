"""Test apply prompts module."""

from vibectl.config import Config
from vibectl.prompts.apply import (
    apply_output_prompt,
    apply_plan_prompt,
    correct_apply_manifest_prompt_fragments,
    plan_apply_filescope_prompt_fragments,
    plan_final_apply_command_prompt_fragments,
    summarize_apply_manifest_prompt_fragments,
)


def test_apply_plan_prompt_structure() -> None:
    """Test that apply_plan_prompt has the expected structure."""
    result = apply_plan_prompt()
    assert isinstance(result, tuple)
    system_fragments, user_fragments = result

    # Check that we have system and user fragments
    assert system_fragments is not None
    assert user_fragments is not None

    # Convert to text to verify content - Fragment is just a string wrapper
    system_text = "\n".join(system_fragments)
    user_text = "\n".join(user_fragments)

    # Verify apply-specific content
    assert "kubectl apply" in system_text or "kubectl apply" in user_text
    assert "YAML" in system_text or "YAML" in user_text


def test_apply_plan_prompt_with_config() -> None:
    """Test apply_plan_prompt with config parameter."""
    config = Config()
    result = apply_plan_prompt(config=config)
    assert isinstance(result, tuple)

    system_fragments, user_fragments = result
    assert system_fragments is not None
    assert user_fragments is not None


def test_apply_plan_prompt_with_memory() -> None:
    """Test apply_plan_prompt with memory parameter."""
    memory = "Previous apply operations completed successfully"
    result = apply_plan_prompt(current_memory=memory)
    assert isinstance(result, tuple)

    system_fragments, user_fragments = result
    assert system_fragments is not None
    assert user_fragments is not None


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


def test_plan_apply_filescope_prompt_fragments() -> None:
    """Test plan_apply_filescope_prompt_fragments function."""
    request = "apply manifests/ to both staging and production namespaces"

    result = plan_apply_filescope_prompt_fragments(request)
    assert isinstance(result, tuple)

    system_fragments, user_fragments = result
    assert system_fragments is not None
    assert user_fragments is not None

    # Check that the request is included in user fragments
    user_text = "\n".join(user_fragments)
    assert request in user_text

    # Check that system fragments contain relevant instructions
    system_text = "\n".join(system_fragments)
    assert "kubectl apply" in system_text
    assert "file_selectors" in system_text


def test_plan_apply_filescope_prompt_fragments_empty_request() -> None:
    """Test plan_apply_filescope_prompt_fragments with empty request."""
    request = ""

    result = plan_apply_filescope_prompt_fragments(request)
    assert isinstance(result, tuple)

    system_fragments, user_fragments = result
    assert system_fragments is not None
    assert user_fragments is not None


def test_summarize_apply_manifest_prompt_fragments() -> None:
    """Test summarize_apply_manifest_prompt_fragments function."""
    current_memory = "deployment/nginx configured"
    manifest_content = """
apiVersion: v1
kind: Service
metadata:
  name: nginx-service
spec:
  selector:
    app: nginx
  ports:
  - port: 80
    targetPort: 8080
"""

    result = summarize_apply_manifest_prompt_fragments(current_memory, manifest_content)
    assert isinstance(result, tuple)

    system_fragments, user_fragments = result
    assert system_fragments is not None
    assert user_fragments is not None

    # Check that both memory and manifest content are included
    user_text = "\n".join(user_fragments)
    assert current_memory in user_text
    assert "nginx-service" in user_text

    # Check that system fragments contain relevant instructions
    system_text = "\n".join(system_fragments)
    assert "kubectl apply" in system_text
    assert "manifest" in system_text.lower()


def test_summarize_apply_manifest_prompt_fragments_empty_memory() -> None:
    """Test summarize_apply_manifest_prompt_fragments with empty memory."""
    current_memory = ""
    manifest_content = "apiVersion: v1\nkind: Pod\nmetadata:\n  name: test-pod"

    result = summarize_apply_manifest_prompt_fragments(current_memory, manifest_content)
    assert isinstance(result, tuple)

    system_fragments, user_fragments = result
    assert system_fragments is not None
    assert user_fragments is not None


def test_correct_apply_manifest_prompt_fragments() -> None:
    """Test correct_apply_manifest_prompt_fragments function."""
    original_file_path = "deployment.yaml"
    original_file_content = "invalid yaml content"
    error_reason = "YAML syntax error: invalid indentation"
    current_operation_memory = "service/nginx configured"
    remaining_user_request = "apply to staging namespace"

    result = correct_apply_manifest_prompt_fragments(
        original_file_path,
        original_file_content,
        error_reason,
        current_operation_memory,
        remaining_user_request,
    )
    assert isinstance(result, tuple)

    system_fragments, user_fragments = result
    assert system_fragments is not None
    assert user_fragments is not None

    # Check that all parameters are included in user fragments
    user_text = "\n".join(user_fragments)
    assert original_file_path in user_text
    assert original_file_content in user_text
    assert error_reason in user_text
    assert current_operation_memory in user_text
    assert remaining_user_request in user_text

    # Check that system fragments contain correction instructions
    system_text = "\n".join(system_fragments)
    assert "correct" in system_text.lower() or "manifest" in system_text.lower()


def test_correct_apply_manifest_prompt_fragments_no_content() -> None:
    """Test correct_apply_manifest_prompt_fragments with no original content."""
    original_file_path = "new-resource.yaml"
    original_file_content = None
    error_reason = "File not found"
    current_operation_memory = ""
    remaining_user_request = "create a basic pod"

    result = correct_apply_manifest_prompt_fragments(
        original_file_path,
        original_file_content,
        error_reason,
        current_operation_memory,
        remaining_user_request,
    )
    assert isinstance(result, tuple)

    system_fragments, user_fragments = result
    assert system_fragments is not None
    assert user_fragments is not None

    # Check that None content is handled appropriately
    user_text = "\n".join(user_fragments)
    assert "not available" in user_text or "not readable" in user_text


def test_plan_final_apply_command_prompt_fragments() -> None:
    """Test plan_final_apply_command_prompt_fragments function."""
    valid_original_manifest_paths = "deployment.yaml, service.yaml"
    corrected_temp_manifest_paths = "/tmp/corrected_configmap.yaml"
    remaining_user_request = "apply to staging and production namespaces"
    current_operation_memory = "deployment/nginx and service/nginx-svc configured"
    unresolvable_sources = "broken.yaml (could not be corrected)"
    final_plan_schema_json = (
        '{"type": "object", "properties": {"commands": {"type": "array"}}}'
    )

    result = plan_final_apply_command_prompt_fragments(
        valid_original_manifest_paths,
        corrected_temp_manifest_paths,
        remaining_user_request,
        current_operation_memory,
        unresolvable_sources,
        final_plan_schema_json,
    )
    assert isinstance(result, tuple)

    system_fragments, user_fragments = result
    assert system_fragments is not None
    assert user_fragments is not None

    # Check that all parameters are included in user fragments
    user_text = "\n".join(user_fragments)
    assert valid_original_manifest_paths in user_text
    assert corrected_temp_manifest_paths in user_text
    assert remaining_user_request in user_text
    assert current_operation_memory in user_text
    assert unresolvable_sources in user_text

    # Check that system fragments contain planning instructions
    system_text = "\n".join(system_fragments)
    assert "kubectl apply" in system_text
    assert "command" in system_text.lower()


def test_plan_final_apply_command_prompt_fragments_minimal() -> None:
    """Test plan_final_apply_command_prompt_fragments with minimal inputs."""
    result = plan_final_apply_command_prompt_fragments(
        valid_original_manifest_paths="",
        corrected_temp_manifest_paths="",
        remaining_user_request="",
        current_operation_memory="",
        unresolvable_sources="",
        final_plan_schema_json='{"type": "object"}',
    )
    assert isinstance(result, tuple)

    system_fragments, user_fragments = result
    assert system_fragments is not None
    assert user_fragments is not None
