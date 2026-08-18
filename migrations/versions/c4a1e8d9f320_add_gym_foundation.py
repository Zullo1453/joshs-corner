"""Add Gym exercises, sessions, and individual workout sets.

Revision ID: c4a1e8d9f320
Revises: bb5f9a2c3d40
"""
from alembic import op
import sqlalchemy as sa


revision = "c4a1e8d9f320"
down_revision = "bb5f9a2c3d40"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "exercise",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("body_part", sa.String(length=30), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("body_part IN ('Chest', 'Back', 'Shoulders', 'Biceps', 'Triceps', 'Legs', 'Core', 'Other')", name="exercise_body_part_valid"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_exercise_active"), "exercise", ["active"], unique=False)
    op.create_index(op.f("ix_exercise_body_part"), "exercise", ["body_part"], unique=False)
    op.create_table(
        "workout_session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workout_date", sa.Date(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workout_session_started_at"), "workout_session", ["started_at"], unique=False)
    op.create_index(op.f("ix_workout_session_workout_date"), "workout_session", ["workout_date"], unique=False)
    op.create_table(
        "workout_exercise",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workout_session_id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercise.id"]),
        sa.ForeignKeyConstraint(["workout_session_id"], ["workout_session.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workout_session_id", "exercise_id", name="workout_exercise_session_exercise"),
    )
    op.create_index(op.f("ix_workout_exercise_exercise_id"), "workout_exercise", ["exercise_id"], unique=False)
    op.create_index(op.f("ix_workout_exercise_workout_session_id"), "workout_exercise", ["workout_session_id"], unique=False)
    op.create_table(
        "exercise_set",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workout_exercise_id", sa.Integer(), nullable=False),
        sa.Column("set_number", sa.Integer(), nullable=False),
        sa.Column("weight_kg", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("weight_kg >= 0 AND weight_kg <= 1000", name="exercise_set_weight_range"),
        sa.CheckConstraint("reps >= 1 AND reps <= 1000", name="exercise_set_reps_range"),
        sa.ForeignKeyConstraint(["workout_exercise_id"], ["workout_exercise.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workout_exercise_id", "set_number", name="exercise_set_workout_exercise_number"),
    )
    op.create_index(op.f("ix_exercise_set_workout_exercise_id"), "exercise_set", ["workout_exercise_id"], unique=False)


def downgrade():
    op.drop_table("exercise_set")
    op.drop_table("workout_exercise")
    op.drop_table("workout_session")
    op.drop_table("exercise")
