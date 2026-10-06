"""Central role-based access-control policies."""

from enum import StrEnum

from nexus.database.models import UserRole


class Capability(StrEnum):
    VIEW_AGENTS = "view_agents"
    CREATE_AGENTS = "create_agents"
    MANAGE_AGENT_CREDENTIALS = "manage_agent_credentials"
    VIEW_OPERATIONS = "view_operations"


ROLE_CAPABILITIES: dict[UserRole, frozenset[Capability]] = {
    UserRole.ADMIN: frozenset(Capability),
    UserRole.APPROVER: frozenset({Capability.VIEW_OPERATIONS}),
    UserRole.VIEWER: frozenset({Capability.VIEW_AGENTS, Capability.VIEW_OPERATIONS}),
}


def has_capability(role: UserRole, capability: Capability) -> bool:
    return capability in ROLE_CAPABILITIES[role]
