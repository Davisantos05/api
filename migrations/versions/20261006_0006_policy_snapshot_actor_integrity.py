"""Preserve policy snapshots and enforce coherent audit actors.

Revision ID: 20261006_0006
Revises: 20261006_0005
"""

from collections import defaultdict
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_0006"
down_revision: str | None = "20261006_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTOR_IDENTITY_CHECK = """
    (actor_type = 'human' AND actor_user_id IS NOT NULL AND actor_agent_id IS NULL)
    OR (actor_type = 'agent' AND actor_agent_id IS NOT NULL AND actor_user_id IS NULL)
    OR (actor_type = 'system' AND actor_user_id IS NULL AND actor_agent_id IS NULL)
"""


def upgrade() -> None:
    with op.batch_alter_table("operation_requests") as batch_op:
        batch_op.add_column(sa.Column("policy_snapshot", sa.JSON(), nullable=True))

    connection = op.get_bind()
    agents = sa.table(
        "agents",
        sa.column("id", sa.Uuid()),
        sa.column("active", sa.Boolean()),
        sa.column("automatic_limit_cents", sa.BigInteger()),
        sa.column("maximum_limit_cents", sa.BigInteger()),
    )
    permissions = sa.table(
        "agent_permissions",
        sa.column("agent_id", sa.Uuid()),
        sa.column("operation", sa.String()),
    )
    operations = sa.table(
        "operation_requests",
        sa.column("id", sa.Uuid()),
        sa.column("agent_id", sa.Uuid()),
        sa.column("policy_snapshot", sa.JSON()),
    )

    allowed_operations: dict[object, list[str]] = defaultdict(list)
    for permission in connection.execute(
        sa.select(permissions.c.agent_id, permissions.c.operation)
    ):
        allowed_operations[permission.agent_id].append(permission.operation)

    agents_by_id = {
        agent.id: agent
        for agent in connection.execute(
            sa.select(
                agents.c.id,
                agents.c.active,
                agents.c.automatic_limit_cents,
                agents.c.maximum_limit_cents,
            )
        )
    }
    for operation in connection.execute(
        sa.select(operations.c.id, operations.c.agent_id)
    ):
        agent = agents_by_id[operation.agent_id]
        snapshot = {
            "schema_version": 1,
            "active": agent.active,
            "allowed_operations": sorted(allowed_operations[agent.id]),
            "automatic_limit_cents": agent.automatic_limit_cents,
            "maximum_limit_cents": agent.maximum_limit_cents,
        }
        connection.execute(
            operations.update()
            .where(operations.c.id == operation.id)
            .values(policy_snapshot=snapshot)
        )

    with op.batch_alter_table("operation_requests") as batch_op:
        batch_op.alter_column(
            "policy_snapshot", existing_type=sa.JSON(), nullable=False
        )

    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.create_check_constraint(
            "ck_audit_events_valid_actor_identity", ACTOR_IDENTITY_CHECK
        )


def downgrade() -> None:
    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.drop_constraint("ck_audit_events_valid_actor_identity", type_="check")
    with op.batch_alter_table("operation_requests") as batch_op:
        batch_op.drop_column("policy_snapshot")
