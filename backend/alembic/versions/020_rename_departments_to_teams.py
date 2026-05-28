"""Rename departments tables to teams

Revision ID: 020
Revises: 019
Creates: 2026-05-11
"""

from alembic import op

revision = '020'
down_revision = '019'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename tables
    op.rename_table('departments', 'teams')
    op.rename_table('department_members', 'team_members')

    # Rename indexes on teams table
    op.execute('ALTER INDEX IF EXISTS ix_departments_tenant_id RENAME TO ix_teams_tenant_id')
    op.execute('ALTER INDEX IF EXISTS ix_departments_created_by RENAME TO ix_teams_created_by')

    # Rename department_id column → team_id in space_access
    op.alter_column('space_access', 'department_id', new_column_name='team_id')

    # Rename constraint on space_access
    op.execute('ALTER TABLE space_access DROP CONSTRAINT IF EXISTS uq_space_department')
    op.create_unique_constraint('uq_space_team', 'space_access', ['space_id', 'team_id'])

    # Rename index on space_access.team_id
    op.execute('ALTER INDEX IF EXISTS ix_space_access_department_id RENAME TO ix_space_access_team_id')


def downgrade() -> None:
    op.alter_column('space_access', 'team_id', new_column_name='department_id')
    op.execute('ALTER TABLE space_access DROP CONSTRAINT IF EXISTS uq_space_team')
    op.create_unique_constraint('uq_space_department', 'space_access', ['space_id', 'department_id'])
    op.execute('ALTER INDEX IF EXISTS ix_space_access_team_id RENAME TO ix_space_access_department_id')

    op.rename_table('teams', 'departments')
    op.rename_table('team_members', 'department_members')

    op.execute('ALTER INDEX IF EXISTS ix_teams_tenant_id RENAME TO ix_departments_tenant_id')
    op.execute('ALTER INDEX IF EXISTS ix_teams_created_by RENAME TO ix_departments_created_by')
