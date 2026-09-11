"""Add explicit completion state to Lists."""
from alembic import op
import sqlalchemy as sa

revision = "b8e4c1d7f920"
down_revision = "a7d3f9c2b610"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("checklists", sa.Column("is_completed", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("checklists", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_checklists_is_completed", "checklists", ["is_completed"])
    op.create_index("ix_checklists_completed_at", "checklists", ["completed_at"])


def downgrade():
    op.drop_index("ix_checklists_completed_at", table_name="checklists")
    op.drop_index("ix_checklists_is_completed", table_name="checklists")
    op.drop_column("checklists", "completed_at")
    op.drop_column("checklists", "is_completed")
