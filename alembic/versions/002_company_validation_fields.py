"""company validation fields

Revision ID: 002_company_validation
Revises: 001_initial
Create Date: 2026-03-28

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "002_company_validation"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("companies", sa.Column("last_validation_status", sa.String(length=64), nullable=True))
    op.add_column(
        "companies",
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("companies", sa.Column("last_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "last_error")
    op.drop_column("companies", "consecutive_failures")
    op.drop_column("companies", "last_validation_status")
    op.drop_column("companies", "last_validated_at")
