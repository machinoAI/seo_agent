"""Initial schema: websites, workflow_runs, agent_results.

Revision ID: 0001
Revises:
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "websites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_websites")),
        sa.UniqueConstraint("domain", name=op.f("uq_websites_domain")),
    )
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("website_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("output_dir", sa.String(length=1024), nullable=True),
        sa.Column("report_path", sa.String(length=1024), nullable=True),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["website_id"],
            ["websites.id"],
            name=op.f("fk_workflow_runs_website_id_websites"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_runs")),
    )
    op.create_index(
        op.f("ix_workflow_runs_website_id"), "workflow_runs", ["website_id"], unique=False
    )
    op.create_table(
        "agent_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("agent", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("prompt_ref", sa.String(length=128), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("reasoning", sa.String(length=32), nullable=True),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("output_path", sa.String(length=1024), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_agent_results_run_id_workflow_runs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_results")),
        sa.UniqueConstraint("run_id", "agent", name=op.f("uq_agent_results_run_id")),
    )
    op.create_index(
        op.f("ix_agent_results_run_id"), "agent_results", ["run_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_results_run_id"), table_name="agent_results")
    op.drop_table("agent_results")
    op.drop_index(op.f("ix_workflow_runs_website_id"), table_name="workflow_runs")
    op.drop_table("workflow_runs")
    op.drop_table("websites")
