"""Tenant-scoped approval queries."""

from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload

from nexus.database.models import (
    ApprovalChoice,
    ApprovalDecision,
    OperationRequestRecord,
)


class ApprovalRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _query() -> Select[OperationRequestRecord]:
        return select(OperationRequestRecord).options(
            joinedload(OperationRequestRecord.agent),
            joinedload(OperationRequestRecord.approval_decision).joinedload(
                ApprovalDecision.decided_by_user
            ),
        )

    def get(
        self, *, company_id: UUID, operation_id: UUID
    ) -> OperationRequestRecord | None:
        return self.session.scalar(
            self._query().where(
                OperationRequestRecord.company_id == company_id,
                OperationRequestRecord.id == operation_id,
            )
        )

    def list(
        self,
        *,
        company_id: UUID,
        status: str = "pending",
        agent_id: UUID | None = None,
        limit: int = 100,
    ) -> list[OperationRequestRecord]:
        query = self._query().where(
            OperationRequestRecord.company_id == company_id,
            OperationRequestRecord.outcome == "pending_approval",
        )
        if status == "pending":
            query = query.where(~OperationRequestRecord.approval_decision.has())
        elif status in {choice.value for choice in ApprovalChoice}:
            query = query.where(
                OperationRequestRecord.approval_decision.has(decision=status)
            )
        if agent_id is not None:
            query = query.where(OperationRequestRecord.agent_id == agent_id)
        return list(
            self.session.scalars(
                query.order_by(OperationRequestRecord.created_at.desc()).limit(limit)
            )
        )

    def add_decision(
        self,
        *,
        operation: OperationRequestRecord,
        user_id: UUID,
        decision: ApprovalChoice,
        reason: str | None,
    ) -> ApprovalDecision:
        record = ApprovalDecision(
            operation_request_id=operation.id,
            company_id=operation.company_id,
            decided_by_user_id=user_id,
            decision=decision,
            reason=reason,
        )
        self.session.add(record)
        self.session.flush()
        return record
