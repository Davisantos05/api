"""Temporary local-only agent identification for NEXUS 0.2."""

import hashlib
import os
import secrets
from uuid import UUID

from nexus.domain.authorization import AgentPolicy


class DevelopmentAgentRegistry:
    """In-memory lookup that retains only SHA-256 token fingerprints."""

    def __init__(self) -> None:
        self._policies_by_token_hash: dict[bytes, AgentPolicy] = {}

    @staticmethod
    def _fingerprint(token: str) -> bytes:
        return hashlib.sha256(token.encode("utf-8")).digest()

    def register(self, token: str, policy: AgentPolicy) -> None:
        """Register a server-owned policy under a development token."""

        if len(token) < 32:
            raise ValueError(
                "development agent tokens must contain at least 32 characters"
            )
        self._policies_by_token_hash[self._fingerprint(token)] = policy

    def identify(self, token: str) -> AgentPolicy | None:
        """Resolve a token without retaining or comparing its plaintext value."""

        candidate = self._fingerprint(token)
        for fingerprint, policy in self._policies_by_token_hash.items():
            if secrets.compare_digest(candidate, fingerprint):
                return policy
        return None


def registry_from_environment() -> DevelopmentAgentRegistry:
    """Build the single local development agent from environment configuration."""

    token = os.getenv("NEXUS_DEV_AGENT_TOKEN")
    if not token:
        raise RuntimeError(
            "NEXUS_DEV_AGENT_TOKEN is required to use the development API"
        )

    registry = DevelopmentAgentRegistry()
    registry.register(
        token,
        AgentPolicy(
            agent_id=UUID("01950000-0000-7000-8000-000000000001"),
            company_id=UUID("01950000-0000-7000-8000-000000000002"),
            active=True,
            allowed_operations=frozenset({"purchase"}),
            automatic_limit_cents=50_000,
            maximum_limit_cents=200_000,
        ),
    )
    return registry
