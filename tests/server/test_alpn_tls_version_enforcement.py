from unittest.mock import AsyncMock, Mock

import pytest

from vibectl.server.alpn_multiplexer import ALPNMultiplexer


@pytest.mark.asyncio
async def test_grpc_tls12_rejected() -> None:
    """gRPC (h2) connections negotiating TLS 1.2 must be rejected."""
    multiplexer = ALPNMultiplexer()

    mock_handler = AsyncMock()
    multiplexer.register_handler("h2", mock_handler)

    mock_reader = AsyncMock()
    mock_writer = Mock()
    mock_writer.is_closing.return_value = False
    mock_writer.close = Mock()
    mock_writer.wait_closed = AsyncMock()

    mock_ssl_object = Mock()
    mock_ssl_object.selected_alpn_protocol.return_value = "h2"
    mock_ssl_object.version.return_value = "TLSv1.2"

    mock_writer.get_extra_info = Mock(return_value=mock_ssl_object)

    await multiplexer._handle_connection(mock_reader, mock_writer)

    # Handler should NOT be called because connection is rejected
    mock_handler.handle_connection.assert_not_called()
    # Connection should be closed
    mock_writer.close.assert_called_once()


@pytest.mark.asyncio
async def test_acme_tls12_allowed() -> None:
    """acme-tls/1 validation is allowed to use TLS 1.2."""
    multiplexer = ALPNMultiplexer()

    mock_handler = AsyncMock()
    multiplexer.register_handler("acme-tls/1", mock_handler)

    mock_reader = AsyncMock()
    mock_writer = Mock()
    mock_writer.is_closing.return_value = False
    mock_writer.close = Mock()
    mock_writer.wait_closed = AsyncMock()

    mock_ssl_object = Mock()
    mock_ssl_object.selected_alpn_protocol.return_value = "acme-tls/1"
    mock_ssl_object.version.return_value = "TLSv1.2"

    mock_writer.get_extra_info = Mock(return_value=mock_ssl_object)

    await multiplexer._handle_connection(mock_reader, mock_writer)

    # Handler should be called for acme-tls/1
    mock_handler.handle_connection.assert_called_once_with(mock_reader, mock_writer)
