from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

"""Lightweight bridge object used to wire together the ALPNMultiplexer and
TLSALPNChallengeServer without creating an import cycle.

The objects are created in no particular order - the component that is born
first gets passed the bridge and stores itself on it.  The second component
then also receives the *same* bridge instance and can look up the counterpart.

This avoids hasattr-hacks and TYPE_CHECKING shims while still keeping the two
modules independent.
"""

if TYPE_CHECKING:  # pragma: no cover - only for type checkers
    from .alpn_multiplexer import ALPNMultiplexer
    from .tls_alpn_challenge_server import TLSALPNChallengeServer


@dataclass(slots=True)
class TLSALPNBridge:  # pylint: disable=too-few-public-methods
    """Runtime link between multiplexer and challenge server."""

    multiplexer: ALPNMultiplexer | None = None
    challenge_server: TLSALPNChallengeServer | None = None

    # Tiny helpers so caller can write bridge.attach(self)
    def attach_multiplexer(self, m: ALPNMultiplexer) -> None:
        """Store ALPNMultiplexer reference."""
        self.multiplexer = m

    def attach_challenge_server(self, s: TLSALPNChallengeServer) -> None:
        """Store TLS-ALPN challenge-server reference."""
        self.challenge_server = s
