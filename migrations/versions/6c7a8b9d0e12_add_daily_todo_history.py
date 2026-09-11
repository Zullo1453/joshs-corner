"""Add dated To-Do lifecycle fields and auditable activity history.

Revision ID: 6c7a8b9d0e12
Revises: d51f6c8e9a32
"""
from alembic import op
import sqlalchemy as sa


revision = "6c7a8b9d0e12"
down_revision = "d51f6c8e9a32"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("todo", schema=None) as batch_op:
        batch_op.add_column(sa.Column("notes", sa.Text(), server_default="", nullable=False))
        batch_op.add_column(sa.Column("current_location", sa.String(length=20), server_default="backlog", nullable=False))
        batch_op.add_column(sa.Column("status", sa.String(length=20), server_default="active", nullable=False))
        batch_op.add_column(sa.Column("scheduled_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("original_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("carried_from_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("carry_count", sa.Integer(), server_default="0", nullable=False))
        batch_op.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("ix_todo_current_location", ["current_location"], unique=False)
        batch_op.create_index("ix_todo_status", ["status"], unique=False)
        batch_op.create_index("ix_todo_scheduled_date", ["scheduled_date"], unique=False)

    op.create_table(
        "todo_activity",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("todo_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_date", sa.Date(), nullable=True),
        sa.Column("destination_date", sa.Date(), nullable=True),
        sa.Column("metadata_json", sa.Text(), server_default="", nullable=False),
        sa.ForeignKeyConstraint(["todo_id"], ["todo.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_todo_activity_todo_id", "todo_activity", ["todo_id"], unique=False)
    op.create_index("ix_todo_activity_event_type", "todo_activity", ["event_type"], unique=False)
    op.create_index("ix_todo_activity_occurred_at", "todo_activity", ["occurred_at"], unique=False)
    op.create_index("ix_todo_activity_source_date", "todo_activity", ["source_date"], unique=False)
    op.create_index("ix_todo_activity_destination_date", "todo_activity", ["destination_date"], unique=False)

    # Set-based SQL is equivalent to the original row loop, works on SQLite
    # and PostgreSQL, and can be rendered by Alembic in offline mode.
    op.execute(sa.text(
        "UPDATE todo SET current_location='archived', status='completed', "
        "archived_at=completed_at WHERE is_completed"
    ))
    op.execute(sa.text(
        "UPDATE todo SET current_location='backlog', status='active' "
        "WHERE NOT is_completed"
    ))
    op.execute(sa.text(
        "INSERT INTO todo_activity "
        "(todo_id, event_type, occurred_at, metadata_json) "
        "SELECT id, "
        "CASE WHEN is_completed THEN 'completed' ELSE 'created_backlog' END, "
        "CASE WHEN is_completed THEN COALESCE(completed_at, created_at) ELSE created_at END, "
        "'{\"legacy\": true}' FROM todo"
    ))


def downgrade():
    op.drop_index("ix_todo_activity_destination_date", table_name="todo_activity")
    op.drop_index("ix_todo_activity_source_date", table_name="todo_activity")
    op.drop_index("ix_todo_activity_occurred_at", table_name="todo_activity")
    op.drop_index("ix_todo_activity_event_type", table_name="todo_activity")
    op.drop_index("ix_todo_activity_todo_id", table_name="todo_activity")
    op.drop_table("todo_activity")
    with op.batch_alter_table("todo", schema=None) as batch_op:
        batch_op.drop_index("ix_todo_scheduled_date")
        batch_op.drop_index("ix_todo_status")
        batch_op.drop_index("ix_todo_current_location")
        batch_op.drop_column("archived_at")
        batch_op.drop_column("carry_count")
        batch_op.drop_column("carried_from_date")
        batch_op.drop_column("original_date")
        batch_op.drop_column("scheduled_date")
        batch_op.drop_column("status")
        batch_op.drop_column("current_location")
        batch_op.drop_column("notes")
