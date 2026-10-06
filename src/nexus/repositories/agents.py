"""Agent persistence and server-owned policy loading."""

from collections.abc import Collection
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload, selectinload

from nexus.database.models import Agent, AgentPermission
from nexus.domain.authorization import AgentPolicy
from nexus.security.tokens import fingerprint_agent_token


class AgentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        company_id: UUID,
        name: str,
        description: str,
        token: str,
        allowed_operations: Collection[str],
        automatic_limit_cents: int,
        maximum_limit_cents: int,
        active: bool = True,
    ) -> Agent:
        if not allowed_operations:
            raise ValueError("an agent must have at least one permission")
        if len(token) < 32:
            raise ValueError(
                "development agent tokens must contain at least 32 characters"
            )
        agent = Agent(
            company_id=company_id,
            name=name,
            description=description,
            active=active,
            automatic_limit_cents=automatic_limit_cents,
            maximum_limit_cents=maximum_limit_cents,
            token_hash=fingerprint_agent_token(token),
            permissions=[
                AgentPermission(operation=operation)
                for operation in sorted(set(allowed_operations))
            ],
        )
        self.session.add(agent)
        self.session.flush()
        return agent

    def get(self, *, company_id: UUID, agent_id: UUID) -> Agent | None:
        return self.session.scalar(
            self._policy_query().where(
                Agent.company_id == company_id,
                Agent.id == agent_id,
            )
        )

    def list_for_company(self, company_id: UUID) -> list[Agent]:
        return list(
            self.session.scalars(
                self._policy_query().where(Agent.company_id == company_id)
            ).unique()
        )

    def identify_by_token(self, token: str) -> Agent | None:
        """Authentication lookup; tenant context is derived from the matched agent."""

        return self.session.scalar(
            self._policy_query().where(
                Agent.token_hash == fingerprint_agent_token(token)
            )
        )

    @staticmethod
    def to_policy(agent: Agent) -> AgentPolicy:
        return AgentPolicy(
            agent_id=agent.id,
            company_id=agent.company_id,
            active=agent.active and agent.company.active,
            allowed_operations=frozenset(
                permission.operation for permission in agent.permissions
            ),
            automatic_limit_cents=agent.automatic_limit_cents,
            maximum_limit_cents=agent.maximum_limit_cents,
        )

    @staticmethod
    def _policy_query() -> Select[Agent]:
        return select(Agent).options(
            joinedload(Agent.company), selectinload(Agent.permissions)
        )
