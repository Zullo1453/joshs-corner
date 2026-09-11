"""Add standalone Lists and reusable List templates.

This is additive: it does not alter, backfill, or reinterpret existing records.
"""
from alembic import op
import sqlalchemy as sa

revision = "a7d3f9c2b610"
down_revision = "a9c4d7e1b250"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("checklists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("is_favorite", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_checklists_is_favorite", "checklists", ["is_favorite"])
    op.create_index("ix_checklists_is_archived", "checklists", ["is_archived"])
    op.create_table("list_sections",
        sa.Column("id", sa.Integer(), nullable=False), sa.Column("checklist_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False), sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["checklist_id"], ["checklists.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_list_sections_checklist_id", "list_sections", ["checklist_id"])
    op.create_table("list_items",
        sa.Column("id", sa.Integer(), nullable=False), sa.Column("checklist_id", sa.Integer(), nullable=False),
        sa.Column("section_id", sa.Integer(), nullable=True), sa.Column("text", sa.String(500), nullable=False),
        sa.Column("detail", sa.Text(), server_default="", nullable=False), sa.Column("is_completed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["checklist_id"], ["checklists.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["section_id"], ["list_sections.id"], ondelete="SET NULL"), sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (("ix_list_items_checklist_id", ["checklist_id"]), ("ix_list_items_section_id", ["section_id"]), ("ix_list_items_is_completed", ["is_completed"])):
        op.create_index(name, "list_items", columns)
    op.create_table("list_templates",
        sa.Column("id", sa.Integer(), nullable=False), sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False), sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.PrimaryKeyConstraint("id"),
    )
    op.create_table("list_template_sections",
        sa.Column("id", sa.Integer(), nullable=False), sa.Column("template_id", sa.Integer(), nullable=False), sa.Column("name", sa.String(160), nullable=False), sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["template_id"], ["list_templates.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_list_template_sections_template_id", "list_template_sections", ["template_id"])
    op.create_table("list_template_items",
        sa.Column("id", sa.Integer(), nullable=False), sa.Column("template_id", sa.Integer(), nullable=False), sa.Column("section_id", sa.Integer(), nullable=True), sa.Column("text", sa.String(500), nullable=False), sa.Column("detail", sa.Text(), server_default="", nullable=False), sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["template_id"], ["list_templates.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["section_id"], ["list_template_sections.id"], ondelete="SET NULL"), sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_list_template_items_template_id", "list_template_items", ["template_id"])
    op.create_index("ix_list_template_items_section_id", "list_template_items", ["section_id"])


def downgrade():
    for table in ("list_template_items", "list_template_sections", "list_templates", "list_items", "list_sections", "checklists"):
        op.drop_table(table)
