"""
gRPC servicer implementation for the vibectl LLM proxy service.

This module implements the actual gRPC service methods for handling
LLM requests and responses.
"""

import logging
import time
import uuid
from collections.abc import Iterator

import grpc
import llm

from vibectl.proto.llm_proxy_pb2 import (  # type: ignore
    ExecuteError,
    ExecuteRequest,
    ExecuteResponse,
    ExecuteSuccess,
    ExecutionMetrics,
    GetServerInfoRequest,
    GetServerInfoResponse,
    ModelInfo,
    ServerLimits,
    StreamChunk,
    StreamComplete,
)
from vibectl.proto.llm_proxy_pb2_grpc import VibectlLLMProxyServicer
from vibectl.utils import get_package_version

logger = logging.getLogger(__name__)


class LLMProxyServicer(VibectlLLMProxyServicer):
    """Main LLM proxy service implementation."""

    def __init__(self, default_model: str | None = None, config: dict | None = None):
        """Initialize the LLM proxy servicer.

        Args:
            default_model: Optional default model to use when none specified
            config: Server configuration dictionary
        """
        self.default_model = default_model
        self.config = config or {}
        logger.info(
            f"LLM proxy servicer initialized with default model: {default_model}"
        )

    def Execute(  # noqa: N802
        self, request: ExecuteRequest, context: grpc.ServicerContext
    ) -> ExecuteResponse:
        """Execute a single LLM request and return the response."""
        start_time = time.time()
        request_id = request.request_id or str(uuid.uuid4())

        logger.info(f"Processing Execute request {request_id}")

        try:
            # Get the model
            model_name = request.model_name or self.default_model
            if not model_name:
                return ExecuteResponse(
                    request_id=request_id,
                    error=ExecuteError(
                        error_code="NO_MODEL",
                        error_message=(
                            "No model specified and no default model configured"
                        ),
                    ),
                )

            model = llm.get_model(model_name)
            if not model:
                return ExecuteResponse(
                    request_id=request_id,
                    error=ExecuteError(
                        error_code="MODEL_NOT_FOUND",
                        error_message=f"Model '{model_name}' not found",
                    ),
                )

            # Construct the prompt
            prompt_parts = []
            if request.system_fragments:
                prompt_parts.extend(request.system_fragments)
            if request.user_fragments:
                prompt_parts.extend(request.user_fragments)

            prompt_text = "\n\n".join(prompt_parts)

            # Execute the LLM request
            response = model.prompt(prompt_text)
            response_text = response.text()

            # Calculate metrics and extract token usage
            duration_ms = int((time.time() - start_time) * 1000)

            # Extract token usage from response if available
            input_tokens = 0
            output_tokens = 0

            try:
                if hasattr(response, "usage"):
                    usage_data = response.usage

                    # Handle callable usage (some models return a function)
                    if callable(usage_data):
                        try:
                            usage_data = usage_data()
                        except Exception as e:
                            logger.warning(f"Error calling usage() method: {e}")
                            usage_data = None

                    # Extract tokens from usage data
                    if isinstance(usage_data, dict):
                        input_tokens = int(usage_data.get("prompt_tokens", 0))
                        output_tokens = int(usage_data.get("completion_tokens", 0))
                    elif (
                        usage_data is not None
                        and hasattr(usage_data, "input")
                        and hasattr(usage_data, "output")
                    ):
                        input_tokens = int(getattr(usage_data, "input", 0))
                        output_tokens = int(getattr(usage_data, "output", 0))

                # If no token usage available, estimate based on text length
                if input_tokens == 0 or output_tokens == 0:

                    def estimate_tokens(text: str) -> int:
                        # Rough estimate: ~4 characters per token
                        return max(1, len(text) // 4)

                    if input_tokens == 0:
                        input_tokens = estimate_tokens(prompt_text)
                    if output_tokens == 0:
                        output_tokens = estimate_tokens(response_text)

            except (
                Exception
            ):  # pragma: no cover - fallback for any token extraction failure
                # Fall back to estimation
                def estimate_tokens(text: str) -> int:
                    return max(1, len(text) // 4)

                input_tokens = estimate_tokens(prompt_text)
                output_tokens = estimate_tokens(response_text)

            # Create metrics with token information
            metrics = ExecutionMetrics(
                duration_ms=duration_ms,
                timestamp=int(time.time()),
                retry_count=0,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

            return ExecuteResponse(
                request_id=request_id,
                success=ExecuteSuccess(
                    response_text=response_text,
                    actual_model_used=model_name,
                    metrics=metrics,
                ),
            )

        except Exception as e:
            logger.error(f"Error processing request {request_id}: {e}")
            duration_ms = int((time.time() - start_time) * 1000)

            return ExecuteResponse(
                request_id=request_id,
                error=ExecuteError(error_code="EXECUTION_FAILED", error_message=str(e)),
            )

    def StreamExecute(  # noqa: N802
        self, request: ExecuteRequest, context: grpc.ServicerContext
    ) -> Iterator[StreamChunk]:
        """Execute an LLM request with streaming response."""
        start_time = time.time()
        request_id = request.request_id or str(uuid.uuid4())

        logger.info(f"Processing StreamExecute request {request_id}")

        try:
            # Get the model
            model_name = request.model_name or self.default_model
            if not model_name:
                yield StreamChunk(
                    request_id=request_id,
                    error=ExecuteError(
                        error_code="NO_MODEL",
                        error_message=(
                            "No model specified and no default model configured"
                        ),
                    ),
                )
                return

            model = llm.get_model(model_name)
            if not model:
                yield StreamChunk(
                    request_id=request_id,
                    error=ExecuteError(
                        error_code="MODEL_NOT_FOUND",
                        error_message=f"Model '{model_name}' not found",
                    ),
                )
                return

            # Construct the prompt
            prompt_parts = []
            if request.system_fragments:
                prompt_parts.extend(request.system_fragments)
            if request.user_fragments:
                prompt_parts.extend(request.user_fragments)

            prompt_text = "\n\n".join(prompt_parts)

            # Use actual streaming from LLM library instead of simulation
            try:
                response = model.prompt(prompt_text)
                logger.debug(f"Got response from model.prompt, type: {type(response)}")

                # Check if this response object supports streaming (is iterable)
                # If so, stream the chunks as they arrive
                response_text_for_metrics = ""

                try:
                    for chunk in response:  # type: ignore[attr-defined]
                        response_text_for_metrics += chunk
                        yield StreamChunk(request_id=request_id, text_chunk=chunk)
                    logger.debug(
                        "Completed streaming, accumulated text length: "
                        f"{len(response_text_for_metrics)}"
                    )
                except TypeError as te:
                    # Response object is not iterable (doesn't support streaming)
                    # Fall back to the complete response
                    logger.info(
                        f"Model {model_name} doesn't support streaming, "
                        f"falling back to simulated streaming: {te}"
                    )
                    response_text_for_metrics = response.text()

                    # Simulate streaming by chunking the complete response
                    chunk_size = 100
                    for i in range(0, len(response_text_for_metrics), chunk_size):
                        chunk_text = response_text_for_metrics[i : i + chunk_size]
                        yield StreamChunk(request_id=request_id, text_chunk=chunk_text)

                # Use the accumulated text for metrics calculation
                response_text = response_text_for_metrics

            except Exception as stream_error:
                logger.warning(
                    f"Streaming failed for request {request_id}, "
                    f"falling back to non-streaming: {stream_error}"
                )

                # Complete fallback: get full response and simulate streaming
                response = model.prompt(prompt_text)
                response_text = response.text()

                chunk_size = 100
                for i in range(0, len(response_text), chunk_size):
                    chunk_text = response_text[i : i + chunk_size]
                    yield StreamChunk(request_id=request_id, text_chunk=chunk_text)

            # Calculate metrics and extract token usage
            duration_ms = int((time.time() - start_time) * 1000)

            # Extract token usage from response if available
            input_tokens = 0
            output_tokens = 0

            try:
                if hasattr(response, "usage"):
                    usage_data = response.usage

                    # Handle callable usage (some models return a function)
                    if callable(usage_data):
                        try:
                            usage_data = usage_data()
                        except Exception as e:
                            logger.warning(f"Error calling usage() method: {e}")
                            usage_data = None

                    # Extract tokens from usage data
                    if isinstance(usage_data, dict):
                        input_tokens = int(usage_data.get("prompt_tokens", 0))
                        output_tokens = int(usage_data.get("completion_tokens", 0))
                    elif (
                        usage_data is not None
                        and hasattr(usage_data, "input")
                        and hasattr(usage_data, "output")
                    ):
                        input_tokens = int(getattr(usage_data, "input", 0))
                        output_tokens = int(getattr(usage_data, "output", 0))

                # If no token usage available, estimate based on text length
                if input_tokens == 0 or output_tokens == 0:

                    def estimate_tokens(text: str) -> int:
                        # Rough estimate: ~4 characters per token
                        return max(1, len(text) // 4)

                    if input_tokens == 0:
                        input_tokens = estimate_tokens(prompt_text)
                    if output_tokens == 0:
                        output_tokens = estimate_tokens(response_text)

            except (
                Exception
            ):  # pragma: no cover - fallback for any token extraction failure
                # Fall back to estimation
                def estimate_tokens(text: str) -> int:
                    return max(1, len(text) // 4)

                input_tokens = estimate_tokens(prompt_text)
                output_tokens = estimate_tokens(response_text)

            # Create metrics with token information
            metrics = ExecutionMetrics(
                duration_ms=duration_ms,
                timestamp=int(time.time()),
                retry_count=0,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

            # Send completion with metrics as two separate chunks
            # (oneof only allows one field to be set at a time)

            # First, send the completion chunk
            yield StreamChunk(
                request_id=request_id,
                complete=StreamComplete(actual_model_used=model_name),
            )

            # Then, send the metrics chunk
            yield StreamChunk(
                request_id=request_id,
                final_metrics=metrics,
            )

        except Exception as e:
            logger.error(f"Error processing streaming request {request_id}: {e}")

            yield StreamChunk(
                request_id=request_id,
                error=ExecuteError(error_code="EXECUTION_FAILED", error_message=str(e)),
            )

    def _get_dynamic_model_aliases(self) -> dict[str, str]:
        """Get model aliases dynamically from the llm library.

        Returns:
            dict: Mapping of aliases to model IDs
        """
        alias_map = {}
        try:
            models_with_aliases = llm.get_models_with_aliases()  # type: ignore[attr-defined]
            for model_with_aliases in models_with_aliases:
                model_id = model_with_aliases.model.model_id
                for alias in model_with_aliases.aliases:
                    alias_map[alias] = model_id

            logger.debug(f"Discovered {len(alias_map)} model aliases from llm library")
            return alias_map

        except Exception as e:
            logger.error(f"Failed to discover model aliases from llm library: {e}")
            return {}

    def GetServerInfo(  # noqa: N802
        self, request: GetServerInfoRequest, context: grpc.ServicerContext
    ) -> GetServerInfoResponse:
        """Get server information including available models and limits."""
        logger.info("Processing GetServerInfo request")

        try:
            # Get available models
            models = []

            # Get dynamic aliases from llm library
            dynamic_aliases = self._get_dynamic_model_aliases()

            # Also allow for any configured aliases (for overrides)
            configured_aliases = self.config.get("model_aliases", {})

            # Merge configured aliases with dynamic ones (configured take precedence)
            all_aliases = {**dynamic_aliases, **configured_aliases}

            for model in llm.get_models():  # type: ignore
                # Find aliases for this model
                model_id = model.model_id
                aliases = [
                    alias for alias, target in all_aliases.items() if target == model_id
                ]

                model_info = ModelInfo(
                    model_id=model_id,
                    display_name=getattr(model, "display_name", model_id),
                    provider=getattr(model, "provider", "unknown"),
                    supports_streaming=False,  # TODO: Check streaming support
                )
                # aliases is a RepeatedScalarContainer, so we need to extend it
                model_info.aliases.extend(aliases)

                models.append(model_info)

            return GetServerInfoResponse(
                server_version=get_package_version(),
                server_name="vibectl-llm-proxy",
                available_models=models,
                default_model=self.default_model or "",
                limits=ServerLimits(),
                model_aliases=all_aliases,
            )

        except Exception as e:
            logger.error(f"Error processing GetServerInfo request: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal server error: {e}")
            raise
