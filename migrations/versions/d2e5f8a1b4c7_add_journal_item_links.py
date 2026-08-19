"""Add optional Journal source links to Deadline and Upcoming records.

Revision ID: d2e5f8a1b4c7
Revises: f1a4c7d8e520
"""
from alembic import op
import sqlalchemy as sa


revision = "d2e5f8a1b4c7"
down_revision = "f1a4c7d8e520"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("deadline") as batch:
        batch.add_column(sa.Column("source_journal_entry_id", sa.Integer(), nullable=True))
        batch.create_index("ix_deadline_source_journal_entry_id", ["source_journal_entry_id"], unique=False)
        batch.create_unique_constraint("uq_deadline_source_journal_entry_id", ["source_journal_entry_id"])
        batch.create_foreign_key(
            "fk_deadline_source_journal_entry", "journal_entry", ["source_journal_entry_id"], ["id"], ondelete="SET NULL"
        )
    with op.batch_alter_table("upcoming_event") as batch:
        batch.add_column(sa.Column("source_journal_entry_id", sa.Integer(), nullable=True))
        batch.create_index("ix_upcoming_event_source_journal_entry_id", ["source_journal_entry_id"], unique=False)
        batch.create_unique_constraint("uq_upcoming_event_source_journal_entry_id", ["source_journal_entry_id"])
        batch.create_foreign_key(
            "fk_upcoming_event_source_journal_entry", "journal_entry", ["source_journal_entry_id"], ["id"], ondelete="SET NULL"
        )


def downgrade():
    with op.batch_alter_table("upcoming_event") as batch:
        batch.drop_constraint("fk_upcoming_event_source_journal_entry", type_="foreignkey")
        batch.drop_constraint("uq_upcoming_event_source_journal_entry_id", type_="unique")
        batch.drop_index("ix_upcoming_event_source_journal_entry_id")
        batch.drop_column("source_journal_entry_id")
    with op.batch_alter_table("deadline") as batch:
        batch.drop_constraint("fk_deadline_source_journal_entry", type_="foreignkey")
        batch.drop_constraint("uq_deadline_source_journal_entry_id", type_="unique")
        batch.drop_index("ix_deadline_source_journal_entry_id")
        batch.drop_column("source_journal_entry_id")
