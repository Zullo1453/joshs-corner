"""Add saved manual weather locations.

Revision ID: aa4e8f1b2c30
Revises: 9a7b3c5d8e10
"""
from alembic import op
import sqlalchemy as sa


revision = "aa4e8f1b2c30"
down_revision = "9a7b3c5d8e10"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "weather_location",
        sa.Column("id", sa.Integer(), nullable=False), sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False), sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False), sa.Column("country_code", sa.String(length=8), server_default="", nullable=False),
        sa.Column("admin_area", sa.String(length=120), server_default="", nullable=False), sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("active", sa.Boolean(), server_default="1", nullable=False), sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cached_weather_json", sa.Text(), server_default="", nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("display_name", "latitude", "longitude", name="weather_location_identity"),
    )
    with op.batch_alter_table("weather_location") as batch_op:
        batch_op.create_index(batch_op.f("ix_weather_location_active"), ["active"], unique=False)


def downgrade():
    op.drop_table("weather_location")
