"""Add generation settings to content_items and space_items

Adds:
  content_items:
    - quiz_count         INT DEFAULT 10  (initial quiz questions to generate)
    - flashcard_count    INT DEFAULT 10  (initial flashcards to generate)

  space_items:
    - allow_learner_regen   BOOL DEFAULT false
    - max_quiz_count        INT  DEFAULT 20
    - max_flashcard_count   INT  DEFAULT 20
"""
from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── content_items: initial generation counts ───────────────────────────
    op.add_column("content_items",
        sa.Column("quiz_count", sa.Integer, nullable=False, server_default="10"))
    op.add_column("content_items",
        sa.Column("flashcard_count", sa.Integer, nullable=False, server_default="10"))

    # ── space_items: per-item learner regen controls ───────────────────────
    op.add_column("space_items",
        sa.Column("allow_learner_regen", sa.Boolean, nullable=False, server_default="false"))
    op.add_column("space_items",
        sa.Column("max_quiz_count", sa.Integer, nullable=False, server_default="20"))
    op.add_column("space_items",
        sa.Column("max_flashcard_count", sa.Integer, nullable=False, server_default="20"))


def downgrade() -> None:
    op.drop_column("space_items", "max_flashcard_count")
    op.drop_column("space_items", "max_quiz_count")
    op.drop_column("space_items", "allow_learner_regen")
    op.drop_column("content_items", "flashcard_count")
    op.drop_column("content_items", "quiz_count")
