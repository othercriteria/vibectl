"""vibectl gRPC protocol definitions."""

try:
    # Import protobuf modules - these may not be available in all environments
    from . import llm_proxy_pb2, llm_proxy_pb2_grpc

    __all__ = ["llm_proxy_pb2", "llm_proxy_pb2_grpc"]

except ImportError:
    # Protobuf files not available - this can happen in CI or if
    # grpcio-tools isn't installed
    llm_proxy_pb2 = None  # type: ignore[assignment]
    llm_proxy_pb2_grpc = None  # type: ignore[assignment]

    __all__ = []
