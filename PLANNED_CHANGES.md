# Planned Changes: LLM Optimization

This document outlines the plan for optimizing the usage of the `llm` library within `vibectl`.

## Goals

1.  **Measure Performance:** Establish baseline metrics for token cost, cache utilization, and command latency related to LLM calls.
2.  **Improve Efficiency:** Reduce token consumption, improve caching, and decrease latency where possible.
3.  **Enhance Observability:** Gain better insight into how LLM prompts are constructed and used, specifically tracking fragment usage.
4.  **Increase Reliability:** Identify and fix potential bugs or inconsistencies in prompt construction, memory updates, or state handling related to LLM interactions.

## Approach

1.  **Instrumentation:**
    *   Wrap LLM calls (`model.prompt`, `conversation.prompt`) to record:
        *   Input prompt (potentially broken down by fragments).
        *   System prompt.
        *   Model used.
        *   Options used (e.g., temperature).
        *   `response.usage()` (input/output tokens).
        *   Execution time (latency).
        *   Whether the response came from a cache (if discoverable).
        *   Fragments used (`fragments=`, `system_fragments=`).
    *   Store this data (e.g., logs, temporary SQLite DB) for analysis.

2.  **Adopt Fragments:**
    *   Refactor existing prompt construction logic (`vibectl/prompt.py`) to use the `fragments=` and `system_fragments=` arguments for `model.prompt()` and `conversation.prompt()`.
    *   Break down prompts into logical fragments, ordered from least to most frequently changing to maximize potential caching benefits (e.g., static instructions, custom instructions, user request, memory, dynamic context like time or command output).
    *   Identify static vs. dynamic parts within current prompt templates (`PLAN_*`, `*_prompt` functions).
    *   Modify prompt generation functions to return lists of system and user fragments instead of monolithic strings.
    *   Update the LLM call sites (likely in `vibectl/llm_utils.py` or similar) to pass these fragments correctly to the `llm` library.
    *   Enhance instrumentation to track fragment usage and investigate if cache hit information is available via the `llm.Response` object (e.g., in `response.json()` or `response.usage().details`).

3.  **Analysis & Optimization:**
    *   Analyze the collected data to identify:
        *   High-cost operations (tokens, time).
        *   Frequently used prompts/fragments (cache candidates).
        *   Infrequently used or unexpectedly used fragments (potential bugs).
        *   Latency bottlenecks.
    *   Implement optimizations based on findings:
        *   Refine prompts for conciseness.
        *   Adjust model parameters (e.g., temperature, max tokens).
        *   Explore explicit caching layers if `llm`'s fragment caching isn't sufficient.
        *   Fix bugs in prompt/fragment logic.

4.  **Verification:**
    *   Measure metrics again after optimizations to confirm improvements.
    *   Ensure tests pass and functionality remains correct.

## Tools & Libraries

*   `llm` library (Python API)
*   `pytest` (for testing wrappers/changes)
*   Standard Python `logging` or a simple database for metrics.

## Open Questions

*   How does `llm`'s fragment caching actually work, especially with different models (OpenAI vs. Anthropic)? Does it require specific logging/setup? (Need to investigate `llm` internals or docs further).
*   What's the best way to store/visualize the collected metrics?
*   Is cache hit information directly exposed by the `llm` library's `Response` object, or do we need to infer it (e.g., via token counts or latency)?

## Out of Scope (Initial Phase)

*   Building a complex, persistent caching system beyond what `llm` might offer via fragments.
*   Major refactoring of core command logic unrelated to LLM calls.
