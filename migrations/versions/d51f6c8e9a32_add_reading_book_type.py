"""Add optional fiction classification to reading items.

Revision ID: d51f6c8e9a32
Revises: c4d8e1f1a921
"""
from alembic import op
import sqlalchemy as sa


revision = "d51f6c8e9a32"
down_revision = "c4d8e1f1a921"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("reading_item", schema=None) as batch_op:
        batch_op.add_column(sa.Column("book_type", sa.String(length=20), nullable=True))
        batch_op.create_check_constraint(
            "reading_book_type_valid",
            "book_type IS NULL OR book_type IN ('fiction', 'non_fiction')",
        )


def downgrade():
    with op.batch_alter_table("reading_item", schema=None) as batch_op:
        batch_op.drop_constraint("reading_book_type_valid", type_="check")
        batch_op.drop_column("book_type")
