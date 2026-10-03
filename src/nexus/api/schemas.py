"""Public HTTP response contracts."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from nexus.domain.authorization import DecisionOutcome, DecisionReason


class OperationResult(BaseModel):
    """Public representation of an authorization decision."""

    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    agent_id: UUID
    operation: str
    amount_cents: int
    outcome: DecisionOutcome
    reason: DecisionReason


class OperationResponse(BaseModel):
    """Successful evaluation envelope."""

    data: OperationResult


class ErrorDetail(BaseModel):
    """Stable API error payload."""

    code: str
    message: str
    details: list[Any] | None = None


class ErrorResponse(BaseModel):
    """Standard error envelope."""

    error: ErrorDetail
