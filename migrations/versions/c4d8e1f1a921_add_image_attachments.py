"""Add locally stored rich-text image attachments.

Revision ID: c4d8e1f1a921
Revises: b31e9f2a7c10
"""
from alembic import op
import sqlalchemy as sa


revision = "c4d8e1f1a921"
down_revision = "b31e9f2a7c10"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "attachment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_type", sa.String(length=40), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("draft_token", sa.String(length=64), nullable=True),
        sa.Column("stored_filename", sa.String(length=120), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=32), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("file_size >= 0", name="attachment_file_size_nonnegative"),
        sa.CheckConstraint("width > 0", name="attachment_width_positive"),
        sa.CheckConstraint("height > 0", name="attachment_height_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stored_filename"),
    )
    op.create_index("ix_attachment_owner_type", "attachment", ["owner_type"])
    op.create_index("ix_attachment_owner_id", "attachment", ["owner_id"])
    op.create_index("ix_attachment_draft_token", "attachment", ["draft_token"])


def downgrade():
    op.drop_index("ix_attachment_draft_token", table_name="attachment")
    op.drop_index("ix_attachment_owner_id", table_name="attachment")
    op.drop_index("ix_attachment_owner_type", table_name="attachment")
    op.drop_table("attachment")
