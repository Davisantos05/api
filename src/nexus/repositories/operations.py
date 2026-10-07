"""Tenant-scoped operation request persistence."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload

from nexus.database.models import (
    Agent,
    ApprovalChoice,
    ApprovalDecision,
    OperationRequestRecord,
)
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

    @staticmethod
    def _detailed_query() -> Select[OperationRequestRecord]:
        return select(OperationRequestRecord).options(
            joinedload(OperationRequestRecord.agent),
            joinedload(OperationRequestRecord.approval_decision).joinedload(
                ApprovalDecision.decided_by_user
            ),
        )

    def get_by_id(
        self, *, company_id: UUID, operation_id: UUID
    ) -> OperationRequestRecord | None:
        return self.session.scalar(
            self._detailed_query().where(
                OperationRequestRecord.company_id == company_id,
                OperationRequestRecord.id == operation_id,
            )
        )

    def list_detailed(
        self,
        *,
        company_id: UUID,
        agent_id: UUID | None = None,
        outcome: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        limit: int = 100,
        undecided_only: bool = False,
    ) -> list[OperationRequestRecord]:
        query = self._detailed_query().where(
            OperationRequestRecord.company_id == company_id
        )
        if agent_id is not None:
            query = query.where(OperationRequestRecord.agent_id == agent_id)
        if outcome is not None:
            query = query.where(OperationRequestRecord.outcome == outcome)
        if undecided_only:
            query = query.where(~OperationRequestRecord.approval_decision.has())
        if created_from is not None:
            query = query.where(OperationRequestRecord.created_at >= created_from)
        if created_to is not None:
            query = query.where(OperationRequestRecord.created_at <= created_to)
        return list(
            self.session.scalars(
                query.order_by(OperationRequestRecord.created_at.desc()).limit(limit)
            )
        )

    def dashboard_summary(self, company_id: UUID) -> dict[str, int]:
        operation_counts = dict(
            self.session.execute(
                select(OperationRequestRecord.outcome, func.count())
                .where(OperationRequestRecord.company_id == company_id)
                .group_by(OperationRequestRecord.outcome)
            ).all()
        )
        approval_counts = dict(
            self.session.execute(
                select(ApprovalDecision.decision, func.count())
                .where(ApprovalDecision.company_id == company_id)
                .group_by(ApprovalDecision.decision)
            ).all()
        )
        return {
            "agents_active": self.session.scalar(
                select(func.count())
                .select_from(Agent)
                .where(Agent.company_id == company_id, Agent.active.is_(True))
            )
            or 0,
            "operations_total": sum(operation_counts.values()),
            "authorized": operation_counts.get("authorized", 0),
            "pending_approval": self.session.scalar(
                select(func.count())
                .select_from(OperationRequestRecord)
                .where(
                    OperationRequestRecord.company_id == company_id,
                    OperationRequestRecord.outcome == "pending_approval",
                    ~OperationRequestRecord.approval_decision.has(),
                )
            )
            or 0,
            "blocked": operation_counts.get("blocked", 0),
            "human_approved": approval_counts.get(ApprovalChoice.APPROVED, 0),
            "human_rejected": approval_counts.get(ApprovalChoice.REJECTED, 0),
        }

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
