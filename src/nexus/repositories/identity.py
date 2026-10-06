"""Repositories for human sessions and agent credentials."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from nexus.database.models import Agent, AgentCredential, Company, User, UserSession
from nexus.security.tokens import (
    fingerprint_agent_token,
    AGENT_TOKEN_PREFIX_LENGTH,
    generate_agent_token,
    generate_session_token,
)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class UserSessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_login(self, *, company_slug: str, email: str) -> User | None:
        return self.session.scalar(
            select(User)
            .join(User.company)
            .options(joinedload(User.company))
            .where(
                Company.slug == company_slug,
                User.email == email.lower(),
            )
        )

    def create(self, user: User, *, lifetime: timedelta) -> tuple[UserSession, str]:
        token = generate_session_token()
        now = datetime.now(UTC)
        record = UserSession(
            user_id=user.id,
            company_id=user.company_id,
            token_hash=fingerprint_agent_token(token),
            created_at=now,
            expires_at=now + lifetime,
        )
        self.session.add(record)
        self.session.flush()
        return record, token

    def authenticate(self, token: str) -> UserSession | None:
        record = self.session.scalar(
            select(UserSession)
            .options(joinedload(UserSession.user).joinedload(User.company))
            .where(UserSession.token_hash == fingerprint_agent_token(token))
        )
        now = datetime.now(UTC)
        if (
            record is None
            or record.revoked_at is not None
            or _utc(record.expires_at) <= now
            or not record.user.active
            or not record.user.company.active
        ):
            return None
        record.last_used_at = now
        self.session.commit()
        return record

    def revoke(self, record: UserSession) -> None:
        record.revoked_at = datetime.now(UTC)
        self.session.commit()

    def revoke_all_for_user(self, user_id: UUID) -> None:
        now = datetime.now(UTC)
        self.session.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )


class AgentCredentialRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self, agent: Agent, *, expires_at: datetime | None = None
    ) -> tuple[AgentCredential, str]:
        token = generate_agent_token()
        record = self.create_from_token(agent, token=token, expires_at=expires_at)
        return record, token

    def create_from_token(
        self, agent: Agent, *, token: str, expires_at: datetime | None = None
    ) -> AgentCredential:
        record = AgentCredential(
            agent_id=agent.id,
            token_hash=fingerprint_agent_token(token),
            token_prefix=token[:AGENT_TOKEN_PREFIX_LENGTH],
            expires_at=expires_at,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def authenticate(self, token: str) -> AgentCredential | None:
        record = self.session.scalar(
            select(AgentCredential)
            .options(
                joinedload(AgentCredential.agent).joinedload(Agent.company),
                joinedload(AgentCredential.agent).selectinload(Agent.permissions),
            )
            .where(AgentCredential.token_hash == fingerprint_agent_token(token))
        )
        now = datetime.now(UTC)
        if (
            record is None
            or record.revoked_at is not None
            or (record.expires_at is not None and _utc(record.expires_at) <= now)
        ):
            return None
        record.last_used_at = now
        self.session.flush()
        return record

    def list_for_agent(
        self, *, company_id: UUID, agent_id: UUID
    ) -> list[AgentCredential]:
        return list(
            self.session.scalars(
                select(AgentCredential)
                .join(AgentCredential.agent)
                .where(Agent.company_id == company_id, Agent.id == agent_id)
                .order_by(AgentCredential.created_at)
            )
        )

    def get(
        self, *, company_id: UUID, agent_id: UUID, credential_id: UUID
    ) -> AgentCredential | None:
        return self.session.scalar(
            select(AgentCredential)
            .join(AgentCredential.agent)
            .where(
                Agent.company_id == company_id,
                Agent.id == agent_id,
                AgentCredential.id == credential_id,
            )
        )

    def revoke(self, credential: AgentCredential) -> None:
        credential.revoked_at = datetime.now(UTC)
        self.session.flush()
