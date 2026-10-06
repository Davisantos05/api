"""Public HTTP response contracts."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StrictInt

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


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_slug: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str
    new_password: str


class UserView(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    email: str
    role: str


class SessionView(BaseModel):
    id: UUID
    expires_at: datetime


class LoginResponse(BaseModel):
    token: str
    session: SessionView
    user: UserView


class AgentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    allowed_operations: frozenset[str] = Field(min_length=1)
    automatic_limit_cents: StrictInt = Field(ge=0)
    maximum_limit_cents: StrictInt = Field(ge=0)


class AgentView(BaseModel):
    id: UUID
    name: str
    description: str
    active: bool
    allowed_operations: list[str]
    automatic_limit_cents: int
    maximum_limit_cents: int


class CredentialCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expires_at: datetime | None = None


class CredentialView(BaseModel):
    id: UUID
    token_prefix: str
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None


class CredentialCreatedResponse(BaseModel):
    credential: CredentialView
    token: str
