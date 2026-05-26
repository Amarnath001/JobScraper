"""Add is_software_engineering_related to jobs.

Revision ID: 003_swe_flag
Revises: 002_company_validation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "003_swe_flag"
down_revision: str | None = "002_company_validation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMN = "is_software_engineering_related"
_INDEX = "ix_jobs_is_software_engineering_related"


def _job_column_names() -> set[str]:
    bind = op.get_bind()
    return {col["name"] for col in inspect(bind).get_columns("jobs")}


def _job_index_names() -> set[str]:
    bind = op.get_bind()
    return {idx["name"] for idx in inspect(bind).get_indexes("jobs")}


def upgrade() -> None:
    if _COLUMN not in _job_column_names():
        op.add_column(
            "jobs",
            sa.Column(
                _COLUMN,
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
    if _INDEX not in _job_index_names():
        op.create_index(_INDEX, "jobs", [_COLUMN], unique=False)


def downgrade() -> None:
    if _INDEX in _job_index_names():
        op.drop_index(_INDEX, table_name="jobs")
    if _COLUMN in _job_column_names():
        op.drop_column("jobs", _COLUMN)
