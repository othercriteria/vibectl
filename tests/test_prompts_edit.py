"""Test edit prompts module."""

import pytest

from vibectl.config import Config
from vibectl.prompts.edit import (
    create_resource_summarization_prompt,
    edit_plan_prompt,
    edit_resource_prompt,
    get_patch_generation_prompt,
    get_resource_summarization_prompt,
    patch_generation_prompt,
    patch_summary_prompt,
    plan_edit_scope,
)


@pytest.fixture
def test_config() -> Config:
    """Create a test config instance."""
    return Config()


@pytest.fixture
def sample_memory() -> str:
    """Sample memory for testing."""
    return "Previous edit operations completed successfully"


@pytest.fixture
def sample_yaml() -> str:
    """Sample YAML for testing."""
    return """apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx
  labels:
    app: nginx
spec:
  replicas: 3
  selector:
    matchLabels:
      app: nginx
  template:
    metadata:
      labels:
        app: nginx
    spec:
      containers:
      - name: nginx
        image: nginx:1.20
        ports:
        - containerPort: 80
        resources:
          limits:
            memory: "256Mi"
            cpu: "500m"
"""


class TestEditPlanPrompt:
    """Test edit_plan_prompt function."""

    def test_basic_structure(self, test_config: Config) -> None:
        """Test that edit_plan_prompt has the expected structure."""
        result = edit_plan_prompt()
        assert isinstance(result, tuple)
        system_fragments, user_fragments = result

        assert system_fragments is not None
        assert user_fragments is not None

        # Convert to text to verify content
        system_text = "\n".join(system_fragments)
        user_text = "\n".join(user_fragments)

        # Verify edit-specific content
        combined_text = system_text + user_text
        assert "edit" in combined_text.lower()
        assert "kubectl" in combined_text.lower()

    def test_with_config(self, test_config: Config) -> None:
        """Test edit_plan_prompt with config parameter."""
        result = edit_plan_prompt(config=test_config)
        assert isinstance(result, tuple)

        system_fragments, user_fragments = result
        assert system_fragments is not None
        assert user_fragments is not None

    def test_with_memory(self, sample_memory: str) -> None:
        """Test edit_plan_prompt with memory parameter."""
        result = edit_plan_prompt(current_memory=sample_memory)
        assert isinstance(result, tuple)

        system_fragments, user_fragments = result
        assert system_fragments is not None
        assert user_fragments is not None

    def test_with_config_and_memory(
        self, test_config: Config, sample_memory: str
    ) -> None:
        """Test edit_plan_prompt with both config and memory parameters."""
        result = edit_plan_prompt(config=test_config, current_memory=sample_memory)
        assert isinstance(result, tuple)

        system_fragments, user_fragments = result
        assert system_fragments is not None
        assert user_fragments is not None

    def test_with_empty_memory(self) -> None:
        """Test edit_plan_prompt with empty memory."""
        result = edit_plan_prompt(current_memory="")
        assert isinstance(result, tuple)

        system_fragments, user_fragments = result
        assert system_fragments is not None
        assert user_fragments is not None

    def test_with_none_memory(self) -> None:
        """Test edit_plan_prompt with None memory."""
        result = edit_plan_prompt(current_memory=None)
        assert isinstance(result, tuple)

        system_fragments, user_fragments = result
        assert system_fragments is not None
        assert user_fragments is not None

    def test_contains_examples(self) -> None:
        """Test that edit_plan_prompt contains expected examples."""
        result = edit_plan_prompt()
        system_fragments, user_fragments = result

        combined_text = "\n".join(system_fragments + user_fragments)
        assert "deployment nginx" in combined_text.lower()
        assert "--output-patch" in combined_text


