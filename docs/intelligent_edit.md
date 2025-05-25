# Intelligent Resource Editing with `vibectl edit vibe`

The `vibectl edit vibe "<user_input_string>"` command provides an intelligent, natural language-driven approach to editing Kubernetes resources. Instead of manually navigating YAML structures, you can describe what you want to change, and the system will interpret your intent, present the resource in natural language, and apply your edits back to the cluster.

## Core Workflow

1. **Understanding Your Request (LLM-Powered):**
   * `vibectl` uses an AI model to interpret your natural language input.
   * It identifies the target resource(s) you want to edit (e.g., `nginx-demo deployment`, `my-service in production namespace`).
   * It extracts the editing context or intent from your request (e.g., "health and readiness checks", "update resource limits", "change image version").

2. **Resource Discovery and Fetching (Local):**
   * The system locates the specified resource using `kubectl get` with appropriate selectors.
   * The current resource configuration is fetched in YAML format for processing.
   * Resource validation ensures the target exists and is accessible.

3. **Natural Language Summarization (LLM-Powered):**
   * The raw YAML configuration is transformed into a concise, human-readable summary.
   * This summary focuses on the most relevant aspects of the resource configuration.
   * Technical YAML details are abstracted into natural language descriptions that are easier to understand and edit.

4. **Interactive Editing (User + LLM-Powered):**
   * The natural language summary is presented in your default editor (following `click.edit()` patterns).
   * You edit the summary using plain English to describe your desired changes.
   * The system detects differences between the original and edited summaries.

5. **Intelligent Patch Generation (LLM-Powered):**
   * The AI analyzes the changes you made to the natural language summary.
   * It generates the appropriate Kubernetes patch operations (strategic merge patch format).
   * The patch is designed to achieve your intended changes while preserving existing configuration.

6. **Patch Application and Verification (Local):**
   * The generated patch is applied using `kubectl patch` against your cluster.
   * The system provides detailed feedback about what was changed.
   * Memory is updated with the operation context for future reference.

7. **Result Summary and Memory Update (LLM-Powered):**
   * A comprehensive summary of the applied changes is generated and displayed.
   * The operation context is stored in the system's working memory for continuity across commands.

## Key Features & Considerations

* **Natural Language Interface:** Edit resources using plain English descriptions rather than raw YAML manipulation.
* **Context-Aware Processing:** The system understands editing intent and focuses on relevant aspects of the resource.
* **Safe Patch Generation:** Uses strategic merge patches to make precise changes without disrupting unrelated configuration.
* **Interactive Workflow:** Leverages your preferred editor for a familiar editing experience.
* **Comprehensive Feedback:** Provides detailed information about what was changed and the current resource state.
* **Memory Integration:** Maintains context about operations for improved continuity across multiple commands.
* **Validation and Safety:** Validates patches before application and provides rollback information.

## Worked Example

The following demonstrates the complete intelligent edit workflow for updating health check configuration on a deployment. The example shows how the system interprets the request, fetches the resource, presents it for editing, and applies the changes.

**Command:** `vibectl edit vibe health and rediness checks for nginx-demo deployment`

**Execution Flow:**

1. **Request Analysis:**
   ```
   [INFO] Planning edit operation: health and rediness checks for nginx-demo deployment
   [INFO] LLM Resource Selectors: ['deployment/nginx-demo']
   [INFO] LLM Kubectl Arguments: ['-n', 'sandbox']
   [INFO] LLM Edit Context: health and readiness checks configuration
   ```

2. **Resource Fetching:**
   ```
   [INFO] Fetching current resource configuration
   [INFO] Running kubectl command: kubectl get deployment/nginx-demo -n sandbox -o yaml
   ```

3. **Natural Language Summarization:**
   ```
   [INFO] Summarizing resource to natural language
   📊 Metrics: Source: LLM Resource Summarization | Latency: 6209.09 ms | Tokens: 1037 in, 321 out
   ```
   The system converts the YAML into a readable summary focusing on current configuration, health checks, resource limits, and other relevant settings.

4. **Interactive Editing:**
   ```
   [INFO] Opening editor for user to make changes
   [INFO] Generating diff between original and edited summaries
   ```
   The user modifies the natural language summary to specify desired changes (e.g., "increase readiness probe failure threshold to 5").

