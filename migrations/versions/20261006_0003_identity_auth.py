"""Add human sessions and rotatable agent credentials.

Revision ID: 20261006_0003
Revises: 20261006_0002
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_0003"
down_revision: str | None = "20261006_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("companies") as batch_op:
        batch_op.add_column(sa.Column("slug", sa.String(length=100), nullable=True))
    connection = op.get_bind()
    companies = sa.table(
        "companies", sa.column("id", sa.Uuid()), sa.column("slug", sa.String())
    )
    for row in connection.execute(sa.select(companies.c.id)):
        connection.execute(
            companies.update()
            .where(companies.c.id == row.id)
            .values(slug=f"company-{str(row.id).replace('-', '')}")
        )
    with op.batch_alter_table("companies") as batch_op:
        batch_op.alter_column("slug", existing_type=sa.String(100), nullable=False)
        batch_op.create_unique_constraint("uq_companies_slug", ["slug"])

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("password_hash", sa.String(length=512), nullable=True)
        )

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_user_sessions_token_hash"),
    )
    op.create_index("ix_user_sessions_company_id", "user_sessions", ["company_id"])
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])

    op.create_table(
        "agent_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column("token_prefix", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_agent_credentials_token_hash"),
    )
    op.create_index("ix_agent_credentials_agent_id", "agent_credentials", ["agent_id"])

    agents = sa.table(
        "agents",
        sa.column("id", sa.Uuid()),
        sa.column("token_hash", sa.LargeBinary()),
    )
    credentials = sa.table(
        "agent_credentials",
        sa.column("id", sa.Uuid()),
        sa.column("agent_id", sa.Uuid()),
        sa.column("token_hash", sa.LargeBinary()),
        sa.column("token_prefix", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(UTC)
    for row in connection.execute(
        sa.select(agents.c.id, agents.c.token_hash).where(
            agents.c.token_hash.is_not(None)
        )
    ):
        connection.execute(
            credentials.insert().values(
                id=uuid4(),
                agent_id=row.id,
                token_hash=row.token_hash,
                token_prefix="legacy",
                created_at=now,
            )
        )
    with op.batch_alter_table("agents") as batch_op:
        batch_op.drop_column("token_hash")


def downgrade() -> None:
    connection = op.get_bind()
    with op.batch_alter_table("agents") as batch_op:
        batch_op.add_column(
            sa.Column("token_hash", sa.LargeBinary(length=32), nullable=True)
        )
    agents = sa.table(
        "agents",
        sa.column("id", sa.Uuid()),
        sa.column("token_hash", sa.LargeBinary()),
    )
    credentials = sa.table(
        "agent_credentials",
        sa.column("agent_id", sa.Uuid()),
        sa.column("token_hash", sa.LargeBinary()),
    )
    for row in connection.execute(sa.select(agents.c.id, agents.c.token_hash)):
        if row.token_hash is None:
            replacement = connection.scalar(
                sa.select(credentials.c.token_hash)
                .where(credentials.c.agent_id == row.id)
                .limit(1)
            )
            if replacement is None:
                raise RuntimeError(
                    "cannot downgrade: every agent needs at least one credential"
                )
            connection.execute(
                agents.update()
                .where(agents.c.id == row.id)
                .values(token_hash=replacement)
            )
    op.drop_index("ix_agent_credentials_agent_id", table_name="agent_credentials")
    op.drop_table("agent_credentials")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_index("ix_user_sessions_company_id", table_name="user_sessions")
    op.drop_table("user_sessions")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("password_hash")
    with op.batch_alter_table("companies") as batch_op:
        batch_op.drop_constraint("uq_companies_slug", type_="unique")
        batch_op.drop_column("slug")
    with op.batch_alter_table("agents") as batch_op:
        batch_op.alter_column(
            "token_hash", existing_type=sa.LargeBinary(32), nullable=False
        )
        batch_op.create_unique_constraint("uq_agents_token_hash", ["token_hash"])
