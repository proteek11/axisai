"""014_avatar_and_path_sections

Adds:
  • avatar_url TEXT NULL  on axis_users        (profile picture upload — #42)
  • section_title TEXT NULL on space_items     (learning path sections — #43)
  • position ordering already exists on space_items; no change needed there
"""

from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── axis_users: profile picture URL ───────────────────────────────────────
    op.add_column(
        "axis_users",
        sa.Column("avatar_url", sa.Text(), nullable=True),
    )

    # ── space_items: section label for learning path builder ──────────────────
    op.add_column(
        "space_items",
        sa.Column("section_title", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("space_items", "section_title")
    op.drop_column("axis_users", "avatar_url")
