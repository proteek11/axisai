"""012_departments_and_space_access

Departments feature:
  • departments          — named user groups per tenant
  • department_members   — many-to-many: user ↔ department
  • space_access         — extend with department_id + granted_by columns
                          make user_id nullable (was NOT NULL)
                          add uq_space_department constraint

Revision ID: 012
Revises: 011
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Create departments table ───────────────────────────────────────────
    op.create_table(
        "departments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("axis_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_departments_tenant_id", "departments", ["tenant_id"])
    op.create_index("ix_departments_created_by", "departments", ["created_by"])

    # ── 2. Create department_members table ────────────────────────────────────
    op.create_table(
        "department_members",
        sa.Column(
            "department_id",
            UUID(as_uuid=True),
            sa.ForeignKey("departments.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("axis_users.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "added_by",
            UUID(as_uuid=True),
            sa.ForeignKey("axis_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("department_id", "user_id", name="uq_dept_member"),
    )

    # ── 3. Extend space_access ────────────────────────────────────────────────

    # 3a. Make user_id nullable (was NOT NULL)
    op.alter_column(
        "space_access",
        "user_id",
        existing_type=UUID(as_uuid=True),
        nullable=True,
    )

    # 3b. Add department_id column
    op.add_column(
        "space_access",
        sa.Column(
            "department_id",
            UUID(as_uuid=True),
            sa.ForeignKey("departments.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("ix_space_access_department_id", "space_access", ["department_id"])

    # 3c. Add granted_by column
    op.add_column(
        "space_access",
        sa.Column(
            "granted_by",
            UUID(as_uuid=True),
            sa.ForeignKey("axis_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # 3d. Add unique constraint for department grants
    op.create_unique_constraint(
        "uq_space_department",
        "space_access",
        ["space_id", "department_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_space_department", "space_access", type_="unique")
    op.drop_index("ix_space_access_department_id", table_name="space_access")
    op.drop_column("space_access", "granted_by")
    op.drop_column("space_access", "department_id")
    op.alter_column(
        "space_access",
        "user_id",
        existing_type=UUID(as_uuid=True),
        nullable=False,
    )
    op.drop_table("department_members")
    op.drop_index("ix_departments_created_by", table_name="departments")
    op.drop_index("ix_departments_tenant_id", table_name="departments")
    op.drop_table("departments")
