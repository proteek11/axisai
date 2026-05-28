"""
Team models — user grouping for Learning Space access control.

A Team is a named group of AxisUsers within a tenant.
A Learning Space can be shared with an entire team (all members get access)
or with individual users directly (existing SpaceAccess with user_id).

Tables:
  teams         — named groups per tenant
  team_members  — many-to-many: user ↔ team
"""
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from .user import AxisUser
    from .tenant import Tenant


class Team(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A named group of users within a tenant."""

    __tablename__ = "teams"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("axis_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    members: Mapped[list["TeamMember"]] = relationship(
        "TeamMember", back_populates="team", cascade="all, delete-orphan"
    )
    creator: Mapped["AxisUser | None"] = relationship(
        "AxisUser", foreign_keys=[created_by]
    )

    def __repr__(self) -> str:
        return f"<Team '{self.name}' tenant={self.tenant_id}>"


class TeamMember(Base):
    """Maps a user to a team. Many-to-many join table."""

    __tablename__ = "team_members"
    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_dept_member"),
    )

    from sqlalchemy import func as _func
    added_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=_func.now(), nullable=False
    )

    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("axis_users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    added_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("axis_users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    team: Mapped["Team"] = relationship("Team", back_populates="members")
    user: Mapped["AxisUser"] = relationship("AxisUser", foreign_keys=[user_id])
    adder: Mapped["AxisUser | None"] = relationship("AxisUser", foreign_keys=[added_by])

    def __repr__(self) -> str:
        return f"<TeamMember dept={self.team_id} user={self.user_id}>"
