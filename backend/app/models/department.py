"""
Department models — user grouping for Learning Space access control.

A Department is a named group of AxisUsers within a tenant.
A Learning Space can be shared with an entire department (all members get access)
or with individual users directly (existing SpaceAccess with user_id).

Tables:
  departments         — named groups per tenant
  department_members  — many-to-many: user ↔ department
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


class Department(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A named group of users within a tenant."""

    __tablename__ = "departments"

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
    members: Mapped[list["DepartmentMember"]] = relationship(
        "DepartmentMember", back_populates="department", cascade="all, delete-orphan"
    )
    creator: Mapped["AxisUser | None"] = relationship(
        "AxisUser", foreign_keys=[created_by]
    )

    def __repr__(self) -> str:
        return f"<Department '{self.name}' tenant={self.tenant_id}>"


class DepartmentMember(Base):
    """Maps a user to a department. Many-to-many join table."""

    __tablename__ = "department_members"
    __table_args__ = (
        UniqueConstraint("department_id", "user_id", name="uq_dept_member"),
    )

    from sqlalchemy import func as _func
    added_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=_func.now(), nullable=False
    )

    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="CASCADE"),
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
    department: Mapped["Department"] = relationship("Department", back_populates="members")
    user: Mapped["AxisUser"] = relationship("AxisUser", foreign_keys=[user_id])
    adder: Mapped["AxisUser | None"] = relationship("AxisUser", foreign_keys=[added_by])

    def __repr__(self) -> str:
        return f"<DepartmentMember dept={self.department_id} user={self.user_id}>"
