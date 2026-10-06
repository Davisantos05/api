"""Persistent multi-tenant data model for NEXUS 0.3."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nexus.database.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class UserRole(StrEnum):
    ADMIN = "admin"
    APPROVER = "approver"
    VIEWER = "viewer"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class Company(TimestampMixin, Base):
    __tablename__ = "companies"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    users: Mapped[list[User]] = relationship(back_populates="company")
    agents: Mapped[list[Agent]] = relationship(back_populates="company")


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("company_id", "email"),)

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            native_enum=False,
            length=20,
            values_callable=lambda roles: [role.value for role in roles],
        ),
        nullable=False,
    )

    company: Mapped[Company] = relationship(back_populates="users")


class Agent(TimestampMixin, Base):
    __tablename__ = "agents"
    __table_args__ = (
        CheckConstraint(
            "automatic_limit_cents >= 0", name="automatic_limit_non_negative"
        ),
        CheckConstraint("maximum_limit_cents >= 0", name="maximum_limit_non_negative"),
        CheckConstraint(
            "automatic_limit_cents <= maximum_limit_cents", name="valid_limit_order"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    automatic_limit_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    maximum_limit_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    token_hash: Mapped[bytes] = mapped_column(
        LargeBinary(32), nullable=False, unique=True
    )

    company: Mapped[Company] = relationship(back_populates="agents")
    permissions: Mapped[list[AgentPermission]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )
    operation_requests: Mapped[list[OperationRequestRecord]] = relationship(
        back_populates="agent"
    )


class AgentPermission(Base):
    __tablename__ = "agent_permissions"
    __table_args__ = (UniqueConstraint("agent_id", "operation"),)

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    operation: Mapped[str] = mapped_column(String(64), nullable=False)

    agent: Mapped[Agent] = relationship(back_populates="permissions")


class OperationRequestRecord(Base):
    __tablename__ = "operation_requests"
    __table_args__ = (
        UniqueConstraint(
            "agent_id",
            "request_id",
            name="uq_operation_requests_agent_id_request_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    request_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    agent: Mapped[Agent] = relationship(back_populates="operation_requests")
