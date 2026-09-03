"""Allow reps-only exercise sets for bodyweight and calisthenics movements."""
from alembic import op
import sqlalchemy as sa


revision = "a9c4d7e1b250"
down_revision = "f6c8d2e4a910"
branch_labels = None
depends_on = None


NEW_MEASUREMENT = (
    "(duration_seconds IS NULL AND weight_kg IS NOT NULL AND reps IS NOT NULL) OR "
    "(duration_seconds IS NULL AND weight_kg IS NULL AND reps IS NOT NULL) OR "
    "(duration_seconds IS NOT NULL AND duration_seconds BETWEEN 1 AND 86400 AND weight_kg IS NULL AND reps IS NULL)"
)
OLD_MEASUREMENT = (
    "(duration_seconds IS NULL AND weight_kg IS NOT NULL AND reps IS NOT NULL) OR "
    "(duration_seconds IS NOT NULL AND duration_seconds BETWEEN 1 AND 86400 AND weight_kg IS NULL AND reps IS NULL)"
)


def upgrade():
    with op.batch_alter_table("exercise_set") as batch:
        batch.drop_constraint("exercise_set_measurement", type_="check")
        batch.create_check_constraint("exercise_set_measurement", NEW_MEASUREMENT)


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM exercise_set WHERE duration_seconds IS NULL AND weight_kg IS NULL AND reps IS NOT NULL")).scalar():
        raise RuntimeError("Cannot downgrade while reps-only sets exist; restore a pre-upgrade backup instead.")
    with op.batch_alter_table("exercise_set") as batch:
        batch.drop_constraint("exercise_set_measurement", type_="check")
        batch.create_check_constraint("exercise_set_measurement", OLD_MEASUREMENT)
