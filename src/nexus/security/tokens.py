"""Generation and one-way fingerprints for opaque NEXUS tokens."""

import hashlib
import secrets

AGENT_TOKEN_PREFIX_LENGTH = 12


def fingerprint_agent_token(token: str) -> bytes:
    """Create the SHA-256 lookup representation stored for an opaque token."""

    return hashlib.sha256(token.encode("utf-8")).digest()


def generate_agent_token() -> str:
    return f"nxs_ag_{secrets.token_urlsafe(32)}"


def generate_session_token() -> str:
    return f"nxs_us_{secrets.token_urlsafe(32)}"