5. **Patch Generation:**
   ```
   [INFO] Generating patch from summary changes
   📊 Metrics: Source: LLM Patch Generation | Latency: 4689.59 ms | Tokens: 5876 in, 194 out
   ```
   The AI converts the summary changes into a strategic merge patch:
   ```json
   {
     "spec": {
       "replicas": 5,
       "template": {
         "spec": {
           "containers": [
             {
               "name": "nginx",
               "readinessProbe": {
                 "failureThreshold": 5
               }
             }
           ]
         }
       }
     }
   }
   ```

6. **Patch Application:**
   ```
   [INFO] Applying generated patch
   [INFO] Executing kubectl patch: patch deployment/nginx-demo -n sandbox -p {...}
   ```

7. **Result Summary:**
   ```
   ╭──────────────────────────────────────────────────── ✨ Vibe ─────────────────────────────────────────────────────╮
   │ 🚀 deployment/nginx-demo in namespace sandbox successfully patched ✅                                            │
   │                                                                                                                  │
   │ 📊 Changes applied:                                                                                              │
   │ - Replicas: ⬆️ Increased to 5                                                                                     │
   │ - Readiness probe: ⚙️ Modified failureThreshold to 5                                                              │
   │                                                                                                                  │
   │ 🕒 Deployment created on 2025-05-04, last updated 2025-05-25                                                     │
   │                                                                                                                  │
   │ 📝 Current status:                                                                                               │
   │ - Available replicas: 3/5 🔄                                                                                     │
   │ - Ready replicas: 3/5 🔄                                                                                         │
   │ - Rolling update strategy: maxSurge 20%, maxUnavailable 20% 📈                                                   │
   │                                                                                                                  │
   │ ⚠️ Note: Deployment shows generation 82 but status observed generation 81, indicating update still in progress 🔄 │
   │                                                                                                                  │
   │ 🔍 Additional configuration:                                                                                     │
   │ - Resources: Requests 500m CPU, 512Mi memory; Limits 1 CPU, 1Gi memory 💪                                        │
   │ - Probes: Both liveness and readiness configured with HTTP checks ✨                                             │
   │ - Volume: ConfigMap "k8s-jokes" mounted at /usr/share/nginx/html 📂                                              │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
   ```

8. **Memory Update:**
   The operation context is preserved for future reference:
   ```
   ╭────────────────────────────────────────────────────────── Memory Content ──────────────────────────────────────────────────────────╮
   │ Working in 'sandbox' namespace with nginx-demo deployment. Patched to set replicas to 5 and readiness probe failure threshold to   │
   │ 5. Deployment has rolling update strategy (maxSurge/maxUnavailable 20%), with current status showing 3/5 pods ready and available. │
   │ The deployment uses nginx:latest image with HTTP health probes, resource limits (1 CPU/1Gi memory), resource requests (500m        │
   │ CPU/512Mi memory), and mounts configMap "k8s-jokes" as a volume at /usr/share/nginx/html. Update is in progress (generation 82,    │
   │ observed generation 81). Deployment was created on 2025-05-04 and last updated on 2025-05-25.                                      │
   ╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
   ```

### What Changed?

In this example, the user requested changes to "health and readiness checks" for the nginx-demo deployment. The system:

- **Interpreted the intent** as modifying probe configurations
- **Identified the target** as `deployment/nginx-demo` in the `sandbox` namespace
- **Generated appropriate changes** including both readiness probe threshold adjustments and replica scaling
- **Applied precise patches** using strategic merge patch format
- **Provided comprehensive feedback** about the changes and their impact
- **Maintained context** for future operations through memory updates

## Configuration

The intelligent edit feature can be controlled through configuration:

```bash
# Enable/disable intelligent editing (default: true)
vibectl config set intelligent_edit true

# When disabled, falls back to standard kubectl edit behavior
vibectl config set intelligent_edit false
```

When `intelligent_edit` is disabled:
- `vibectl edit <resource>` passes through directly to `kubectl edit`
- `vibectl edit vibe <request>` performs basic vibe processing without the intelligent workflow

## Future Enhancements (Not Yet Implemented)

* **Multi-Resource Editing:** Support for editing multiple related resources in a single operation.
* **Preview Mode:** Option to preview generated patches before applying them to the cluster.
* **Rollback Integration:** Enhanced integration with kubectl rollout for easy reversal of changes.
* **Template-Based Editing:** Support for applying common editing patterns across multiple resources.
* **Diff Visualization:** Rich diff display showing before/after comparisons of both natural language summaries and YAML configurations.
