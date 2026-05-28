"""Skills system, Org Roles, Proficiency Levels, Report Snapshots

Revision ID: 034
Revises: 033
Create Date: 2026-05-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Proficiency Levels ────────────────────────────────────────────────────
    op.create_table(
        "proficiency_levels",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("level_order", sa.SmallInteger(), nullable=False),
        sa.Column("label", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("tenant_id", "level_order", name="uq_prof_level_tenant_order"),
        sa.UniqueConstraint("tenant_id", "label", name="uq_prof_level_tenant_label"),
    )

    # ── Org Roles ─────────────────────────────────────────────────────────────
    op.create_table(
        "org_roles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("team_id", UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("is_archived", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_org_role_tenant_name"),
    )
    op.create_index("idx_org_roles_tenant", "org_roles", ["tenant_id"])

    # ── User Org Roles (junction — one active per user) ───────────────────────
    op.create_table(
        "user_org_roles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("axis_users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("org_role_id", UUID(as_uuid=True), sa.ForeignKey("org_roles.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("assigned_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
    )
    op.create_index("idx_user_org_roles_user", "user_org_roles", ["user_id"])

    # ── Add active_org_role_id shortcut to axis_users ─────────────────────────
    op.add_column(
        "axis_users",
        sa.Column("active_org_role_id", UUID(as_uuid=True),
                  sa.ForeignKey("org_roles.id", ondelete="SET NULL"),
                  nullable=True),
    )

    # ── Skill Categories ──────────────────────────────────────────────────────
    op.create_table(
        "skill_categories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_skill_cat_tenant_name"),
    )

    # ── Skills ────────────────────────────────────────────────────────────────
    op.create_table(
        "skills",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("category_id", UUID(as_uuid=True),
                  sa.ForeignKey("skill_categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_skill_tenant_name"),
    )
    op.create_index("idx_skills_tenant", "skills", ["tenant_id"])
    op.create_index("idx_skills_category", "skills", ["category_id"])

    # ── Org Role Skill Targets ────────────────────────────────────────────────
    op.create_table(
        "org_role_skill_targets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_role_id", UUID(as_uuid=True),
                  sa.ForeignKey("org_roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("skill_id", UUID(as_uuid=True),
                  sa.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_level_id", UUID(as_uuid=True),
                  sa.ForeignKey("proficiency_levels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("org_role_id", "skill_id", name="uq_role_skill_target"),
    )

    # ── Content Skill Tags ────────────────────────────────────────────────────
    op.create_table(
        "content_skill_tags",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("content_item_id", UUID(as_uuid=True),
                  sa.ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("skill_id", UUID(as_uuid=True),
                  sa.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level_id", UUID(as_uuid=True),
                  sa.ForeignKey("proficiency_levels.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.String(32), nullable=False),   # ai | manual | confirmed_ai
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("tagged_by", UUID(as_uuid=True),
                  sa.ForeignKey("axis_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("content_item_id", "skill_id", name="uq_content_skill_tag"),
    )
    op.create_index("idx_content_skill_tags_content", "content_skill_tags", ["content_item_id"])
    op.create_index("idx_content_skill_tags_skill", "content_skill_tags", ["skill_id"])

    # ── User Skill Progress ───────────────────────────────────────────────────
    op.create_table(
        "user_skill_progress",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("axis_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("skill_id", UUID(as_uuid=True),
                  sa.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("current_level_id", UUID(as_uuid=True),
                  sa.ForeignKey("proficiency_levels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_content_id", UUID(as_uuid=True),
                  sa.ForeignKey("content_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("earned_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_id", "skill_id", name="uq_user_skill_progress"),
    )
    op.create_index("idx_user_skill_progress_user", "user_skill_progress", ["user_id"])
    op.create_index("idx_user_skill_progress_skill", "user_skill_progress", ["skill_id"])

    # ── Report Snapshots ──────────────────────────────────────────────────────
    op.create_table(
        "report_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("report_type", sa.String(64), nullable=False),
        sa.Column("filters", JSONB(), nullable=True),
        sa.Column("data", JSONB(), nullable=False),
        sa.Column("generated_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True),
                  sa.ForeignKey("axis_users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("idx_report_snapshots_tenant_type",
                    "report_snapshots", ["tenant_id", "report_type"])

    # ── Leaderboard index optimisation ────────────────────────────────────────
    # Speeds up space leaderboard queries via space_accesses
    op.create_index(
        "idx_space_accesses_space_user",
        "space_access",
        ["space_id", "user_id"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("idx_space_accesses_space_user", "space_access", if_exists=True)
    op.drop_table("report_snapshots")
    op.drop_table("user_skill_progress")
    op.drop_table("content_skill_tags")
    op.drop_table("org_role_skill_targets")
    op.drop_table("skills")
    op.drop_table("skill_categories")
    op.drop_column("axis_users", "active_org_role_id")
    op.drop_table("user_org_roles")
    op.drop_table("org_roles")
    op.drop_table("proficiency_levels")
