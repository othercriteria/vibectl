# Planned Changes

## Enhanced Watch/Follow Functionality

- **Goal:** Provide richer, interactive watch/follow capabilities for `vibectl` commands, extending beyond basic `kubectl --watch` or `--follow`.

- **Core Behavior & Supported Commands:**
    - The core idea is to run the underlying `kubectl` command (`--watch` or `--follow`) and pipe its output through a new live display handler based on the `asyncio` and `rich` components from `port-forward`/`wait`.
    - **Commands using `--watch`:**
        - `get`: Intercepts `--watch`. Runs `kubectl get <resource> --watch` and pipes to live display.
        - `events`: Intercepts `--watch`. Runs `kubectl events --watch` and pipes to live display.
    - **Commands using `--follow`:**
        - `logs`: Intercepts `--follow` (or `-f`). Runs `kubectl logs --follow` and pipes output stream to live display.

- **Live Display Handler:**
    - Reuses/adapts `asyncio` and `rich` components.
    - Clearly displays streaming output/status updates.
    - Handles termination gracefully (Ctrl+C). Clarify that this exits the *display* only, not the underlying K8s operation/stream if applicable.

- **Interaction (Initial):**
    - Implement basic graceful exit (Ctrl+C).
    - *Future:* Explore filtering live output (TODO).
    - *Future:* Explore writing live output to a file (TODO).
    - *Future:* Explore pausing/resuming the *display* (TODO).

- **`vibe` Integration (Post-Termination):**
    - For `--watch` commands, the `vibe` summarization runs *after* the user terminates the watch (Ctrl+C).
    - For `logs --follow`, `vibe` summarization likely runs post-termination as well, summarizing the streamed logs.
    - *Future:* Explore triggering `vibe` on-demand during the watch/follow (TODO).

- **Output Format Handling (`get --watch`):**
    - Initially, `vibectl get --watch` will ignore conflicting `--output` flags for the live display, using the default `kubectl watch` stream format.
    - *Future:* Investigate supporting other `--output` formats (TODO).

- **Scope:**
    - Exclude `vibectl just` from enhanced `--watch` behavior initially.
    - Consider future verb expansion (e.g., `cordon`, `top`) as per TODO.

- **Error Handling:**
    - Clearly display errors from the underlying `kubectl` command or the custom watch/poll logic.
