"""
Core LLM proxy service implementation.

This module provides the main LLMProxyServicer class that handles gRPC requests
and interfaces with LLM models.
"""

import logging
import time
import uuid
from collections.abc import Iterator

import grpc  # type: ignore
import llm

from .proto.llm_proxy_pb2 import (  # type: ignore
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
from .proto.llm_proxy_pb2_grpc import VibectlLLMProxyServicer  # type: ignore

logger = logging.getLogger(__name__)


class LLMProxyServicer(VibectlLLMProxyServicer):
    """Main LLM proxy service implementation."""

    def __init__(self, default_model: str | None = None):
        """Initialize the LLM proxy servicer.

        Args:
            default_model: Default model to use if none specified in requests
        """
        self.default_model = default_model
        logger.info(f"Initialized LLMProxyServicer with default_model={default_model}")

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

            # Calculate metrics
            duration_ms = int((time.time() - start_time) * 1000)

            return ExecuteResponse(
                request_id=request_id,
                success=ExecuteSuccess(
                    response_text=response_text,
                    actual_model_used=model_name,
                    metrics=ExecutionMetrics(
                        duration_ms=duration_ms,
                        timestamp=int(time.time()),
                        retry_count=0,
                    ),
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

            # For now, simulate streaming by chunking the response
            # TODO: Implement actual streaming when LLM library supports it
            response = model.prompt(prompt_text)
            response_text = response.text()

            # Split response into chunks
            chunk_size = 100
            for i in range(0, len(response_text), chunk_size):
                chunk_text = response_text[i : i + chunk_size]
                yield StreamChunk(request_id=request_id, text_chunk=chunk_text)

            # Send completion
            duration_ms = int((time.time() - start_time) * 1000)
            yield StreamChunk(
                request_id=request_id,
                complete=StreamComplete(actual_model_used=model_name),
                final_metrics=ExecutionMetrics(
                    duration_ms=duration_ms, timestamp=int(time.time()), retry_count=0
                ),
            )

        except Exception as e:
            logger.error(f"Error processing streaming request {request_id}: {e}")

            yield StreamChunk(
                request_id=request_id,
                error=ExecuteError(error_code="EXECUTION_FAILED", error_message=str(e)),
            )

    def GetServerInfo(  # noqa: N802
        self, request: GetServerInfoRequest, context: grpc.ServicerContext
    ) -> GetServerInfoResponse:
        """Get server information including available models and limits."""
        logger.info("Processing GetServerInfo request")

        try:
            # Get available models
            models = []
            for model in llm.get_models():  # type: ignore
                models.append(
                    ModelInfo(
                        model_id=model.model_id,
                        display_name=getattr(model, "display_name", model.model_id),
                        provider=getattr(model, "provider", "unknown"),
                        supports_streaming=False,  # TODO: Check streaming support
                    )
                )

            return GetServerInfoResponse(
                server_version="0.1.0",  # TODO: Get from package version
                available_models=models,
                default_model=self.default_model or "",
                limits=ServerLimits(),
            )

        except Exception as e:
            logger.error(f"Error processing GetServerInfo request: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal server error: {e}")
            raise
