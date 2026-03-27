"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2026-03-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("careers_url", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_config", postgresql.JSONB(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_companies_source_type", "companies", ["source_type"], unique=False)
    op.create_index("ix_companies_enabled", "companies", ["enabled"], unique=False)

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("external_job_id", sa.String(length=512), nullable=True),
        sa.Column("title", sa.String(length=1024), nullable=False),
        sa.Column("team", sa.String(length=512), nullable=True),
        sa.Column("location", sa.String(length=512), nullable=True),
        sa.Column("employment_type", sa.String(length=256), nullable=True),
        sa.Column("level", sa.String(length=256), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("description_text", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("entry_level_score", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_entry_level", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("fingerprint_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_jobs_fingerprint_hash", "jobs", ["fingerprint_hash"], unique=False)
    op.create_index("ix_jobs_first_seen_at", "jobs", ["first_seen_at"], unique=False)
    op.create_index("ix_jobs_is_entry_level", "jobs", ["is_entry_level"], unique=False)
    op.create_index("ix_jobs_is_active", "jobs", ["is_active"], unique=False)
    op.create_index("ix_jobs_company_id", "jobs", ["company_id"], unique=False)
    op.create_unique_constraint("uq_jobs_fingerprint_hash", "jobs", ["fingerprint_hash"])


def downgrade() -> None:
    op.drop_constraint("uq_jobs_fingerprint_hash", "jobs", type_="unique")
    op.drop_index("ix_jobs_company_id", table_name="jobs")
    op.drop_index("ix_jobs_is_active", table_name="jobs")
    op.drop_index("ix_jobs_is_entry_level", table_name="jobs")
    op.drop_index("ix_jobs_first_seen_at", table_name="jobs")
    op.drop_index("ix_jobs_fingerprint_hash", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_companies_enabled", table_name="companies")
    op.drop_index("ix_companies_source_type", table_name="companies")
    op.drop_table("companies")
