"""Atomic human approval decisions."""

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from nexus.database.models import ApprovalChoice, ApprovalDecision, AuditActorType
from nexus.repositories.approvals import ApprovalRepository
from nexus.repositories.audit import AuditAction, AuditRepository


class ApprovalNotFoundError(Exception):
    pass


class OperationNotApprovableError(Exception):
    pass


class ApprovalConflictError(Exception):
    pass


class ApprovalService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.approvals = ApprovalRepository(session)
        self.audit = AuditRepository(session)

    def decide(
        self,
        *,
        company_id: UUID,
        operation_id: UUID,
        user_id: UUID,
        decision: ApprovalChoice,
        reason: str | None,
    ) -> ApprovalDecision:
        operation = self.approvals.get(company_id=company_id, operation_id=operation_id)
        if operation is None:
            raise ApprovalNotFoundError
        if operation.outcome != "pending_approval":
            raise OperationNotApprovableError
        if operation.approval_decision is not None:
            raise ApprovalConflictError
        try:
            record = self.approvals.add_decision(
                operation=operation,
                user_id=user_id,
                decision=decision,
                reason=reason,
            )
            action = (
                AuditAction.APPROVAL_APPROVED
                if decision is ApprovalChoice.APPROVED
                else AuditAction.APPROVAL_REJECTED
            )
            self.audit.add(
                company_id=company_id,
                actor_type=AuditActorType.HUMAN,
                actor_user_id=user_id,
                action=action,
                target_type="operation_request",
                target_id=operation.id,
                metadata={"decision": decision.value, "reason_provided": bool(reason)},
            )
            self.session.commit()
            return record
        except IntegrityError as error:
            self.session.rollback()
            raise ApprovalConflictError from error