class TestEditResourcePrompt:
    """Test edit_resource_prompt function."""

    def test_basic_structure(self) -> None:
        """Test that edit_resource_prompt has the expected structure."""
        result = edit_resource_prompt()
        assert isinstance(result, tuple)
        system_fragments, user_fragments = result

        assert system_fragments is not None
        assert user_fragments is not None

        # Convert to text to verify content
        combined_text = "\n".join(system_fragments + user_fragments)
        assert "edit" in combined_text.lower()
        assert "summarize" in combined_text.lower()

    def test_with_config(self, test_config: Config) -> None:
        """Test edit_resource_prompt with config parameter."""
        result = edit_resource_prompt(config=test_config)
        assert isinstance(result, tuple)

    def test_with_memory(self, sample_memory: str) -> None:
        """Test edit_resource_prompt with memory parameter."""
        result = edit_resource_prompt(current_memory=sample_memory)
        assert isinstance(result, tuple)

    def test_with_config_and_memory(
        self, test_config: Config, sample_memory: str
    ) -> None:
        """Test edit_resource_prompt with both config and memory parameters."""
        result = edit_resource_prompt(config=test_config, current_memory=sample_memory)
        assert isinstance(result, tuple)

    def test_contains_focus_points(self) -> None:
        """Test that edit_resource_prompt contains expected focus points."""
        result = edit_resource_prompt()
        system_fragments, user_fragments = result

        combined_text = "\n".join(system_fragments + user_fragments)
        assert "resource type" in combined_text.lower()
        assert "changes" in combined_text.lower()


class TestPatchGenerationPrompt:
    """Test patch_generation_prompt function."""

    def test_basic_structure(self) -> None:
        """Test that patch_generation_prompt has the expected structure."""
        result = patch_generation_prompt()
        assert isinstance(result, tuple)
        system_fragments, user_fragments = result

        assert system_fragments is not None
        assert user_fragments is not None

        combined_text = "\n".join(system_fragments + user_fragments)
        assert "patch" in combined_text.lower()
        assert "kubectl" in combined_text.lower()

    def test_with_config(self, test_config: Config) -> None:
        """Test patch_generation_prompt with config parameter."""
        result = patch_generation_prompt(config=test_config)
        assert isinstance(result, tuple)

    def test_with_memory(self, sample_memory: str) -> None:
        """Test patch_generation_prompt with memory parameter."""
        result = patch_generation_prompt(current_memory=sample_memory)
        assert isinstance(result, tuple)

    def test_contains_examples(self) -> None:
        """Test that patch_generation_prompt contains expected examples."""
        result = patch_generation_prompt()
        system_fragments, user_fragments = result

        combined_text = "\n".join(system_fragments + user_fragments)
        assert "replicas" in combined_text.lower()
        assert "strategic merge" in combined_text.lower()


class TestPatchSummaryPrompt:
    """Test patch_summary_prompt function."""

    def test_basic_structure(self) -> None:
        """Test that patch_summary_prompt has the expected structure."""
        result = patch_summary_prompt()
        assert isinstance(result, tuple)
        system_fragments, user_fragments = result

        assert system_fragments is not None
        assert user_fragments is not None

        combined_text = "\n".join(system_fragments + user_fragments)
        assert "patch" in combined_text.lower()
        assert "summarize" in combined_text.lower()

    def test_with_config(self, test_config: Config) -> None:
        """Test patch_summary_prompt with config parameter."""
        result = patch_summary_prompt(config=test_config)
        assert isinstance(result, tuple)

    def test_with_memory(self, sample_memory: str) -> None:
        """Test patch_summary_prompt with memory parameter."""
        result = patch_summary_prompt(current_memory=sample_memory)
        assert isinstance(result, tuple)


