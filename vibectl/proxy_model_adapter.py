"""
Proxy model adapter for communicating with vibectl LLM proxy server.

This module provides a ModelAdapter implementation that forwards requests
to a remote vibectl LLM proxy server via gRPC, enabling transparent
delegation of LLM calls to a centralized service.
"""

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import grpc
from pydantic import BaseModel

from .config import Config
from .logutil import logger
from .model_adapter import ModelAdapter, StreamingMetricsCollector
from .proto import llm_proxy_pb2, llm_proxy_pb2_grpc  # type: ignore[attr-defined]
from .proto.llm_proxy_pb2 import GetServerInfoRequest  # type: ignore[attr-defined]
from .types import LLMMetrics, SystemFragments, UserFragments


class ProxyModelWrapper:
    """Wrapper class to represent a remote model accessible via proxy."""

    def __init__(self, model_name: str, adapter: "ProxyModelAdapter"):
        self.model_name = model_name
        self.model_id = model_name  # For compatibility with existing code
        self.adapter = adapter

    def __str__(self) -> str:
        return f"ProxyModel({self.model_name})"

    def __repr__(self) -> str:
        return f"ProxyModelWrapper(model_name='{self.model_name}')"


class ProxyStreamingMetricsCollector(StreamingMetricsCollector):
    """Metrics collector for proxy streaming responses."""

    def __init__(self, request_id: str):
        self.request_id = request_id
        self.start_time = time.monotonic()
        self._metrics: LLMMetrics | None = None
        self._completed = False

    def set_final_metrics(self, metrics: LLMMetrics) -> None:
        """Set the final metrics from the proxy response."""
        self._metrics = metrics
        self._completed = True

    async def get_metrics(self) -> LLMMetrics | None:
        """Get the final metrics if available."""
        return self._metrics

    @property
    def completed(self) -> bool:
        """Check if streaming is completed."""
        return self._completed


