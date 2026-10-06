"""Tenant-scoped operation request persistence."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from nexus.database.models import OperationRequestRecord
from nexus.domain.authorization import (
    AgentPolicy,
    AuthorizationDecision,
    OperationRequest,
)


class OperationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(
        self, *, company_id: UUID, agent_id: UUID, request_id: UUID
    ) -> OperationRequestRecord | None:
        return self.session.scalar(
            select(OperationRequestRecord).where(
                OperationRequestRecord.company_id == company_id,
                OperationRequestRecord.agent_id == agent_id,
                OperationRequestRecord.request_id == request_id,
            )
        )

    def list_for_company(self, company_id: UUID) -> list[OperationRequestRecord]:
        return list(
            self.session.scalars(
                select(OperationRequestRecord).where(
                    OperationRequestRecord.company_id == company_id
                )
            )
        )

    def add(
        self,
        decision: AuthorizationDecision,
        request: OperationRequest,
        policy: AgentPolicy,
    ) -> OperationRequestRecord:
        record = OperationRequestRecord(
            request_id=request.request_id,
            company_id=decision.company_id,
            agent_id=decision.agent_id,
            operation=request.operation,
            amount_cents=request.amount_cents,
            outcome=decision.outcome.value,
            reason=decision.reason.value,
            policy_snapshot={
                "schema_version": 1,
                "active": policy.active,
                "allowed_operations": sorted(policy.allowed_operations),
                "automatic_limit_cents": policy.automatic_limit_cents,
                "maximum_limit_cents": policy.maximum_limit_cents,
            },
        )
        self.session.add(record)
        self.session.flush()
        return record
