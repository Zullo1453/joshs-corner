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

    connection = op.get_bind()
    legacy_rows = connection.execute(
        sa.text("SELECT id, is_completed, completed_at, created_at FROM todo")
    ).mappings().all()
    for row in legacy_rows:
        if row["is_completed"]:
            # Completed legacy tasks have a reliable completion timestamp but no
            # supported scheduled date, so preserve them as archived history.
            connection.execute(
                sa.text("UPDATE todo SET current_location='archived', status='completed', archived_at=:completed_at WHERE id=:id"),
                {"id": row["id"], "completed_at": row["completed_at"]},
            )
            event_type = "completed"
            occurred_at = row["completed_at"] or row["created_at"]
        else:
            # No due-date existed in the legacy schema; incomplete tasks become
            # unscheduled Backlog tasks rather than being assigned a guessed day.
            connection.execute(
                sa.text("UPDATE todo SET current_location='backlog', status='active' WHERE id=:id"),
                {"id": row["id"]},
            )
            event_type = "created_backlog"
            occurred_at = row["created_at"]
        connection.execute(
            sa.text("INSERT INTO todo_activity (todo_id, event_type, occurred_at, metadata_json) VALUES (:todo_id, :event_type, :occurred_at, :metadata_json)"),
            {"todo_id": row["id"], "event_type": event_type, "occurred_at": occurred_at, "metadata_json": '{"legacy": true}'},
        )


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
