"""Add auth security blocklist table.

Revision ID: e5b7c1a9d4f0
Revises: c9d5e2a1f4b7
Create Date: 2026-02-28 19:05:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5b7c1a9d4f0'
down_revision = 'c9d5e2a1f4b7'
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def _has_index(inspector, table_name, index_name):
    return any(index.get('name') == index_name for index in inspector.get_indexes(table_name))


def _has_fk_name(inspector, table_name, constraint_name):
    for foreign_key in inspector.get_foreign_keys(table_name):
        if foreign_key.get('name') == constraint_name:
            return True
    return False


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = 'auth_security_blocklist'

    if not _has_table(inspector, table_name):
        op.create_table(
            table_name,
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('identifier_type', sa.String(length=16), nullable=False),
            sa.Column('identifier_value', sa.String(length=255), nullable=False),
            sa.Column('reason', sa.String(length=255), nullable=True),
            sa.Column('created_by_user_id', sa.Integer(), nullable=True),
            sa.Column('expires_at', sa.DateTime(), nullable=True),
            sa.Column('revoked_at', sa.DateTime(), nullable=True),
            sa.Column('metadata_json', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(
                ['created_by_user_id'],
                ['users.id'],
                name='fk_auth_security_blocklist_created_by_user_id_users',
            ),
            sa.PrimaryKeyConstraint('id'),
        )

    inspector = sa.inspect(bind)
    if _has_table(inspector, table_name):
        if not _has_index(inspector, table_name, 'ix_auth_security_blocklist_identifier_type'):
            op.create_index(
                'ix_auth_security_blocklist_identifier_type',
                table_name,
                ['identifier_type'],
                unique=False,
            )
        if not _has_index(inspector, table_name, 'ix_auth_security_blocklist_identifier_value'):
            op.create_index(
                'ix_auth_security_blocklist_identifier_value',
                table_name,
                ['identifier_value'],
                unique=False,
            )
        if not _has_index(inspector, table_name, 'ix_auth_security_blocklist_created_by_user_id'):
            op.create_index(
                'ix_auth_security_blocklist_created_by_user_id',
                table_name,
                ['created_by_user_id'],
                unique=False,
            )
        if not _has_index(inspector, table_name, 'ix_auth_security_blocklist_expires_at'):
            op.create_index('ix_auth_security_blocklist_expires_at', table_name, ['expires_at'], unique=False)
        if not _has_index(inspector, table_name, 'ix_auth_security_blocklist_revoked_at'):
            op.create_index('ix_auth_security_blocklist_revoked_at', table_name, ['revoked_at'], unique=False)
        if not _has_index(inspector, table_name, 'ix_auth_security_blocklist_created_at'):
            op.create_index('ix_auth_security_blocklist_created_at', table_name, ['created_at'], unique=False)
        if not _has_fk_name(inspector, table_name, 'fk_auth_security_blocklist_created_by_user_id_users'):
            op.create_foreign_key(
                'fk_auth_security_blocklist_created_by_user_id_users',
                table_name,
                'users',
                ['created_by_user_id'],
                ['id'],
            )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = 'auth_security_blocklist'
    if not _has_table(inspector, table_name):
        return

    if _has_index(inspector, table_name, 'ix_auth_security_blocklist_created_at'):
        op.drop_index('ix_auth_security_blocklist_created_at', table_name=table_name)
    if _has_index(inspector, table_name, 'ix_auth_security_blocklist_revoked_at'):
        op.drop_index('ix_auth_security_blocklist_revoked_at', table_name=table_name)
    if _has_index(inspector, table_name, 'ix_auth_security_blocklist_expires_at'):
        op.drop_index('ix_auth_security_blocklist_expires_at', table_name=table_name)
    if _has_index(inspector, table_name, 'ix_auth_security_blocklist_created_by_user_id'):
        op.drop_index('ix_auth_security_blocklist_created_by_user_id', table_name=table_name)
    if _has_index(inspector, table_name, 'ix_auth_security_blocklist_identifier_value'):
        op.drop_index('ix_auth_security_blocklist_identifier_value', table_name=table_name)
    if _has_index(inspector, table_name, 'ix_auth_security_blocklist_identifier_type'):
        op.drop_index('ix_auth_security_blocklist_identifier_type', table_name=table_name)
    if _has_fk_name(inspector, table_name, 'fk_auth_security_blocklist_created_by_user_id_users'):
        op.drop_constraint('fk_auth_security_blocklist_created_by_user_id_users', table_name, type_='foreignkey')

    op.drop_table(table_name)
