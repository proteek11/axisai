"""Rename team_members.department_id to team_id

Revision ID: 021
Revises: 020
Creates: 2026-05-11
"""

from alembic import op

revision = '021'
down_revision = '020'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename department_id → team_id in team_members table
    # (migration 020 renamed the table but missed this column)
    op.alter_column('team_members', 'department_id', new_column_name='team_id')

    # Rename any FK constraint referencing the old column name
    op.execute("""
        DO $$
        DECLARE
            r RECORD;
        BEGIN
            FOR r IN
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = 'team_members'::regclass
                  AND conname ILIKE '%department%'
            LOOP
                EXECUTE 'ALTER TABLE team_members RENAME CONSTRAINT ' || quote_ident(r.conname)
                     || ' TO ' || quote_ident(REPLACE(r.conname, 'department', 'team'));
            END LOOP;
        END $$;
    """)

    # Rename index if it exists
    op.execute('ALTER INDEX IF EXISTS ix_team_members_department_id RENAME TO ix_team_members_team_id')


def downgrade() -> None:
    op.execute('ALTER INDEX IF EXISTS ix_team_members_team_id RENAME TO ix_team_members_department_id')
    op.alter_column('team_members', 'team_id', new_column_name='department_id')
