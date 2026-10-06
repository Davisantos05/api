"""Add human approval decisions and immutable audit events.

Revision ID: 20261006_0005
Revises: 20261006_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_0005"
down_revision: str | None = "20261006_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "approval_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("operation_request_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "decision",
            sa.Enum(
                "approved",
                "rejected",
                name="approvalchoice",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["operation_request_id"], ["operation_requests.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "operation_request_id",
            name="uq_approval_decisions_operation_request_id",
        ),
    )
    op.create_index(
        "ix_approval_decisions_company_id", "approval_decisions", ["company_id"]
    )
    op.create_index(
        "ix_approval_decisions_decided_by_user_id",
        "approval_decisions",
        ["decided_by_user_id"],
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column(
            "actor_type",
            sa.Enum(
                "human",
                "agent",
                "system",
                name="auditactortype",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_agent_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_agent_id"], ["agents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "company_id",
        "actor_user_id",
        "actor_agent_id",
        "action",
        "target_type",
        "created_at",
    ):
        op.create_index(f"ix_audit_events_{column}", "audit_events", [column])


def downgrade() -> None:
    for column in (
        "created_at",
        "target_type",
        "action",
        "actor_agent_id",
        "actor_user_id",
        "company_id",
    ):
        op.drop_index(f"ix_audit_events_{column}", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index(
        "ix_approval_decisions_decided_by_user_id",
        table_name="approval_decisions",
    )
    op.drop_index("ix_approval_decisions_company_id", table_name="approval_decisions")
    op.drop_table("approval_decisions")
