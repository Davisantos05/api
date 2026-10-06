"""Scope operation request idempotency to each agent.

Revision ID: 20261006_0002
Revises: 20261005_0001
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261006_0002"
down_revision: str | None = "20261005_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("operation_requests") as batch_op:
        batch_op.drop_constraint("uq_operation_requests_request_id", type_="unique")
        batch_op.create_unique_constraint(
            "uq_operation_requests_agent_id_request_id",
            ["agent_id", "request_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("operation_requests") as batch_op:
        batch_op.drop_constraint(
            "uq_operation_requests_agent_id_request_id", type_="unique"
        )
        batch_op.create_unique_constraint(
            "uq_operation_requests_request_id", ["request_id"]
        )
