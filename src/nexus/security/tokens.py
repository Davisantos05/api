"""Shared helpers for temporary agent token fingerprints."""

import hashlib


def fingerprint_agent_token(token: str) -> bytes:
    """Create the one-way lookup representation stored by NEXUS 0.3."""

    return hashlib.sha256(token.encode("utf-8")).digest()
