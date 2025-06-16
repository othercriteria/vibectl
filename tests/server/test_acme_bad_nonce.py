from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import acme.errors
import pytest

from vibectl.server.acme_client import ACMEClient


@pytest.fixture()
def acme_cfg() -> dict[str, object]:
    return {
        "enabled": True,
        "email": "foo@example.com",
        "domains": ["example.com"],
        "directory_url": "https://acme.example/dir",
    }


def test_request_certificate_retries_on_bad_nonce(
    acme_cfg: dict[str, object], tmp_path: Path
) -> None:
    client = ACMEClient(
        directory_url=str(acme_cfg["directory_url"]), email="foo@example.com"
    )

    # Mock out internal client and network interactions
    mock_client = MagicMock()
    client._client = mock_client  # type: ignore[assignment, attr-defined]
    client._account_key = MagicMock()

    # Mock objects needed for successful path
    good_final_order = Mock()
    good_final_order.fullchain_pem = "CERT"

    def _make_bad_nonce() -> acme.errors.BadNonce:
        # Create instance without invoking BadNonce.__init__
        # (constructor requires params)
        err = acme.errors.BadNonce.__new__(acme.errors.BadNonce)  # type: ignore[misc]
        return err

    class SideEffectTracker:
        def __init__(self) -> None:
            self.call_count = 0

        def __call__(self, *_: Any, **__: Any) -> Mock:
            if self.call_count == 0:
                self.call_count += 1
                raise _make_bad_nonce()
            return good_final_order

    side_effect = SideEffectTracker()

    mock_client.new_order.return_value.authorizations = []
    # patch final functions to simplify: we'll patch request_certificate internal flow
    with (
        patch.object(ACMEClient, "register_account"),
        patch.object(
            ACMEClient,
            "_create_csr",
            return_value=Mock(csr=Mock(public_bytes=Mock(return_value=b"csr"))),
        ),
        patch.object(
            mock_client, "new_order", return_value=Mock(authorizations=[])
        ) as _new_order,
        patch.object(
            mock_client, "finalize_order", side_effect=side_effect
        ) as mock_finalize,
        patch("vibectl.server.acme_client.rsa.generate_private_key") as mock_rsa,
    ):
        mock_key = Mock()
        mock_key.private_bytes.return_value = b"KEY"
        mock_rsa.return_value = mock_key

        with patch.object(mock_client.net, "get", return_value=Mock(json=lambda: {})):
            cert_bytes, key_bytes = client.request_certificate(["example.com"])

            assert cert_bytes == b"CERT"
            assert key_bytes == b"KEY"

            # finalize_order called twice: first raises badNonce, second returns cert
            assert mock_finalize.call_count == 2
