"""Timed exercise sets and a reference distance for named routes."""
from alembic import op
import sqlalchemy as sa

revision = "f6c8d2e4a910"
down_revision = "e4b7a9c2d610"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("exercise", sa.Column("tracking_type", sa.String(12), nullable=False, server_default="reps"))
    op.add_column("run_route", sa.Column("distance_km", sa.Numeric(8, 3), nullable=True))
    with op.batch_alter_table("exercise_set") as batch:
        batch.add_column(sa.Column("duration_seconds", sa.Integer(), nullable=True))
        batch.alter_column("weight_kg", existing_type=sa.Numeric(8, 2), nullable=True)
        batch.alter_column("reps", existing_type=sa.Integer(), nullable=True)
        batch.create_check_constraint("exercise_set_measurement",
            "(duration_seconds IS NULL AND weight_kg IS NOT NULL AND reps IS NOT NULL) OR "
            "(duration_seconds IS NOT NULL AND duration_seconds BETWEEN 1 AND 86400 AND weight_kg IS NULL AND reps IS NULL)")


def downgrade():
    # Never silently discard timed history to fit the old schema.
    if op.get_bind().execute(sa.text("SELECT count(*) FROM exercise_set WHERE duration_seconds IS NOT NULL")).scalar():
        raise RuntimeError("Cannot downgrade while timed sets exist; restore a pre-upgrade backup instead.")
    with op.batch_alter_table("exercise_set") as batch:
        batch.drop_constraint("exercise_set_measurement", type_="check")
        batch.drop_column("duration_seconds")
        batch.alter_column("weight_kg", existing_type=sa.Numeric(8, 2), nullable=False)
        batch.alter_column("reps", existing_type=sa.Integer(), nullable=False)
    with op.batch_alter_table("run_route") as batch:
        batch.drop_column("distance_km")
    with op.batch_alter_table("exercise") as batch:
        batch.drop_column("tracking_type")
