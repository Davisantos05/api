"""Minimize stored agent credential prefixes.

Revision ID: 20261006_0004
Revises: 20261006_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_0004"
down_revision: str | None = "20261006_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    credentials = sa.table(
        "agent_credentials",
        sa.column("token_prefix", sa.String(length=20)),
    )
    op.execute(
        credentials.update()
        .where(sa.func.length(credentials.c.token_prefix) > 12)
        .values(token_prefix=sa.func.substr(credentials.c.token_prefix, 1, 12))
    )


def downgrade() -> None:
    # Removed token characters cannot and should not be reconstructed.
    pass
