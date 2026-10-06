"""Create the initial multi-tenant NEXUS schema.

Revision ID: 20261005_0001
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261005_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companies")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "admin",
                "approver",
                "viewer",
                name="userrole",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_users_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("company_id", "email", name=op.f("uq_users_company_id")),
    )
    op.create_index(op.f("ix_users_company_id"), "users", ["company_id"])
    op.create_table(
        "agents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("automatic_limit_cents", sa.BigInteger(), nullable=False),
        sa.Column("maximum_limit_cents", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "automatic_limit_cents >= 0",
            name=op.f("ck_agents_automatic_limit_non_negative"),
        ),
        sa.CheckConstraint(
            "maximum_limit_cents >= 0",
            name=op.f("ck_agents_maximum_limit_non_negative"),
        ),
        sa.CheckConstraint(
            "automatic_limit_cents <= maximum_limit_cents",
            name=op.f("ck_agents_valid_limit_order"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_agents_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agents")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_agents_token_hash")),
    )
    op.create_index(op.f("ix_agents_company_id"), "agents", ["company_id"])
    op.create_table(
        "agent_permissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name=op.f("fk_agent_permissions_agent_id_agents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_permissions")),
        sa.UniqueConstraint(
            "agent_id", "operation", name=op.f("uq_agent_permissions_agent_id")
        ),
    )
    op.create_index(
        op.f("ix_agent_permissions_agent_id"), "agent_permissions", ["agent_id"]
    )
    op.create_table(
        "operation_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name=op.f("fk_operation_requests_agent_id_agents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_operation_requests_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_operation_requests")),
        sa.UniqueConstraint(
            "request_id", name=op.f("uq_operation_requests_request_id")
        ),
    )
    op.create_index(
        op.f("ix_operation_requests_agent_id"), "operation_requests", ["agent_id"]
    )
    op.create_index(
        op.f("ix_operation_requests_company_id"), "operation_requests", ["company_id"]
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_operation_requests_company_id"), table_name="operation_requests"
    )
    op.drop_index(
        op.f("ix_operation_requests_agent_id"), table_name="operation_requests"
    )
    op.drop_table("operation_requests")
    op.drop_index(op.f("ix_agent_permissions_agent_id"), table_name="agent_permissions")
    op.drop_table("agent_permissions")
    op.drop_index(op.f("ix_agents_company_id"), table_name="agents")
    op.drop_table("agents")
    op.drop_index(op.f("ix_users_company_id"), table_name="users")
    op.drop_table("users")
    op.drop_table("companies")
