"""Add per-user access token revocation cutoff.

Revision ID: b4c1d9e7f2a3
Revises: a8e3d1b4c5f6
Create Date: 2026-02-28 15:05:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b4c1d9e7f2a3'
down_revision = 'a8e3d1b4c5f6'
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name, column_name):
    return any(column.get('name') == column_name for column in inspector.get_columns(table_name))


def _has_index(inspector, table_name, index_name):
    return any(index.get('name') == index_name for index in inspector.get_indexes(table_name))


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    users_table = 'users'
    cutoff_column = 'access_token_revoked_at'
    cutoff_index = 'ix_users_access_token_revoked_at'
    if _has_table(inspector, users_table) and not _has_column(inspector, users_table, cutoff_column):
        op.add_column(users_table, sa.Column(cutoff_column, sa.DateTime(), nullable=True))

    inspector = sa.inspect(bind)
    if _has_table(inspector, users_table) and not _has_index(inspector, users_table, cutoff_index):
        op.create_index(cutoff_index, users_table, [cutoff_column], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    users_table = 'users'
    cutoff_column = 'access_token_revoked_at'
    cutoff_index = 'ix_users_access_token_revoked_at'
    if _has_table(inspector, users_table):
        if _has_index(inspector, users_table, cutoff_index):
            op.drop_index(cutoff_index, table_name=users_table)
        if _has_column(inspector, users_table, cutoff_column):
            op.drop_column(users_table, cutoff_column)
