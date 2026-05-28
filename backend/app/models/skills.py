"""
Skills System, Org Roles & Report Snapshots — ORM models.

Tables (migration 034):
  proficiency_levels     — org-defined scale (Awareness / Working / Expert, customisable)
  org_roles              — job roles within a tenant, optionally scoped to a team
  user_org_roles         — junction: which role(s) a user has held
  skill_categories       — grouping for the skill library
  skills                 — individual skills
  org_role_skill_targets — required proficiency level per role per skill
  content_skill_tags     — AI / manual skill tags on content items
  user_skill_progress    — learner's current attained level per skill
  report_snapshots       — cached / generated report data blobs
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from .tenant import Tenant
    from .user import AxisUser
    from .team import Team
    from .content import ContentItem


# ---------------------------------------------------------------------------
# Proficiency Levels
# ---------------------------------------------------------------------------

class ProficiencyLevel(UUIDPrimaryKeyMixin, Base):
    """
    Org-defined proficiency scale step.

    Default seed (added at tenant creation):
      1 — Awareness  — Basic knowledge, can recognise concepts
      2 — Working    — Can apply the skill with guidance
      3 — Expert     — Can teach and lead others

    Admin can rename labels, add up to 6 levels, reorder, and delete
    levels that carry no existing skill-target or progress data.
    """

    __tablename__ = "proficiency_levels"
    __table_args__ = (
        UniqueConstraint("tenant_id", "level_order", name="uq_prof_level_tenant_order"),
        UniqueConstraint("tenant_id", "label",       name="uq_prof_level_tenant_label"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    level_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    skill_targets: Mapped[list["OrgRoleSkillTarget"]] = relationship(
        "OrgRoleSkillTarget", back_populates="target_level", cascade="all, delete-orphan"
    )
    content_skill_tags: Mapped[list["ContentSkillTag"]] = relationship(
        "ContentSkillTag", back_populates="level"
    )
    user_skill_progress: Mapped[list["UserSkillProgress"]] = relationship(
        "UserSkillProgress", back_populates="current_level"
    )

    def __repr__(self) -> str:
        return f"<ProficiencyLevel {self.level_order}:{self.label} tenant={self.tenant_id}>"


# ---------------------------------------------------------------------------
# Org Roles
# ---------------------------------------------------------------------------

class OrgRole(UUIDPrimaryKeyMixin, Base):
    """
    A job function / seniority level within the organisation.

    team_id is nullable — general roles (e.g. 'New Joiner') have no team.
    Seeded defaults: New Joiner, Team Member, Team Lead, Manager, Director.
    """

    __tablename__ = "org_roles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_org_role_tenant_name"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    team: Mapped[Optional["Team"]] = relationship("Team")
    user_org_roles: Mapped[list["UserOrgRole"]] = relationship(
        "UserOrgRole", back_populates="org_role", cascade="all, delete-orphan"
    )
    skill_targets: Mapped[list["OrgRoleSkillTarget"]] = relationship(
        "OrgRoleSkillTarget", back_populates="org_role", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<OrgRole '{self.name}' tenant={self.tenant_id}>"


class UserOrgRole(UUIDPrimaryKeyMixin, Base):
    """
    Junction: user ↔ org role.

    is_active=True marks the user's *current* role.
    Previous roles remain in history with is_active=False.
    Only one active row per user should exist (enforced by application logic).
    """

    __tablename__ = "user_org_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("axis_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    org_role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("org_roles.id", ondelete="CASCADE"),
        nullable=False,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)

    # Relationships
    user: Mapped["AxisUser"] = relationship("AxisUser")
    org_role: Mapped["OrgRole"] = relationship("OrgRole", back_populates="user_org_roles")

    def __repr__(self) -> str:
        return f"<UserOrgRole user={self.user_id} role={self.org_role_id} active={self.is_active}>"


# ---------------------------------------------------------------------------
# Skill Categories + Skills
# ---------------------------------------------------------------------------

class SkillCategory(UUIDPrimaryKeyMixin, Base):
    """
    Top-level grouping for the skill library.
    Examples: 'Data & Analytics', 'Leadership', 'Communication'
    """

    __tablename__ = "skill_categories"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_skill_cat_tenant_name"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    skills: Mapped[list["Skill"]] = relationship(
        "Skill", back_populates="category", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<SkillCategory '{self.name}' tenant={self.tenant_id}>"


class Skill(UUIDPrimaryKeyMixin, Base):
    """
    A single learnable skill within the tenant's library.
    Examples: 'Python', 'Active Listening', 'Project Management'
    """

    __tablename__ = "skills"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_skill_tenant_name"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skill_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    category: Mapped[Optional["SkillCategory"]] = relationship(
        "SkillCategory", back_populates="skills"
    )
    role_targets: Mapped[list["OrgRoleSkillTarget"]] = relationship(
        "OrgRoleSkillTarget", back_populates="skill", cascade="all, delete-orphan"
    )
    content_tags: Mapped[list["ContentSkillTag"]] = relationship(
        "ContentSkillTag", back_populates="skill", cascade="all, delete-orphan"
    )
    user_progress: Mapped[list["UserSkillProgress"]] = relationship(
        "UserSkillProgress", back_populates="skill", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Skill '{self.name}' tenant={self.tenant_id}>"


# ---------------------------------------------------------------------------
# Org Role ↔ Skill Targets
# ---------------------------------------------------------------------------

class OrgRoleSkillTarget(UUIDPrimaryKeyMixin, Base):
    """
    Required proficiency level for a specific skill within an org role.

    Example:
      OrgRole='Junior Engineer'  Skill='Python'  target_level='Working'
    """

    __tablename__ = "org_role_skill_targets"
    __table_args__ = (
        UniqueConstraint("org_role_id", "skill_id", name="uq_role_skill_target"),
    )

    org_role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("org_roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_level_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("proficiency_levels.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    org_role: Mapped["OrgRole"] = relationship("OrgRole", back_populates="skill_targets")
    skill: Mapped["Skill"] = relationship("Skill", back_populates="role_targets")
    target_level: Mapped["ProficiencyLevel"] = relationship(
        "ProficiencyLevel", back_populates="skill_targets"
    )

    def __repr__(self) -> str:
        return f"<OrgRoleSkillTarget role={self.org_role_id} skill={self.skill_id}>"


# ---------------------------------------------------------------------------
# Content Skill Tags
# ---------------------------------------------------------------------------

class ContentSkillTag(UUIDPrimaryKeyMixin, Base):
    """
    Skill tag applied to a content item.

    source values:
      'ai'           — tagged by AI auto-detect (confidence < 1.0)
      'manual'       — tagged manually by admin / creator
      'confirmed_ai' — AI tag reviewed and confirmed by a human
    """

    __tablename__ = "content_skill_tags"
    __table_args__ = (
        UniqueConstraint("content_item_id", "skill_id", name="uq_content_skill_tag"),
    )

    content_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    level_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("proficiency_levels.id", ondelete="SET NULL"),
        nullable=True,
    )
    # 'ai' | 'manual' | 'confirmed_ai'
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    tagged_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("axis_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    content_item: Mapped["ContentItem"] = relationship("ContentItem")
    skill: Mapped["Skill"] = relationship("Skill", back_populates="content_tags")
    level: Mapped[Optional["ProficiencyLevel"]] = relationship(
        "ProficiencyLevel", back_populates="content_skill_tags"
    )
    tagger: Mapped[Optional["AxisUser"]] = relationship("AxisUser", foreign_keys=[tagged_by])

    def __repr__(self) -> str:
        return f"<ContentSkillTag content={self.content_item_id} skill={self.skill_id} src={self.source}>"


# ---------------------------------------------------------------------------
# User Skill Progress
# ---------------------------------------------------------------------------

class UserSkillProgress(UUIDPrimaryKeyMixin, Base):
    """
    Learner's current attained proficiency level for a skill.

    One row per (user, skill). Updated upward-only when content is completed
    (never auto-downgraded). source_content_id records which content item
    last caused an upgrade.
    """

    __tablename__ = "user_skill_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "skill_id", name="uq_user_skill_progress"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("axis_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    current_level_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("proficiency_levels.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_content_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    earned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["AxisUser"] = relationship("AxisUser")
    skill: Mapped["Skill"] = relationship("Skill", back_populates="user_progress")
    current_level: Mapped["ProficiencyLevel"] = relationship(
        "ProficiencyLevel", back_populates="user_skill_progress"
    )
    source_content: Mapped[Optional["ContentItem"]] = relationship("ContentItem")

    def __repr__(self) -> str:
        return f"<UserSkillProgress user={self.user_id} skill={self.skill_id} level={self.current_level_id}>"


# ---------------------------------------------------------------------------
# Report Snapshots
# ---------------------------------------------------------------------------

class ReportSnapshot(UUIDPrimaryKeyMixin, Base):
    """
    Cached / server-generated report data stored as JSONB.

    Used by:
      - Scheduled report generation (Celery beat task)
      - On-demand PDF export (stored so PDF can be re-downloaded without re-query)

    expires_at=NULL means the snapshot never auto-expires.
    """

    __tablename__ = "report_snapshots"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    report_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    filters: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("axis_users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    creator: Mapped[Optional["AxisUser"]] = relationship("AxisUser")

    def __repr__(self) -> str:
        return f"<ReportSnapshot type={self.report_type} tenant={self.tenant_id}>"
