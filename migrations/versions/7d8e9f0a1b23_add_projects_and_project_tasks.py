"""Add Projects and link normal To-Do records to their project.

Revision ID: 7d8e9f0a1b23
Revises: 6c7a8b9d0e12
"""
from alembic import op
import sqlalchemy as sa


revision = "7d8e9f0a1b23"
down_revision = "6c7a8b9d0e12"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "project",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_status", "project", ["status"], unique=False)
    op.create_index("ix_project_target_date", "project", ["target_date"], unique=False)
    with op.batch_alter_table("todo", schema=None) as batch_op:
        batch_op.add_column(sa.Column("project_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_todo_project_id_project", "project", ["project_id"], ["id"])
        batch_op.create_index("ix_todo_project_id", ["project_id"], unique=False)
    op.create_table(
        "project_activity",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("todo_id", sa.Integer(), nullable=True),
        sa.Column("source_date", sa.Date(), nullable=True),
        sa.Column("destination_date", sa.Date(), nullable=True),
        sa.Column("metadata_json", sa.Text(), server_default="", nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["todo_id"], ["todo.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("project_id", "event_type", "occurred_at", "todo_id", "source_date", "destination_date"):
        op.create_index(f"ix_project_activity_{column}", "project_activity", [column], unique=False)


def downgrade():
    for column in ("destination_date", "source_date", "todo_id", "occurred_at", "event_type", "project_id"):
        op.drop_index(f"ix_project_activity_{column}", table_name="project_activity")
    op.drop_table("project_activity")
    with op.batch_alter_table("todo", schema=None) as batch_op:
        batch_op.drop_index("ix_todo_project_id")
        batch_op.drop_constraint("fk_todo_project_id_project", type_="foreignkey")
        batch_op.drop_column("project_id")
    op.drop_index("ix_project_target_date", table_name="project")
    op.drop_index("ix_project_status", table_name="project")
    op.drop_table("project")
