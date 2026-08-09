"""Add generic automation metadata and run history.

Revision ID: 9a7b3c5d8e10
Revises: 268a59cac5dd
"""
from alembic import op
import sqlalchemy as sa


revision = "9a7b3c5d8e10"
down_revision = "268a59cac5dd"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "automation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("automation_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('active', 'paused', 'archived')", name="automation_status_valid"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("automation", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_automation_automation_type"), ["automation_type"], unique=False)
        batch_op.create_index(batch_op.f("ix_automation_next_check_at"), ["next_check_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_automation_status"), ["status"], unique=False)

    op.create_table(
        "automation_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("automation_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("summary", sa.Text(), server_default="", nullable=False),
        sa.CheckConstraint("status IN ('running', 'succeeded', 'failed')", name="automation_run_status_valid"),
        sa.ForeignKeyConstraint(["automation_id"], ["automation.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("automation_run", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_automation_run_automation_id"), ["automation_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_automation_run_started_at"), ["started_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_automation_run_status"), ["status"], unique=False)


def downgrade():
    with op.batch_alter_table("automation_run", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_automation_run_status"))
        batch_op.drop_index(batch_op.f("ix_automation_run_started_at"))
        batch_op.drop_index(batch_op.f("ix_automation_run_automation_id"))
    op.drop_table("automation_run")
    with op.batch_alter_table("automation", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_automation_status"))
        batch_op.drop_index(batch_op.f("ix_automation_next_check_at"))
        batch_op.drop_index(batch_op.f("ix_automation_automation_type"))
    op.drop_table("automation")
