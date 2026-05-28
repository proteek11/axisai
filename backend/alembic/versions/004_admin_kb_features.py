"""004_admin_kb_features

Adds:
  - tenants: feature flags + rate limit columns
  - user_token_overrides: new table (per-user limit overrides)
  - chat_sessions: chat_mode column
  - kb_items: new table (admin support documents)
  - processing_jobs: content_item_id nullable (for KB_INGEST jobs)

Revision ID: 004
Revises: 003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. tenants — feature flags ────────────────────────────────────────────
    op.add_column("tenants", sa.Column("feature_summary",     sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("tenants", sa.Column("feature_glossary",    sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("tenants", sa.Column("feature_flashcards",  sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("tenants", sa.Column("feature_quiz",        sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("tenants", sa.Column("feature_faq",         sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("tenants", sa.Column("feature_infographic", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("tenants", sa.Column("feature_chatbot",     sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("tenants", sa.Column("feature_kb_chat",     sa.Boolean(), nullable=False, server_default="true"))

    # ── 2. tenants — rate limit columns ──────────────────────────────────────
    op.add_column("tenants", sa.Column("chat_session_msg_limit",  sa.Integer(), nullable=False, server_default="50"))
    op.add_column("tenants", sa.Column("chat_daily_msg_limit",    sa.Integer(), nullable=False, server_default="200"))
    op.add_column("tenants", sa.Column("chat_monthly_msg_limit",  sa.Integer(), nullable=False, server_default="2000"))
    op.add_column("tenants", sa.Column("token_monthly_limit",     sa.Integer(), nullable=False, server_default="5000000"))

    # ── 3. user_token_overrides — new table ───────────────────────────────────
    op.create_table(
        "user_token_overrides",
        sa.Column("id",                     UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id",              UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("moodle_user_id",         sa.Integer(), nullable=False),
        sa.Column("chat_session_msg_limit", sa.Integer(), nullable=True),
        sa.Column("chat_daily_msg_limit",   sa.Integer(), nullable=True),
        sa.Column("chat_monthly_msg_limit", sa.Integer(), nullable=True),
        sa.Column("token_monthly_limit",    sa.Integer(), nullable=True),
        sa.Column("note",                   sa.String(500), nullable=True),
        sa.Column("set_by_moodle_user_id",  sa.Integer(), nullable=True),
        sa.Column("created_at",             sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at",             sa.DateTime(timezone=True), onupdate=sa.func.now(), nullable=True),
    )
    op.create_index("ix_user_token_overrides_tenant_id",      "user_token_overrides", ["tenant_id"])
    op.create_index("ix_user_token_overrides_moodle_user_id", "user_token_overrides", ["moodle_user_id"])
    op.create_index(
        "ix_user_token_overrides_tenant_user",
        "user_token_overrides",
        ["tenant_id", "moodle_user_id"],
        unique=True,
    )

    # ── 4. chat_sessions — add chat_mode ─────────────────────────────────────
    op.add_column(
        "chat_sessions",
        sa.Column("chat_mode", sa.String(20), nullable=False, server_default="study",
                  comment="study|support|learning — routes RAG to correct vector collection"),
    )
    op.create_index("ix_chat_sessions_chat_mode", "chat_sessions", ["chat_mode"])

    # ── 5. kb_items — new table ───────────────────────────────────────────────
    op.create_table(
        "kb_items",
        sa.Column("id",                          UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id",                   UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title",                        sa.String(512), nullable=False),
        sa.Column("doc_type",                     sa.String(30), nullable=False, server_default="support"),
        sa.Column("source_url",                   sa.String(2048), nullable=True),
        sa.Column("file_path",                    sa.String(2048), nullable=True),
        sa.Column("content_hash",                 sa.String(64), nullable=True),
        sa.Column("status",                       sa.String(20), nullable=False, server_default="pending"),
        sa.Column("chunk_count",                  sa.Integer(), nullable=False, server_default="0"),
        sa.Column("word_count",                   sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message",                sa.Text(), nullable=True),
        sa.Column("is_active",                    sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("uploaded_by_moodle_user_id",  sa.Integer(), nullable=True),
        sa.Column("processing_metadata",          JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at",                   sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at",                   sa.DateTime(timezone=True), onupdate=sa.func.now(), nullable=True),
    )
    op.create_index("ix_kb_items_tenant_id", "kb_items", ["tenant_id"])
    op.create_index("ix_kb_items_doc_type",  "kb_items", ["doc_type"])
    op.create_index("ix_kb_items_status",    "kb_items", ["status"])
    op.create_index("ix_kb_items_is_active", "kb_items", ["is_active"])

    # ── 6. processing_jobs — make content_item_id nullable ───────────────────
    # Required for KB_INGEST and STRUCTURED_INGEST jobs that don't belong
    # to a content_item directly.
    op.alter_column(
        "processing_jobs",
        "content_item_id",
        existing_type=UUID(as_uuid=True),
        nullable=True,
    )

    # ── 7. Add new job types to the enum-like column (VARCHAR — no enum type) ─
    # job_type is stored as VARCHAR(30) so no enum migration needed.
    # The new values (kb_ingest, structured_ingest) are accepted automatically.


def downgrade() -> None:
    # Reverse order
    op.alter_column("processing_jobs", "content_item_id", existing_type=UUID(as_uuid=True), nullable=False)

    op.drop_index("ix_kb_items_is_active", table_name="kb_items")
    op.drop_index("ix_kb_items_status", table_name="kb_items")
    op.drop_index("ix_kb_items_doc_type", table_name="kb_items")
    op.drop_index("ix_kb_items_tenant_id", table_name="kb_items")
    op.drop_table("kb_items")

    op.drop_index("ix_chat_sessions_chat_mode", table_name="chat_sessions")
    op.drop_column("chat_sessions", "chat_mode")

    op.drop_index("ix_user_token_overrides_tenant_user", table_name="user_token_overrides")
    op.drop_index("ix_user_token_overrides_moodle_user_id", table_name="user_token_overrides")
    op.drop_index("ix_user_token_overrides_tenant_id", table_name="user_token_overrides")
    op.drop_table("user_token_overrides")

    for col in [
        "token_monthly_limit", "chat_monthly_msg_limit", "chat_daily_msg_limit",
        "chat_session_msg_limit", "feature_kb_chat", "feature_chatbot",
        "feature_infographic", "feature_faq", "feature_quiz",
        "feature_flashcards", "feature_glossary", "feature_summary",
    ]:
        op.drop_column("tenants", col)
