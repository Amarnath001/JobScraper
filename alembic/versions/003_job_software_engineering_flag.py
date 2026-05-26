"""Add is_software_engineering_related to jobs."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_job_software_engineering_flag"
down_revision: Union[str, None] = "002_company_validation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "is_software_engineering_related",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index(
        "ix_jobs_is_software_engineering_related",
        "jobs",
        ["is_software_engineering_related"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_is_software_engineering_related", table_name="jobs")
    op.drop_column("jobs", "is_software_engineering_related")
