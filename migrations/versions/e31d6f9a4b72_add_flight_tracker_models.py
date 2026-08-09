"""Add the Flight Tracker configuration and normalized observation models.

Revision ID: e31d6f9a4b72
Revises: 9a7b3c5d8e10
"""
from alembic import op
import sqlalchemy as sa


revision = "e31d6f9a4b72"
down_revision = "9a7b3c5d8e10"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("automation_run", schema=None) as batch_op:
        batch_op.add_column(sa.Column("provider", sa.String(length=40), server_default="", nullable=False))
        batch_op.add_column(sa.Column("configuration_version", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_automation_run_configuration_version"), ["configuration_version"], unique=False)
    op.create_table(
        "flight_tracker",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("automation_id", sa.Integer(), nullable=False),
        sa.Column("outbound_origin", sa.String(length=3), nullable=False),
        sa.Column("outbound_destination", sa.String(length=3), nullable=False),
        sa.Column("outbound_date", sa.Date(), nullable=False),
        sa.Column("return_origin", sa.String(length=3), nullable=False),
        sa.Column("return_destination", sa.String(length=3), nullable=False),
        sa.Column("return_date", sa.Date(), nullable=False),
        sa.Column("adults", sa.Integer(), server_default="1", nullable=False),
        sa.Column("cabin_class", sa.String(length=24), server_default="economy", nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="AUD", nullable=False),
        sa.Column("target_price_cents", sa.Integer(), nullable=False),
        sa.Column("primary_max_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("primary_max_stops", sa.Integer(), nullable=False),
        sa.Column("secondary_enabled", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("configuration_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("adults >= 1 AND adults <= 9", name="flight_tracker_adults_valid"),
        sa.CheckConstraint("target_price_cents > 0", name="flight_tracker_target_positive"),
        sa.CheckConstraint("primary_max_duration_minutes > 0 AND primary_max_duration_minutes <= 10080", name="flight_tracker_duration_valid"),
        sa.CheckConstraint("primary_max_stops >= 0 AND primary_max_stops <= 6", name="flight_tracker_stops_valid"),
        sa.CheckConstraint("cabin_class IN ('economy', 'premium_economy', 'business', 'first')", name="flight_tracker_cabin_valid"),
        sa.CheckConstraint("configuration_version >= 1", name="flight_tracker_config_version_valid"),
        sa.ForeignKeyConstraint(["automation_id"], ["automation.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("automation_id"),
    )
    with op.batch_alter_table("flight_tracker", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_flight_tracker_automation_id"), ["automation_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_flight_tracker_outbound_date"), ["outbound_date"], unique=False)
        batch_op.create_index(batch_op.f("ix_flight_tracker_return_date"), ["return_date"], unique=False)
    op.create_table(
        "flight_offer",
        sa.Column("id", sa.Integer(), nullable=False), sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("tracker_id", sa.Integer(), nullable=False), sa.Column("configuration_version", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False), sa.Column("total_price_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False), sa.Column("outbound_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("return_duration_minutes", sa.Integer(), nullable=False), sa.Column("outbound_stops", sa.Integer(), nullable=False),
        sa.Column("return_stops", sa.Integer(), nullable=False), sa.Column("airline_summary", sa.String(length=240), server_default="", nullable=False),
        sa.Column("itinerary_summary", sa.String(length=500), server_default="", nullable=False),
        sa.Column("provider_offer_reference", sa.String(length=160), server_default="", nullable=False),
        sa.Column("booking_url", sa.String(length=1000), server_default="", nullable=False), sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("category IN ('primary', 'secondary')", name="flight_offer_category_valid"),
        sa.CheckConstraint("total_price_cents > 0", name="flight_offer_price_positive"),
        sa.CheckConstraint("outbound_duration_minutes >= 0", name="flight_offer_outbound_duration_valid"),
        sa.CheckConstraint("return_duration_minutes >= 0", name="flight_offer_return_duration_valid"),
        sa.CheckConstraint("outbound_stops >= 0", name="flight_offer_outbound_stops_valid"),
        sa.CheckConstraint("return_stops >= 0", name="flight_offer_return_stops_valid"),
        sa.ForeignKeyConstraint(["run_id"], ["automation_run.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tracker_id"], ["flight_tracker.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("run_id", "fingerprint", name="flight_offer_run_fingerprint_unique"),
    )
    with op.batch_alter_table("flight_offer", schema=None) as batch_op:
        for column in ("run_id", "tracker_id", "configuration_version", "category", "total_price_cents", "observed_at"):
            batch_op.create_index(batch_op.f(f"ix_flight_offer_{column}"), [column], unique=False)


def downgrade():
    with op.batch_alter_table("flight_offer", schema=None) as batch_op:
        for column in ("observed_at", "total_price_cents", "category", "configuration_version", "tracker_id", "run_id"):
            batch_op.drop_index(batch_op.f(f"ix_flight_offer_{column}"))
    op.drop_table("flight_offer")
    with op.batch_alter_table("flight_tracker", schema=None) as batch_op:
        for column in ("return_date", "outbound_date", "automation_id"):
            batch_op.drop_index(batch_op.f(f"ix_flight_tracker_{column}"))
    op.drop_table("flight_tracker")
    with op.batch_alter_table("automation_run", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_automation_run_configuration_version"))
        batch_op.drop_column("configuration_version")
        batch_op.drop_column("provider")
