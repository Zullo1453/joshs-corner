"""Align the Flight Tracker one-to-one index with its model constraint.

Revision ID: f4c29a7b1e8d
Revises: e31d6f9a4b72
"""
from alembic import op


revision = "f4c29a7b1e8d"
down_revision = "e31d6f9a4b72"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("flight_tracker", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_flight_tracker_automation_id"))
        batch_op.create_index(
            batch_op.f("ix_flight_tracker_automation_id"), ["automation_id"], unique=True
        )


def downgrade():
    with op.batch_alter_table("flight_tracker", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_flight_tracker_automation_id"))
        batch_op.create_index(
            batch_op.f("ix_flight_tracker_automation_id"), ["automation_id"], unique=False
        )
