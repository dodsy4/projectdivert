"""Add auth lifecycle tables and email verification column.

Revision ID: a8e3d1b4c5f6
Revises: f6d4a8c2b9e1
Create Date: 2026-02-28 12:20:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a8e3d1b4c5f6'
down_revision = 'f6d4a8c2b9e1'
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name, column_name):
    return any(column.get('name') == column_name for column in inspector.get_columns(table_name))


def _has_index(inspector, table_name, index_name):
    return any(index.get('name') == index_name for index in inspector.get_indexes(table_name))


def _has_fk(inspector, table_name, constrained_column):
    for foreign_key in inspector.get_foreign_keys(table_name):
        columns = foreign_key.get('constrained_columns') or []
        if constrained_column in columns:
            return True
    return False


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    users_table = 'users'
    users_verified_index = 'ix_users_email_verified_at'
    if _has_table(inspector, users_table) and not _has_column(inspector, users_table, 'email_verified_at'):
        op.add_column(users_table, sa.Column('email_verified_at', sa.DateTime(), nullable=True))

    inspector = sa.inspect(bind)
    if _has_table(inspector, users_table) and not _has_index(inspector, users_table, users_verified_index):
        op.create_index(users_verified_index, users_table, ['email_verified_at'], unique=False)

    table_name = 'auth_lifecycle_tokens'
    if not _has_table(inspector, table_name):
        op.create_table(
            table_name,
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('token_id', sa.String(length=64), nullable=False),
            sa.Column('token_type', sa.String(length=32), nullable=False),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('used_at', sa.DateTime(), nullable=True),
            sa.Column('revoked_at', sa.DateTime(), nullable=True),
            sa.Column('metadata_json', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )

    inspector = sa.inspect(bind)
    if _has_table(inspector, table_name):
        if not _has_index(inspector, table_name, 'ix_auth_lifecycle_tokens_user_id'):
            op.create_index('ix_auth_lifecycle_tokens_user_id', table_name, ['user_id'], unique=False)
        if not _has_index(inspector, table_name, 'ix_auth_lifecycle_tokens_token_id'):
            op.create_index('ix_auth_lifecycle_tokens_token_id', table_name, ['token_id'], unique=True)
        if not _has_index(inspector, table_name, 'ix_auth_lifecycle_tokens_token_type'):
            op.create_index('ix_auth_lifecycle_tokens_token_type', table_name, ['token_type'], unique=False)
        if not _has_index(inspector, table_name, 'ix_auth_lifecycle_tokens_expires_at'):
            op.create_index('ix_auth_lifecycle_tokens_expires_at', table_name, ['expires_at'], unique=False)
        if not _has_index(inspector, table_name, 'ix_auth_lifecycle_tokens_used_at'):
            op.create_index('ix_auth_lifecycle_tokens_used_at', table_name, ['used_at'], unique=False)
        if not _has_index(inspector, table_name, 'ix_auth_lifecycle_tokens_revoked_at'):
            op.create_index('ix_auth_lifecycle_tokens_revoked_at', table_name, ['revoked_at'], unique=False)

        if not _has_fk(inspector, table_name, 'user_id'):
            op.create_foreign_key(
                'fk_auth_lifecycle_tokens_user_id_users',
                table_name,
                'users',
                ['user_id'],
                ['id'],
            )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    table_name = 'auth_lifecycle_tokens'
    if _has_table(inspector, table_name):
        if _has_index(inspector, table_name, 'ix_auth_lifecycle_tokens_revoked_at'):
            op.drop_index('ix_auth_lifecycle_tokens_revoked_at', table_name=table_name)
        if _has_index(inspector, table_name, 'ix_auth_lifecycle_tokens_used_at'):
            op.drop_index('ix_auth_lifecycle_tokens_used_at', table_name=table_name)
        if _has_index(inspector, table_name, 'ix_auth_lifecycle_tokens_expires_at'):
            op.drop_index('ix_auth_lifecycle_tokens_expires_at', table_name=table_name)
        if _has_index(inspector, table_name, 'ix_auth_lifecycle_tokens_token_type'):
            op.drop_index('ix_auth_lifecycle_tokens_token_type', table_name=table_name)
        if _has_index(inspector, table_name, 'ix_auth_lifecycle_tokens_token_id'):
            op.drop_index('ix_auth_lifecycle_tokens_token_id', table_name=table_name)
        if _has_index(inspector, table_name, 'ix_auth_lifecycle_tokens_user_id'):
            op.drop_index('ix_auth_lifecycle_tokens_user_id', table_name=table_name)
        if _has_fk(inspector, table_name, 'user_id'):
            op.drop_constraint('fk_auth_lifecycle_tokens_user_id_users', table_name, type_='foreignkey')
        op.drop_table(table_name)

    inspector = sa.inspect(bind)
    users_table = 'users'
    users_verified_index = 'ix_users_email_verified_at'
    if _has_table(inspector, users_table):
        if _has_index(inspector, users_table, users_verified_index):
            op.drop_index(users_verified_index, table_name=users_table)
        if _has_column(inspector, users_table, 'email_verified_at'):
            op.drop_column(users_table, 'email_verified_at')
