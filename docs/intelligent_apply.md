# Intelligent Manifest Application with `vibectl apply vibe`

The `vibectl apply vibe "<user_input_string>"` command intelligently processes your request to apply Kubernetes manifests. It aims to understand your intent, work with various file inputs, and even attempt to correct or generate manifests based on your input and the context of other provided files.

## Core Workflow

1. **Understanding Your Request (LLM-Powered):**
    * `vibectl` first uses an AI model to interpret your input string.
    * It identifies the files, directories, or glob patterns you intend to apply (e.g., `my-app.yaml`, `./manifests/`, `*-deployment.yaml`).
    * It also extracts any additional instructions or context from your request (e.g., "apply these to the staging namespace", "use server-side apply").

2. **Discovering and Validating Files (Local):**
    * The tool locates all specified files based on your input.
    * Each discovered file is validated:
        * Basic YAML/JSON syntax is checked.
        * `kubectl apply --dry-run=server` is used to ensure Kubernetes can understand it as a valid manifest.

3. **Building Context and Summarizing (LLM-Powered):**
    * For each valid manifest, the AI generates a concise summary.
    * These summaries build an "operational memory" that helps the AI understand the overall state of what\'s being applied. This context is crucial for accurately correcting other files or planning the final apply operation.

4. **Correcting and Generating Manifests (LLM-Powered):**
    * If any of your specified files are not valid Kubernetes manifests (e.g., they have syntax errors, are plain text descriptions hinting at a manifest\'s purpose, or are empty but the filename suggests an intent):
        * The AI attempts to correct the existing content into a valid Kubernetes manifest.
        * Alternatively, if correction isn\'t feasible (e.g., the file is unreadable or the content is entirely unrelated), it tries to generate a new manifest. This generation is based on the file path, any readable content, the overall user request, and the context from other valid manifests.
        * Successfully corrected or generated manifests are saved to temporary files. These new manifests are also summarized to update the operational memory, ensuring the AI has the most current context.
    * Files that cannot be read or confidently corrected/generated into valid manifests are marked as unresolvable and are not included in the apply operation.

5. **Planning the Final `kubectl apply` (LLM-Powered):**
    * Using all the information gathered:
        * The original valid manifests.
        * The newly corrected or generated temporary manifests.
        * The overall user request (including any flags or specific instructions like target namespace or apply options).
        * The comprehensive operational memory built from all valid/corrected sources.
        * A list of any unresolvable files (for context, though they won\'t be applied).
    * The AI formulates the final `kubectl apply` command(s) needed to achieve your goal. This may involve applying multiple files (originals and temporary ones) and incorporating options like `-n <namespace>`, `--server-side`, `--prune`, etc., based on your initial request and the context.

6. **Execution and Cleanup (Local):**
    * The planned `kubectl apply` command(s) are executed against your Kubernetes cluster.
    * Any temporary files created during the correction or generation steps are automatically cleaned up after the operation.
    * A summary of the operations, including which files were applied as-is, which were corrected (noting original vs. temporary path), and which were unresolvable, is provided through logs and the command\'s final output.

## Key Features & Considerations

* **Flexible Input:** Handles direct file paths, directories, and glob patterns for manifest sources.
* **Intelligent Correction/Generation:** Attempts to fix errors in manifests or generate new ones based on context and user intent, reducing manual effort.
* **Context-Aware Operations:** Builds an understanding of all manifests being applied together to make more informed decisions during correction and planning.
* **Transparency:** Provides logging about its actions, including which files are being processed, corrected, or generated.
* **Validation:** Leverages `kubectl apply --dry-run=server` to ensure manifest validity before attempting to make changes to the cluster.
* **Automation:** Streamlines the process of applying multiple manifests, especially when some may have issues.

## Worked Example

The snippet below shows an actual run of the intelligent apply workflow. The log output is extremely verbose, but the key steps are:

```bash
❯ vibectl config set log_level INFO
❯ k create namespace apply-demo-1
❯ k create namespace apply-demo-2
❯ vibectl memory set ""
❯ vibectl apply vibe "examples/manifests/apply/ into both apply-demo-1 and apply-demo-2 namespaces"
[INFO] Starting intelligent apply workflow...
[INFO] Total files discovered and processed: 6
[INFO] Semantically valid manifests found: 2
[INFO] Invalid/non-manifest sources to correct/generate: 4
[INFO] Total corrected/generated manifests: 3
[INFO] Total unresolvable sources after Step 4: 1
[INFO] Executing planned command 1/2: ... -n apply-demo-1
✨ Vibe check: Deployment and Service Resources
deployment.apps/valid-deployment-1 created
service/valid-service-1 created
...
[INFO] Executing planned command 2/2: ... -n apply-demo-2
```

The operation applies the original valid manifests plus three AI-corrected ones, creating identical resources in both namespaces.

### What changed?

Compared with the files in `examples/manifests/apply/`:

- **`valid_manifest_1.yaml` & `valid_manifest_2.yaml`** were applied unchanged.
- **`natural_language_resource.txt`** → generated a `Deployment` called `nlp-deployment` with 2 replicas and the label `env: production`.
- **`invalid_logic.yaml`** → transformed from an invalid `NonExistentKind` object into a standard `Deployment` (named `invalid-logic-resource`) using the `nginx:latest` image and CPU/memory limits.
- **`invalid_syntax.yaml`** → fixed indentation issues to create the `invalid-syntax-deployment` Deployment.
- **`not_a_resource.txt`** → skipped entirely because it was recognized as license text and not a manifest.

## Future Enhancements (Not Yet Implemented)

* **Interactive Confirmation:** Option for users to review a diff and confirm changes before applying LLM-corrected or generated manifests.
* **Enhanced Kustomize Support:** Deeper integration with Kustomize, especially when manifests are being generated or modified as part of a kustomization.
