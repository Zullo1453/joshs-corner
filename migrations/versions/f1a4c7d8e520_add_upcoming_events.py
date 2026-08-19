"""Add independent Upcoming events.

Revision ID: f1a4c7d8e520
Revises: e8d2c6b1a470
"""
from alembic import op
import sqlalchemy as sa


revision = "f1a4c7d8e520"
down_revision = "e8d2c6b1a470"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "upcoming_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_time", sa.Time(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_upcoming_event_event_date"), "upcoming_event", ["event_date"], unique=False)


def downgrade():
    op.drop_table("upcoming_event")