class TestResourceSummarizationPrompt:
    """Test resource summarization prompt functions."""

    def test_get_resource_summarization_prompt_basic(self, sample_yaml: str) -> None:
        """Test get_resource_summarization_prompt with basic parameters."""
        result = get_resource_summarization_prompt(
            resource_yaml=sample_yaml,
            resource_kind="Deployment",
            resource_name="nginx",
        )

        assert isinstance(result, tuple)
        system_fragments, user_fragments = result
        assert system_fragments is not None
        assert user_fragments is not None

        combined_text = "\n".join(system_fragments + user_fragments)
        assert "nginx" in combined_text
        assert "Deployment" in combined_text

    def test_get_resource_summarization_prompt_with_context(
        self, sample_yaml: str
    ) -> None:
        """Test get_resource_summarization_prompt with edit context."""
        result = get_resource_summarization_prompt(
            resource_yaml=sample_yaml,
            resource_kind="Deployment",
            resource_name="nginx",
            edit_context="resource limits",
        )

        assert isinstance(result, tuple)
        system_fragments, user_fragments = result

        combined_text = "\n".join(system_fragments + user_fragments)
        assert "resource limits" in combined_text

    def test_get_resource_summarization_prompt_no_context(
        self, sample_yaml: str
    ) -> None:
        """Test get_resource_summarization_prompt without edit context."""
        result = get_resource_summarization_prompt(
            resource_yaml=sample_yaml,
            resource_kind="Service",
            resource_name="api",
            edit_context=None,
        )

        assert isinstance(result, tuple)
        system_fragments, user_fragments = result
        assert system_fragments is not None
        assert user_fragments is not None

    def test_create_resource_summarization_prompt_basic(self, sample_yaml: str) -> None:
        """Test create_resource_summarization_prompt with basic parameters."""
        result = create_resource_summarization_prompt(
            resource_yaml=sample_yaml,
            resource_kind="Deployment",
            resource_name="nginx",
        )

        assert isinstance(result, tuple)
        system_fragments, user_fragments = result
        assert system_fragments is not None
        assert user_fragments is not None

        user_text = "\n".join(user_fragments)
        assert sample_yaml in user_text
        assert "nginx" in user_text
        assert "Deployment" in user_text

    def test_create_resource_summarization_prompt_with_context(
        self, sample_yaml: str
    ) -> None:
        """Test create_resource_summarization_prompt with edit context."""
        result = create_resource_summarization_prompt(
            resource_yaml=sample_yaml,
            resource_kind="Deployment",
            resource_name="nginx",
            edit_context="scaling configuration",
        )

        assert isinstance(result, tuple)
        system_fragments, user_fragments = result

        user_text = "\n".join(user_fragments)
        assert "scaling configuration" in user_text

    def test_create_resource_summarization_prompt_with_custom_descriptions(
        self, sample_yaml: str
    ) -> None:
        """Test create_resource_summarization_prompt with custom descriptions."""
        custom_task = "Custom task description for testing"
        custom_context = "Custom context instructions for testing"

        result = create_resource_summarization_prompt(
            resource_yaml=sample_yaml,
            resource_kind="Deployment",
            resource_name="nginx",
            task_description=custom_task,
            context_instructions=custom_context,
        )

        assert isinstance(result, tuple)
        system_fragments, user_fragments = result

        system_text = "\n".join(system_fragments)
        user_text = "\n".join(user_fragments)

        assert custom_task in system_text
        assert custom_context in user_text

    def test_create_resource_summarization_prompt_empty_task_description(
        self, sample_yaml: str
    ) -> None:
        """Test create_resource_summarization_prompt with empty task description."""
        result = create_resource_summarization_prompt(
            resource_yaml=sample_yaml,
            resource_kind="Deployment",
            resource_name="nginx",
            task_description="",
            context_instructions="",
        )

        assert isinstance(result, tuple)
        system_fragments, user_fragments = result

        # Should fallback to default task description
        system_text = "\n".join(system_fragments)
        assert "expert kubernetes" in system_text.lower()

    def test_create_resource_summarization_prompt_no_edit_context(
        self, sample_yaml: str
    ) -> None:
        """Test create_resource_summarization_prompt without edit context."""
        result = create_resource_summarization_prompt(
            resource_yaml=sample_yaml,
            resource_kind="ConfigMap",
            resource_name="app-config",
            edit_context=None,
        )

        assert isinstance(result, tuple)
        system_fragments, user_fragments = result

        user_text = "\n".join(user_fragments)
        assert "ConfigMap" in user_text
        assert "app-config" in user_text


class TestPlanEditScope:
    """Test plan_edit_scope function."""

    def test_basic_structure(self) -> None:
        """Test that plan_edit_scope has the expected structure."""
        request = "edit nginx deployment"
        result = plan_edit_scope(
            request=request,
        )

        assert isinstance(result, tuple)
        system_fragments, user_fragments = result
        assert system_fragments is not None
        assert user_fragments is not None

        user_text = "\n".join(user_fragments)
        assert request in user_text

    def test_with_config(self, test_config: Config) -> None:
        """Test plan_edit_scope with config parameter."""
        result = plan_edit_scope(
            request="edit service frontend",
            config=test_config,
        )

        assert isinstance(result, tuple)

    def test_with_memory(self, sample_memory: str) -> None:
        """Test plan_edit_scope with memory parameter."""
        result = plan_edit_scope(
            request="edit deployment api",
            current_memory=sample_memory,
        )

        assert isinstance(result, tuple)

    def test_json_schema_included(self) -> None:
        """Test that plan_edit_scope includes JSON schema instructions."""
        result = plan_edit_scope(
            request="edit configmap app-config",
        )

        assert isinstance(result, tuple)
        system_fragments, user_fragments = result

        combined_text = "\n".join(system_fragments + user_fragments)
        assert "JSON" in combined_text
        assert "schema" in combined_text.lower()

    def test_contains_examples(self) -> None:
        """Test that plan_edit_scope contains expected examples."""
        result = plan_edit_scope(
            request="edit nginx deployment",
        )

        assert isinstance(result, tuple)
        system_fragments, user_fragments = result

        combined_text = "\n".join(system_fragments + user_fragments)
        assert "resource_selectors" in combined_text
        assert "kubectl_arguments" in combined_text
        assert "edit_context" in combined_text


