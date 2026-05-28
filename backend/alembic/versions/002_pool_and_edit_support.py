"""Pool and edit support: flashcard_items, glossary_terms, ai_outputs edits, quiz_questions pool fields

Revision ID: 002
Revises: 001
Create Date: 2026-03-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. flashcard_items — dedicated pool table (previously JSON blob in ai_outputs)
    # -------------------------------------------------------------------------
    op.create_table(
        "flashcard_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("content_item_id", UUID(as_uuid=True), sa.ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ai_output_id", UUID(as_uuid=True), sa.ForeignKey("ai_outputs.id", ondelete="SET NULL"), nullable=True),
        # Card content
        sa.Column("front", sa.Text, nullable=False),
        sa.Column("back", sa.Text, nullable=False),
        sa.Column("hint", sa.Text, nullable=True),
        sa.Column("card_type", sa.String(50), nullable=True),        # definition|application|comparison|cause_effect|process
        sa.Column("difficulty", sa.String(20), nullable=True),       # easy|medium|hard
        sa.Column("topic", sa.String(255), nullable=True),
        # Pool management
        sa.Column("source", sa.String(20), nullable=False, server_default="generated"),  # generated|manual
        sa.Column("generation_batch", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        # Manual entry tracking
        sa.Column("manually_added_by", sa.BigInteger, nullable=True),  # moodle_user_id
        # Qdrant reference for semantic dedup
        sa.Column("qdrant_id", UUID(as_uuid=True), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_flashcard_items_content_item_id", "flashcard_items", ["content_item_id"])
    op.create_index("ix_flashcard_items_tenant_id", "flashcard_items", ["tenant_id"])
    op.create_index("ix_flashcard_items_source", "flashcard_items", ["source"])
    op.create_index("ix_flashcard_items_is_active", "flashcard_items", ["is_active"])
    op.create_index("ix_flashcard_items_generation_batch", "flashcard_items", ["generation_batch"])

    # -------------------------------------------------------------------------
    # 2. glossary_terms — dedicated pool table (previously JSON blob in ai_outputs)
    # -------------------------------------------------------------------------
    op.create_table(
        "glossary_terms",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("content_item_id", UUID(as_uuid=True), sa.ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ai_output_id", UUID(as_uuid=True), sa.ForeignKey("ai_outputs.id", ondelete="SET NULL"), nullable=True),
        # Term content
        sa.Column("term", sa.String(255), nullable=False),
        sa.Column("definition", sa.Text, nullable=False),
        sa.Column("context", sa.Text, nullable=True),               # example sentence from source
        sa.Column("related_terms", JSONB, nullable=True),           # list of related term strings
        sa.Column("category", sa.String(50), nullable=True),        # concept|process|tool|formula|principle|other
        # Pool management
        sa.Column("source", sa.String(20), nullable=False, server_default="generated"),  # generated|manual
        sa.Column("generation_batch", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        # Manual entry tracking
        sa.Column("manually_added_by", sa.BigInteger, nullable=True),  # moodle_user_id
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_glossary_terms_content_item_id", "glossary_terms", ["content_item_id"])
    op.create_index("ix_glossary_terms_tenant_id", "glossary_terms", ["tenant_id"])
    op.create_index("ix_glossary_terms_term", "glossary_terms", ["term"])
    op.create_index("ix_glossary_terms_source", "glossary_terms", ["source"])
    op.create_index("ix_glossary_terms_is_active", "glossary_terms", ["is_active"])

    # -------------------------------------------------------------------------
    # 3. ai_outputs — add teacher edit fields (for Summary, and fallback for others)
    # -------------------------------------------------------------------------
    op.add_column("ai_outputs", sa.Column(
        "edited_content",
        JSONB,
        nullable=True,
        comment="Teacher-edited override of payload. Served instead of payload when present."
    ))
    op.add_column("ai_outputs", sa.Column(
        "is_teacher_edited",
        sa.Boolean,
        nullable=False,
        server_default="false",
        comment="True when teacher has saved edits to this output"
    ))
    op.add_column("ai_outputs", sa.Column(
        "last_edited_by",
        sa.BigInteger,
        nullable=True,
        comment="moodle_user_id of last teacher to edit"
    ))
    op.add_column("ai_outputs", sa.Column(
        "last_edited_at",
        sa.DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of last teacher edit"
    ))

    # -------------------------------------------------------------------------
    # 4. quiz_questions — add pool management fields (source, generation_batch,
    #    manually_added_by, qdrant_id) to match flashcard_items pattern
    # -------------------------------------------------------------------------
    op.add_column("quiz_questions", sa.Column(
        "source",
        sa.String(20),
        nullable=False,
        server_default="generated",
        comment="generated | manual"
    ))
    op.add_column("quiz_questions", sa.Column(
        "generation_batch",
        sa.Integer,
        nullable=False,
        server_default="1",
        comment="Which regenerate pass created this item (1 = first, 2 = first regen, etc.)"
    ))
    op.add_column("quiz_questions", sa.Column(
        "manually_added_by",
        sa.BigInteger,
        nullable=True,
        comment="moodle_user_id if source=manual"
    ))
    op.add_column("quiz_questions", sa.Column(
        "qdrant_id",
        UUID(as_uuid=True),
        nullable=True,
        comment="ID in axis_question_intelligence Qdrant collection for semantic dedup"
    ))

    op.create_index("ix_quiz_questions_source", "quiz_questions", ["source"])
    op.create_index("ix_quiz_questions_generation_batch", "quiz_questions", ["generation_batch"])


def downgrade() -> None:
    # Remove quiz_questions new columns
    op.drop_index("ix_quiz_questions_generation_batch", table_name="quiz_questions")
    op.drop_index("ix_quiz_questions_source", table_name="quiz_questions")
    op.drop_column("quiz_questions", "qdrant_id")
    op.drop_column("quiz_questions", "manually_added_by")
    op.drop_column("quiz_questions", "generation_batch")
    op.drop_column("quiz_questions", "source")

    # Remove ai_outputs new columns
    op.drop_column("ai_outputs", "last_edited_at")
    op.drop_column("ai_outputs", "last_edited_by")
    op.drop_column("ai_outputs", "is_teacher_edited")
    op.drop_column("ai_outputs", "edited_content")

    # Drop new tables
    op.drop_table("glossary_terms")
    op.drop_table("flashcard_items")