class ProxyModelAdapter(ModelAdapter):
    """Model adapter that proxies requests to a remote vibectl LLM proxy server."""

    def __init__(
        self, config: Config | None = None, host: str = "localhost", port: int = 50051
    ):
        """Initialize the proxy model adapter.

        Args:
            config: Optional Config instance for client configuration
            host: Proxy server host (default: localhost)
            port: Proxy server port (default: 50051)
        """
        self.config = config or Config()
        self.host = host
        self.port = port
        self.channel: grpc.Channel | None = None
        self.stub: llm_proxy_pb2_grpc.VibectlLLMProxyStub | None = None
        self._model_cache: dict[str, ProxyModelWrapper] = {}

        logger.debug("ProxyModelAdapter initialized for %s:%d", self.host, self.port)

    def _get_channel(self) -> grpc.Channel:
        """Get or create the gRPC channel."""
        if self.channel is None:
            target = f"{self.host}:{self.port}"
            self.channel = grpc.insecure_channel(target)
            self.stub = llm_proxy_pb2_grpc.VibectlLLMProxyStub(self.channel)
            logger.debug("Created gRPC channel to %s", target)
        return self.channel

    def _get_stub(self) -> llm_proxy_pb2_grpc.VibectlLLMProxyStub:
        """Get or create the gRPC stub."""
        self._get_channel()  # Ensure channel exists
        if self.stub is None:
            raise RuntimeError("Failed to create gRPC stub")
        return self.stub

    def get_model(self, model_name: str) -> Any:
        """Get a proxy model wrapper by name.

        Args:
            model_name: The name of the model to get (can be an alias)

        Returns:
            ProxyModelWrapper: A wrapper representing the remote model

        Raises:
            ValueError: If the model is not available on the proxy server
        """
        # Check cache first
        if model_name in self._model_cache:
            logger.debug("Model '%s' found in cache", model_name)
            return self._model_cache[model_name]

        # Check if model is available on proxy server
        try:
            stub = self._get_stub()
            request = GetServerInfoRequest()  # type: ignore[attr-defined]
            response = stub.GetServerInfo(request, timeout=10.0)

            # Get available models from server
            available_models = [model.model_id for model in response.available_models]

            # Try direct match first
            resolved_model_name = model_name
            if model_name not in available_models:
                # Try alias resolution
                alias_result = self._resolve_model_alias(model_name, available_models)
                if alias_result is None:
                    raise ValueError(
                        f"Model '{model_name}' not available on proxy server. "
                        f"Available models: {', '.join(available_models)}"
                    )
                resolved_model_name = alias_result

            # Create and cache the wrapper (use original name for caching to
            # support aliases)
            wrapper = ProxyModelWrapper(resolved_model_name, self)
            self._model_cache[model_name] = (
                wrapper  # Cache by requested name for efficiency
            )
            logger.info(
                "Model '%s' resolved to '%s' and cached",
                model_name,
                resolved_model_name,
            )
            return wrapper

        except grpc.RpcError as e:
            logger.error("gRPC error checking model availability: %s", e)
            raise ValueError(f"Failed to connect to proxy server: {e}") from e
        except Exception as e:
            logger.error("Error getting model '%s': %s", model_name, e)
            raise ValueError(f"Failed to get model '{model_name}': {e}") from e

    def _resolve_model_alias(
        self, alias: str, available_models: list[str]
    ) -> str | None:
        """Resolve a model alias to the actual model name available on the server.

        Args:
            alias: The alias to resolve (e.g., 'claude-4-sonnet')
            available_models: List of model names available on the server

        Returns:
            The resolved model name, or None if no match found
        """
        # Common alias mappings based on llm CLI patterns
        alias_mappings = {
            # Claude models
            "claude-4-sonnet": "anthropic/claude-sonnet-4-0",
            "claude-4-opus": "anthropic/claude-opus-4-0",
            "claude-3.7-sonnet": "anthropic/claude-3-7-sonnet-latest",
            "claude-3.7-sonnet-latest": "anthropic/claude-3-7-sonnet-latest",
            "claude-3.5-sonnet": "anthropic/claude-3-5-sonnet-latest",
            "claude-3.5-sonnet-latest": "anthropic/claude-3-5-sonnet-latest",
            "claude-3.5-haiku": "anthropic/claude-3-5-haiku-latest",
            "claude-3-opus": "anthropic/claude-3-opus-latest",
            "claude-3-sonnet": "anthropic/claude-3-sonnet-20240229",
            "claude-3-haiku": "anthropic/claude-3-haiku-20240307",
            # GPT models (usually don't need aliases since names match)
            "gpt-4": "gpt-4",
            "gpt-4o": "gpt-4o",
            "gpt-3.5-turbo": "gpt-3.5-turbo",
            # O1 models
            "o1": "o1",
            "o1-mini": "o1-mini",
            "o1-preview": "o1-preview",
        }

        # First try direct alias mapping
        if alias in alias_mappings:
            mapped_name = alias_mappings[alias]
            if mapped_name in available_models:
                logger.debug("Resolved alias '%s' to '%s'", alias, mapped_name)
                return mapped_name

        # If no direct mapping, try fuzzy matching for similar patterns
        alias_lower = alias.lower()
        for model_name in available_models:
            model_lower = model_name.lower()

            # Try to find partial matches (e.g., "claude-4-sonnet" matches
            # "anthropic/claude-sonnet-4-0")
            if (
                "claude" in alias_lower
                and "claude" in model_lower
                and (
                    ("4-sonnet" in alias_lower and "sonnet-4-0" in model_lower)
                    or ("3.7-sonnet" in alias_lower and "3-7-sonnet" in model_lower)
                    or ("3.5-sonnet" in alias_lower and "3-5-sonnet" in model_lower)
                )
            ):
                logger.debug("Fuzzy matched alias '%s' to '%s'", alias, model_name)
                return model_name

        logger.debug("No alias resolution found for '%s'", alias)
        return None

    def _convert_metrics(self, pb_metrics: Any) -> LLMMetrics | None:
        """Convert protobuf metrics to LLMMetrics."""
        if pb_metrics is None:
            return None

        return LLMMetrics(
            token_input=pb_metrics.input_tokens
            if pb_metrics.HasField("input_tokens")
            else 0,
            token_output=pb_metrics.output_tokens
            if pb_metrics.HasField("output_tokens")
            else 0,
            latency_ms=float(pb_metrics.duration_ms),
            total_processing_duration_ms=float(pb_metrics.duration_ms),
            cost_usd=pb_metrics.cost_usd if pb_metrics.HasField("cost_usd") else None,
        )

    def _create_execute_request(
        self,
        model: Any,
        system_fragments: SystemFragments,
        user_fragments: UserFragments,
        response_model: type[BaseModel] | None = None,
    ) -> Any:  # type: ignore[misc]  # Protobuf type not available at type check time
        """Create an ExecuteRequest protobuf message."""
        if not isinstance(model, ProxyModelWrapper):
            raise ValueError(f"Expected ProxyModelWrapper, got {type(model)}")

        request = llm_proxy_pb2.ExecuteRequest()  # type: ignore[attr-defined]
        request.request_id = str(uuid.uuid4())
        request.model_name = model.model_name

        # Convert fragments to strings
        if system_fragments:
            request.system_fragments.extend(system_fragments)
        if user_fragments:
            request.user_fragments.extend(user_fragments)

        # Add response model schema if provided
        if response_model is not None:
            try:
                schema = response_model.model_json_schema()
                request.response_model_schema = json.dumps(schema)
            except Exception as e:
                logger.warning("Failed to serialize response model schema: %s", e)

        return request

    async def execute(
        self,
        model: Any,
        system_fragments: SystemFragments,
        user_fragments: UserFragments,
        response_model: type[BaseModel] | None = None,
    ) -> tuple[str, LLMMetrics | None]:
        """Execute a prompt on the proxy server.

        Args:
            model: ProxyModelWrapper representing the remote model
            system_fragments: List of system prompt fragments
            user_fragments: List of user prompt fragments
            response_model: Optional Pydantic model for structured JSON response

        Returns:
            tuple[str, LLMMetrics | None]: Response text and metrics

        Raises:
            ValueError: If execution fails
        """
        try:
            stub = self._get_stub()
            request = self._create_execute_request(
                model, system_fragments, user_fragments, response_model
            )

            logger.debug(
                "Executing request %s for model %s",
                request.request_id,
                request.model_name,
            )

            # Execute the request
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: stub.Execute(request, timeout=60.0)
            )

            # Handle response
            if response.HasField("success"):
                success = response.success
                metrics = self._convert_metrics(success.metrics)
                logger.debug(
                    "Request %s completed successfully, actual model: %s",
                    response.request_id,
                    success.actual_model_used,
                )
                return success.response_text, metrics
            elif response.HasField("error"):
                error = response.error
                error_msg = (
                    f"Proxy server error ({error.error_code}): {error.error_message}"
                )
                if error.HasField("error_details"):
                    error_msg += f" - {error.error_details}"
                logger.error("Request %s failed: %s", response.request_id, error_msg)
                raise ValueError(error_msg)
            else:
                raise ValueError("Invalid response from proxy server")

        except grpc.RpcError as e:
            logger.error("gRPC error during execute: %s", e)
            raise ValueError(f"Failed to execute request: {e}") from e
        except Exception as e:
            logger.error("Error during execute: %s", e)
            raise ValueError(f"Proxy execution failed: {e}") from e

    async def execute_and_log_metrics(
        self,
        model: Any,
        system_fragments: SystemFragments,
        user_fragments: UserFragments,
        response_model: type[BaseModel] | None = None,
    ) -> tuple[str, LLMMetrics | None]:
        """Execute a prompt and log metrics.

        This is identical to execute() since metrics logging is handled
        by the proxy server.
        """
        return await self.execute(
            model, system_fragments, user_fragments, response_model
        )

    async def stream_execute(
        self,
        model: Any,
        system_fragments: SystemFragments,
        user_fragments: UserFragments,
        response_model: type[BaseModel] | None = None,
    ) -> AsyncIterator[str]:
        """Execute a prompt with streaming response.

        Args:
            model: ProxyModelWrapper representing the remote model
            system_fragments: List of system prompt fragments
            user_fragments: List of user prompt fragments
            response_model: Optional Pydantic model (ignored for streaming)

        Yields:
            str: Response chunks

        Raises:
            ValueError: If streaming fails
        """
        try:
            stub = self._get_stub()
            request = self._create_execute_request(
                model, system_fragments, user_fragments, response_model
            )

            logger.debug(
                "Starting stream for request %s, model %s",
                request.request_id,
                request.model_name,
            )

            # Create async wrapper for the streaming call
            def _stream_call() -> Any:
                return stub.StreamExecute(request, timeout=120.0)

            stream = await asyncio.get_event_loop().run_in_executor(None, _stream_call)

            # Process streaming chunks
            async for chunk_pb in self._async_stream_wrapper(stream):
                if chunk_pb.HasField("text_chunk"):
                    yield chunk_pb.text_chunk
                elif chunk_pb.HasField("error"):
                    error = chunk_pb.error
                    error_msg = (
                        f"Proxy server error ({error.error_code}): "
                        f"{error.error_message}"
                    )
                    if error.HasField("error_details"):
                        error_msg += f" - {error.error_details}"
                    logger.error(
                        "Stream error for request %s: %s",
                        chunk_pb.request_id,
                        error_msg,
                    )
                    raise ValueError(error_msg)
                elif chunk_pb.HasField("complete"):
                    logger.debug(
                        "Stream completed for request %s, actual model: %s",
                        chunk_pb.request_id,
                        chunk_pb.complete.actual_model_used,
                    )
                    break
                # final_metrics are handled by stream_execute_and_log_metrics

        except grpc.RpcError as e:
            logger.error("gRPC error during stream_execute: %s", e)
            raise ValueError(f"Failed to stream request: {e}") from e
        except Exception as e:
            logger.error("Error during stream_execute: %s", e)
            raise ValueError(f"Proxy streaming failed: {e}") from e

    async def stream_execute_and_log_metrics(
        self,
        model: Any,
        system_fragments: SystemFragments,
        user_fragments: UserFragments,
        response_model: type[BaseModel] | None = None,
    ) -> tuple[AsyncIterator[str], StreamingMetricsCollector]:
        """Execute a prompt with streaming response and metrics collection.

        Args:
            model: ProxyModelWrapper representing the remote model
            system_fragments: List of system prompt fragments
            user_fragments: List of user prompt fragments
            response_model: Optional Pydantic model (ignored for streaming)

        Returns:
            tuple containing async iterator for response chunks and metrics collector
        """
        try:
            stub = self._get_stub()
            request = self._create_execute_request(
                model, system_fragments, user_fragments, response_model
            )

            metrics_collector = ProxyStreamingMetricsCollector(request.request_id)

            logger.debug(
                "Starting stream with metrics for request %s, model %s",
                request.request_id,
                request.model_name,
            )

            # Create the streaming iterator with metrics handling
            async def _streaming_iterator() -> AsyncIterator[str]:
                def _stream_call() -> Any:
                    return stub.StreamExecute(request, timeout=120.0)

                stream = await asyncio.get_event_loop().run_in_executor(
                    None, _stream_call
                )

                async for chunk_pb in self._async_stream_wrapper(stream):
                    if chunk_pb.HasField("text_chunk"):
                        yield chunk_pb.text_chunk
                    elif chunk_pb.HasField("final_metrics"):
                        metrics = self._convert_metrics(chunk_pb.final_metrics)
                        if metrics:
                            metrics_collector.set_final_metrics(metrics)
                    elif chunk_pb.HasField("error"):
                        error = chunk_pb.error
                        error_msg = (
                            f"Proxy server error ({error.error_code}): "
                            f"{error.error_message}"
                        )
                        if error.HasField("error_details"):
                            error_msg += f" - {error.error_details}"
                        logger.error(
                            "Stream error for request %s: %s",
                            chunk_pb.request_id,
                            error_msg,
                        )
                        raise ValueError(error_msg)
                    elif chunk_pb.HasField("complete"):
                        logger.debug(
                            "Stream completed for request %s, actual model: %s",
                            chunk_pb.request_id,
                            chunk_pb.complete.actual_model_used,
                        )
                        break

            return _streaming_iterator(), metrics_collector

        except grpc.RpcError as e:
            logger.error("gRPC error during stream_execute_and_log_metrics: %s", e)
            raise ValueError(f"Failed to stream request with metrics: {e}") from e
        except Exception as e:
            logger.error("Error during stream_execute_and_log_metrics: %s", e)
            raise ValueError(f"Proxy streaming with metrics failed: {e}") from e

    async def _async_stream_wrapper(self, stream: Any) -> AsyncIterator[Any]:
        """Convert gRPC streaming response to async iterator."""
        loop = asyncio.get_event_loop()

        def _get_next() -> Any | None:
            try:
                return next(stream)
            except StopIteration:
                return None

        while True:
            chunk = await loop.run_in_executor(None, _get_next)
            if chunk is None:
                break
            yield chunk

    def validate_model_key(self, model_name: str) -> str | None:
        """Validate model key - delegated to proxy server.

        For proxy connections, key validation is handled server-side.
        This method always returns None as keys are managed by the server.

        Args:
            model_name: The name of the model (unused for proxy)

        Returns:
            None: No client-side key validation needed
        """
        logger.debug(
            "Key validation delegated to proxy server for model: %s", model_name
        )
        return None

    def validate_model_name(self, model_name: str) -> str | None:
        """Validate model name against proxy server.

        Args:
            model_name: The name of the model to validate

        Returns:
            Error message if validation fails, None otherwise
        """
        try:
            # Try to get the model, which will validate it exists on the server
            self.get_model(model_name)
            return None
        except ValueError as e:
            return str(e)
        except Exception as e:
            logger.error(
                "Unexpected error validating model name '%s': %s", model_name, e
            )
            return f"Validation error: {e}"

    def close(self) -> None:
        """Close the gRPC channel."""
        if self.channel is not None:
            self.channel.close()
            self.channel = None
            self.stub = None
            logger.debug("Closed gRPC channel")

    def __enter__(self) -> "ProxyModelAdapter":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()
