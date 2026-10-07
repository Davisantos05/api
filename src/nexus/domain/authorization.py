"""Pure authorization rules for agent-requested operations.

This module deliberately knows nothing about HTTP, authentication, or storage.
Callers must load ``AgentPolicy`` from a trusted server-side source.
"""

import re
from enum import StrEnum
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)


class DecisionOutcome(StrEnum):
    """Possible outcomes of evaluating an operation."""

    AUTHORIZED = "authorized"
    PENDING_APPROVAL = "pending_approval"
    BLOCKED = "blocked"


class DecisionReason(StrEnum):
    """Stable, machine-readable explanations for authorization decisions."""

    WITHIN_AUTOMATIC_LIMIT = "within_automatic_limit"
    HUMAN_APPROVAL_REQUIRED = "human_approval_required"
    MAXIMUM_LIMIT_EXCEEDED = "maximum_limit_exceeded"
    OPERATION_NOT_ALLOWED = "operation_not_allowed"
    AGENT_INACTIVE = "agent_inactive"


class OperationRequest(BaseModel):
    """Validated facts supplied for one operation evaluation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: UUID
    operation: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    amount_cents: StrictInt = Field(ge=0)


class AgentPolicy(BaseModel):
    """Trusted policy snapshot loaded by the server for an authenticated agent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: UUID
    company_id: UUID
    active: bool
    allowed_operations: frozenset[str]
    automatic_limit_cents: StrictInt = Field(ge=0)
    maximum_limit_cents: StrictInt = Field(ge=0)

    @field_validator("allowed_operations")
    @classmethod
    def validate_operations(cls, operations: frozenset[str]) -> frozenset[str]:
        if not operations:
            raise ValueError("at least one operation must be allowed")
        for operation in operations:
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", operation):
                raise ValueError(
                    "allowed operations must start with a lowercase letter and use "
                    "only lowercase letters, numbers, or underscores"
                )
        return operations

    @model_validator(mode="after")
    def validate_limits(self) -> "AgentPolicy":
        if self.automatic_limit_cents > self.maximum_limit_cents:
            raise ValueError("automatic limit cannot exceed maximum limit")
        return self


class AuthorizationDecision(BaseModel):
    """Immutable and explainable output suitable for later audit persistence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: UUID
    agent_id: UUID
    company_id: UUID
    operation: str
    amount_cents: int
    outcome: DecisionOutcome
    reason: DecisionReason


def evaluate_operation(
    policy: AgentPolicy, request: OperationRequest
) -> AuthorizationDecision:
    """Evaluate one request using only its server-owned agent policy."""

    if not policy.active:
        outcome = DecisionOutcome.BLOCKED
        reason = DecisionReason.AGENT_INACTIVE
    elif request.operation not in policy.allowed_operations:
        outcome = DecisionOutcome.BLOCKED
        reason = DecisionReason.OPERATION_NOT_ALLOWED
    elif request.amount_cents <= policy.automatic_limit_cents:
        outcome = DecisionOutcome.AUTHORIZED
        reason = DecisionReason.WITHIN_AUTOMATIC_LIMIT
    elif request.amount_cents <= policy.maximum_limit_cents:
        outcome = DecisionOutcome.PENDING_APPROVAL
        reason = DecisionReason.HUMAN_APPROVAL_REQUIRED
    else:
        outcome = DecisionOutcome.BLOCKED
        reason = DecisionReason.MAXIMUM_LIMIT_EXCEEDED

    return AuthorizationDecision(
        request_id=request.request_id,
        agent_id=policy.agent_id,
        company_id=policy.company_id,
        operation=request.operation,
        amount_cents=request.amount_cents,
        outcome=outcome,
        reason=reason,
    )
