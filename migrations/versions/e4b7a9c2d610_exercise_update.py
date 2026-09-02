"""Stage 4B: exercise favourites, independent workout templates, and runs."""
from alembic import op
import sqlalchemy as sa

revision = "e4b7a9c2d610"
down_revision = "0dd8dae16435"
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade():
    op.add_column("exercise", sa.Column("is_favorite", sa.Boolean(), server_default="0", nullable=False))
    op.create_table("workout_template",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False), *timestamps())
    op.create_table("workout_template_exercise",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("workout_template.id", ondelete="CASCADE"), nullable=False),
        sa.Column("exercise_id", sa.Integer(), sa.ForeignKey("exercise.id"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.UniqueConstraint("template_id", "exercise_id", name="uq_template_exercise"))
    op.create_index("ix_workout_template_exercise_template_id", "workout_template_exercise", ["template_id"])
    op.create_index("ix_workout_template_exercise_exercise_id", "workout_template_exercise", ["exercise_id"])
    op.create_table("run_route",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("name_key", sa.String(320), nullable=False, unique=True),
        sa.Column("notes", sa.Text(), server_default="", nullable=False), *timestamps())
    op.create_table("run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("route_id", sa.Integer(), sa.ForeignKey("run_route.id"), nullable=False),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column("run_time", sa.Time(), nullable=True),
        sa.Column("distance_km", sa.Numeric(8, 3), nullable=False),
        sa.Column("elapsed_seconds", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        *timestamps(),
        sa.CheckConstraint("distance_km > 0 AND distance_km <= 1000", name="run_distance_range"),
        sa.CheckConstraint("elapsed_seconds > 0 AND elapsed_seconds <= 604800", name="run_duration_range"))
    op.create_index("ix_run_route_id", "run", ["route_id"])
    op.create_index("ix_run_run_date", "run", ["run_date"])


def downgrade():
    op.drop_table("run")
    op.drop_table("run_route")
    op.drop_table("workout_template_exercise")
    op.drop_table("workout_template")
    with op.batch_alter_table("exercise") as batch:
        batch.drop_column("is_favorite")
