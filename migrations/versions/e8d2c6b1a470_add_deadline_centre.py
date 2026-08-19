"""Add independent, date-bound Deadline records.

Revision ID: e8d2c6b1a470
Revises: c4a1e8d9f320
"""
from alembic import op
import sqlalchemy as sa


revision = "e8d2c6b1a470"
down_revision = "c4a1e8d9f320"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "deadline",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("is_completed", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_deadline_due_date"), "deadline", ["due_date"], unique=False)
    op.create_index(op.f("ix_deadline_is_completed"), "deadline", ["is_completed"], unique=False)
    op.create_index(op.f("ix_deadline_completed_at"), "deadline", ["completed_at"], unique=False)


def downgrade():
    op.drop_table("deadline")
