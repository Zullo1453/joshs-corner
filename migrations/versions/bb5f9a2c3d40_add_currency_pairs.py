"""Add saved manual currency reference-rate pairs.

Revision ID: bb5f9a2c3d40
Revises: aa4e8f1b2c30
"""
from alembic import op
import sqlalchemy as sa


revision = "bb5f9a2c3d40"
down_revision = "aa4e8f1b2c30"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "currency_pair",
        sa.Column("id", sa.Integer(), nullable=False), sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column("quote_currency", sa.String(length=3), nullable=False), sa.Column("display_name", sa.String(length=120), server_default="", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False), sa.Column("active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True), sa.Column("cached_rates_json", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("base_currency <> quote_currency", name="currency_pair_distinct"), sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("base_currency", "quote_currency", name="currency_pair_identity"),
    )
    with op.batch_alter_table("currency_pair") as batch_op:
        batch_op.create_index(batch_op.f("ix_currency_pair_active"), ["active"], unique=False)


def downgrade():
    op.drop_table("currency_pair")