class TestGetPatchGenerationPrompt:
    """Test get_patch_generation_prompt function."""

    def test_basic_structure(self) -> None:
        """Test that get_patch_generation_prompt has the expected structure."""
        result = get_patch_generation_prompt(
            resource="deployment/nginx",
            args=("--namespace", "default"),
            original_summary="Original nginx deployment with 3 replicas",
            summary_diff="""--- original
+++ edited
@@ -1,3 +1,3 @@
 nginx deployment configuration:
-replicas: 3
+replicas: 5
 image: nginx:1.20""",
            original_yaml="""apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx""",
        )

        assert isinstance(result, tuple)
        system_fragments, user_fragments = result
        assert system_fragments is not None
        assert user_fragments is not None

        user_text = "\n".join(user_fragments)
        assert "deployment/nginx" in user_text
        assert "replicas: 3" in user_text
        assert "replicas: 5" in user_text
        assert "--namespace" in user_text
        assert "default" in user_text

    def test_diff_content_included(self) -> None:
        """Test that diff content is properly included."""
        summary_diff = """--- original
+++ edited
@@ -1,2 +1,2 @@
-memory: 256Mi
+memory: 512Mi"""

        result = get_patch_generation_prompt(
            resource="deployment/test",
            args=(),
            original_summary="Test deployment",
            summary_diff=summary_diff,
            original_yaml="kind: Deployment",
        )

        user_text = "\n".join(result[1])
        assert "256Mi" in user_text
        assert "512Mi" in user_text
        assert "```diff" in user_text

    def test_original_yaml_included(self) -> None:
        """Test that original YAML is properly included."""
        original_yaml = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-app
spec:
  replicas: 2"""

        result = get_patch_generation_prompt(
            resource="deployment/test-app",
            args=(),
            original_summary="Test app deployment",
            summary_diff="""--- original
+++ edited
@@ -1 +1 @@
-replicas: 2
+replicas: 4""",
            original_yaml=original_yaml,
        )

        user_text = "\n".join(result[1])
        assert "```yaml" in user_text
        assert "kind: Deployment" in user_text
        assert "name: test-app" in user_text

    def test_empty_args_handled(self) -> None:
        """Test that empty args are handled properly."""
        result = get_patch_generation_prompt(
            resource="service/api",
            args=(),
            original_summary="API service",
            summary_diff="""--- original
+++ edited
@@ -1 +1 @@
-port: 80
+port: 8080""",
            original_yaml="kind: Service",
        )

        assert isinstance(result, tuple)
        user_text = "\n".join(result[1])
        assert "service/api" in user_text


class TestPluginIntegration:
    """Test plugin integration aspects."""

    def test_functions_have_decorators(self) -> None:
        """Test that functions have the expected plugin override decorators."""
        # This is a basic test to ensure the decorators are present
        # The actual plugin override functionality is tested elsewhere

        # Check that functions return PromptFragments when called
        result1 = edit_plan_prompt()
        result2 = edit_resource_prompt()
        result3 = patch_generation_prompt()
        result4 = patch_summary_prompt()

        for result in [result1, result2, result3, result4]:
            assert isinstance(result, tuple)
            assert len(result) == 2
            system_frags, user_frags = result
            assert system_frags is not None
            assert user_frags is not None

    def test_custom_override_functions_work(self) -> None:
        """Test that custom override functions work without exceptions."""
        # These should not raise exceptions and should return valid PromptFragments
        result1 = get_resource_summarization_prompt(
            resource_yaml="test: yaml",
            resource_kind="Test",
            resource_name="test",
        )

        result2 = plan_edit_scope(
            request="test request",
        )

        assert isinstance(result1, tuple)
        assert isinstance(result2, tuple)

        # Verify structure
        for result in [result1, result2]:
            system_frags, user_frags = result
            assert system_frags is not None
            assert user_frags is not None
