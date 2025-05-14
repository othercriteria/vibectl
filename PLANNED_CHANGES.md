# Planned Changes: LLM Optimization

This document outlines the plan for optimizing the usage of the `llm` library within `vibectl`.

## Goals

1.  **Measure Performance:** Establish baseline metrics for token cost, cache utilization, and command latency related to LLM calls.
2.  **Improve Efficiency:** Reduce token consumption, improve caching, and decrease latency where possible.
3.  **Enhance Observability:** Gain better insight into how LLM prompts are constructed and used, specifically tracking fragment usage.
4.  **Increase Reliability:** Identify and fix potential bugs or inconsistencies in prompt construction, memory updates, or state handling related to LLM interactions.

**Note:** The primary refactoring to adopt fragments and improve metrics display has been completed. Remaining detailed instrumentation, systematic data storage/analysis, and deeper caching explorations have been moved to `TODO.md` under "Performance Optimization".

## Approach

1.  **Instrumentation:**
    *   LLM calls (`model.prompt`, `conversation.prompt`) have been wrapped to record key metrics (tokens, latency) and log fragment usage.
    *   (Deferred to TODO.md) Store detailed instrumentation data persistently for broader analysis.
    *   (Deferred to TODO.md) Explicitly log all LLM call options (e.g., temperature).
    *   (Out of Scope for this phase) Detailed cache hit information from the `llm` library itself was not pursued further.

2.  **Adopt Fragments:**
    *   Prompt construction logic (`vibectl/prompt.py`) has been refactored to use `fragments=` and `system_fragments=`.
    *   Prompts have been broken down into logical fragments.
    *   Static vs. dynamic parts within prompt templates have been identified.
    *   Prompt generation functions now return lists of system and user fragments.
    *   LLM call sites have been updated to pass these fragments correctly.

3.  **Analysis & Optimization:**
    *   (Deferred to TODO.md) Systematic analysis of collected data for high-cost operations, fragment usage, and bottlenecks.
    *   (Deferred to TODO.md / Out of Scope for this phase) Exploration of explicit caching layers beyond `llm`'s fragment caching.

4.  **Verification:**
    *   Metrics are displayed and can be manually checked after optimizations.
    *   Tests pass and functionality remains correct.

## Tools & Libraries

*   `llm` library (Python API)
*   `pytest` (for testing wrappers/changes)
*   Standard Python `logging` or a simple database for metrics.

## Open Questions

*   (Deferred to TODO.md / Out of Scope for this phase) How does `llm`'s fragment caching actually work, especially with different models (OpenAI vs. Anthropic)? Does it require specific logging/setup?
*   (Deferred to TODO.md) What's the best way to store/visualize the collected metrics?
*   (Out of Scope for this phase) Is cache hit information directly exposed by the `llm` library's `Response` object, or do we need to infer it?

## Out of Scope (Initial Phase)

*   Building a complex, persistent caching system beyond what `llm` might offer via fragments (deferred to `TODO.md` as a future consideration if needed).
*   Major refactoring of core command logic unrelated to LLM calls.
