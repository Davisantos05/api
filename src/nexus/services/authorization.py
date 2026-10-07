"""Persistent orchestration around the pure authorization engine."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from nexus.database.models import AuditActorType, OperationRequestRecord
from nexus.domain.authorization import (
    AuthorizationDecision,
    DecisionOutcome,
    DecisionReason,
    OperationRequest,
    evaluate_operation,
)
from nexus.repositories.agents import AgentRepository
from nexus.repositories.audit import AuditAction, AuditRepository
from nexus.repositories.identity import AgentCredentialRepository
from nexus.repositories.operations import OperationRepository


class UnknownAgentError(Exception):
    """Raised when a development token does not identify a persisted agent."""


class IdempotencyConflictError(Exception):
    """Raised when a request identifier is reused with different content."""


class PersistentAuthorizationService:
    """Authenticate, load policy, evaluate and persist one simulated operation."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.agents = AgentRepository(session)
        self.credentials = AgentCredentialRepository(session)
        self.operations = OperationRepository(session)
        self.audit = AuditRepository(session)

    def evaluate(
        self, *, token: str, request: OperationRequest
    ) -> AuthorizationDecision:
        credential = self.credentials.authenticate(token)
        if credential is None:
            raise UnknownAgentError
        agent = credential.agent

        existing = self.operations.get(
            company_id=agent.company_id,
            agent_id=agent.id,
            request_id=request.request_id,
        )
        if existing is not None:
            replay = self._replay_or_reject(existing, request)
            self.session.commit()
            return replay

        policy = self.agents.to_policy(agent)
        decision = evaluate_operation(policy, request)
        try:
            record = self.operations.add(decision, request, policy)
            self.audit.add(
                company_id=agent.company_id,
                actor_type=AuditActorType.AGENT,
                actor_agent_id=agent.id,
                action=AuditAction.OPERATION_REQUESTED,
                target_type="operation_request",
                target_id=record.id,
                metadata={
                    "operation": request.operation,
                    "amount_cents": request.amount_cents,
                },
            )
            action = {
                DecisionOutcome.AUTHORIZED: AuditAction.OPERATION_AUTHORIZED,
                DecisionOutcome.BLOCKED: AuditAction.OPERATION_BLOCKED,
                DecisionOutcome.PENDING_APPROVAL: AuditAction.OPERATION_PENDING,
            }[decision.outcome]
            self.audit.add(
                company_id=agent.company_id,
                actor_type=AuditActorType.SYSTEM,
                action=action,
                target_type="operation_request",
                target_id=record.id,
                metadata={"reason": decision.reason.value},
            )
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            concurrent = self.operations.get(
                company_id=agent.company_id,
                agent_id=agent.id,
                request_id=request.request_id,
            )
            if concurrent is None:
                raise IdempotencyConflictError from error
            return self._replay_or_reject(concurrent, request)
        return decision

    @staticmethod
    def _replay_or_reject(
        record: OperationRequestRecord, request: OperationRequest
    ) -> AuthorizationDecision:
        if (
            record.operation != request.operation
            or record.amount_cents != request.amount_cents
        ):
            raise IdempotencyConflictError
        return AuthorizationDecision(
            request_id=record.request_id,
            agent_id=record.agent_id,
            company_id=record.company_id,
            operation=record.operation,
            amount_cents=record.amount_cents,
            outcome=DecisionOutcome(record.outcome),
            reason=DecisionReason(record.reason),
        )
