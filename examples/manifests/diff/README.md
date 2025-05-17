# Example Manifests for `vibectl diff` Testing

This directory contains a set of Kubernetes manifests designed to test the `vibectl diff` subcommand and potentially other subcommands that involve comparing local configurations with the cluster state.

## Namespace

* `diff-namespace.yaml`: Defines a dedicated namespace `diff-demo-ns` to isolate these test resources.

## Manifest Sets

We have two primary states represented:

1. **Initial State (`diff-initial-state.yaml`)**:
    * A `ConfigMap` named `diff-demo-cm` with some initial data.
    * A `Secret` named `diff-demo-secret` with initial credential data.
    This file is intended to be applied to the cluster first to set up a baseline.

2. **Modified State (`diff-modified-state.yaml`)**:
    * The `ConfigMap` `diff-demo-cm` with some data changed and new data added.
    * The `Secret` `diff-demo-secret` with some credential data changed.
    * A **new** `Secret` named `diff-demo-secret-new`.
    This file represents a local configuration that has diverged from the initial cluster state and is used as the input for `kubectl diff` or `vibectl diff`.

## Usage Workflow

1. **Setup Namespace & Initial State**:

    ```bash
    kubectl apply -f examples/manifests/diff-namespace.yaml
    kubectl apply -f examples/manifests/diff-initial-state.yaml
    ```

2. **Perform Diff**:
    Observe the differences between the local `diff-modified-state.yaml` and the live cluster state.

    ```bash
    kubectl diff -f examples/manifests/diff-modified-state.yaml
    # Expected to be replaced with:
    # vibectl diff -f examples/manifests/diff-modified-state.yaml
    ```

3. **Teardown**:
    Remove the resources and the namespace.

    ```bash
    kubectl delete -f examples/manifests/diff-initial-state.yaml
    kubectl delete -f examples/manifests/diff-modified-state.yaml # To remove the new secret if applied
    kubectl delete -f examples/manifests/diff-namespace.yaml
    ```

    *(Note: `diff-modified-state.yaml` is included in delete if you were to apply it after diffing to see the changes live)*

This setup allows for clear, reproducible demonstrations and tests of diffing logic.
