"""Append-only, tenant-scoped audit persistence."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from nexus.database.models import AuditActorType, AuditEvent

FORBIDDEN_METADATA_FRAGMENTS = frozenset(
    {"password", "token", "authorization", "secret", "credential", "hash"}
)


class AuditAction(StrEnum):
    HUMAN_LOGIN = "human.login"
    HUMAN_LOGOUT = "human.logout"
    PASSWORD_CHANGED = "human.password_changed"
    AGENT_CREATED = "agent.created"
    CREDENTIAL_CREATED = "agent_credential.created"
    CREDENTIAL_REVOKED = "agent_credential.revoked"
    OPERATION_REQUESTED = "operation.requested"
    OPERATION_AUTHORIZED = "operation.authorized"
    OPERATION_BLOCKED = "operation.blocked"
    OPERATION_PENDING = "operation.pending_approval"
    APPROVAL_APPROVED = "approval.approved"
    APPROVAL_REJECTED = "approval.rejected"


def sanitize_metadata(metadata: dict[str, object] | None) -> dict[str, object]:
    """Accept only shallow, non-secret scalar metadata assembled by the server."""

    clean: dict[str, object] = {}
    for key, value in (metadata or {}).items():
        normalized = key.lower().replace("-", "_")
        if any(fragment in normalized for fragment in FORBIDDEN_METADATA_FRAGMENTS):
            raise ValueError(f"sensitive audit metadata key is forbidden: {key}")
        if not isinstance(value, (str, int, float, bool, type(None))):
            raise ValueError(f"audit metadata value must be scalar: {key}")
        clean[key] = value
    return clean


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(
        self,
        *,
        company_id: UUID,
        actor_type: AuditActorType,
        action: AuditAction,
        target_type: str,
        target_id: UUID,
        actor_user_id: UUID | None = None,
        actor_agent_id: UUID | None = None,
        metadata: dict[str, object] | None = None,
    ) -> AuditEvent:
        valid_actor = {
            AuditActorType.HUMAN: actor_user_id is not None and actor_agent_id is None,
            AuditActorType.AGENT: actor_agent_id is not None and actor_user_id is None,
            AuditActorType.SYSTEM: actor_user_id is None and actor_agent_id is None,
        }[actor_type]
        if not valid_actor:
            raise ValueError("audit actor identifiers do not match actor_type")
        event = AuditEvent(
            company_id=company_id,
            actor_type=actor_type,
            actor_user_id=actor_user_id,
            actor_agent_id=actor_agent_id,
            action=action.value,
            target_type=target_type,
            target_id=target_id,
            metadata_json=sanitize_metadata(metadata),
        )
        self.session.add(event)
        self.session.flush()
        return event

    def list_for_company(
        self,
        *,
        company_id: UUID,
        actor_type: AuditActorType | None = None,
        action: str | None = None,
        target_type: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        query: Select[AuditEvent] = select(AuditEvent).where(
            AuditEvent.company_id == company_id
        )
        if actor_type is not None:
            query = query.where(AuditEvent.actor_type == actor_type)
        if action is not None:
            query = query.where(AuditEvent.action == action)
        if target_type is not None:
            query = query.where(AuditEvent.target_type == target_type)
        if created_from is not None:
            query = query.where(AuditEvent.created_at >= created_from)
        if created_to is not None:
            query = query.where(AuditEvent.created_at <= created_to)
        return list(
            self.session.scalars(
                query.order_by(AuditEvent.created_at.desc()).limit(limit)
            )
        )
