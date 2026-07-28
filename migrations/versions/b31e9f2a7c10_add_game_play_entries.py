"""Add dated game play entries.

Revision ID: b31e9f2a7c10
Revises: 070eaf1e0963
"""
from alembic import op
import sqlalchemy as sa

revision = "b31e9f2a7c10"
down_revision = "070eaf1e0963"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "game_play_entry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("played_on", sa.Date(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["game_journal.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_game_play_entry_game_id", "game_play_entry", ["game_id"])
    op.create_index("ix_game_play_entry_played_on", "game_play_entry", ["played_on"])


def downgrade():
    op.drop_index("ix_game_play_entry_played_on", table_name="game_play_entry")
    op.drop_index("ix_game_play_entry_game_id", table_name="game_play_entry")
    op.drop_table("game_play_entry")
