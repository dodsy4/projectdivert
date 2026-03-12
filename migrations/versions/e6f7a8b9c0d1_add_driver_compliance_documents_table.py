"""Add driver compliance documents table.

Revision ID: e6f7a8b9c0d1
Revises: d4e5f6a7b8c9
Create Date: 2026-03-12 18:20:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e6f7a8b9c0d1'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def _has_index(inspector, table_name, index_name):
    return any(index.get('name') == index_name for index in inspector.get_indexes(table_name))


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = 'driver_compliance_documents'

    if not _has_table(inspector, table_name):
        op.create_table(
            table_name,
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('driver_user_id', sa.Integer(), nullable=False),
            sa.Column('uploaded_by_user_id', sa.Integer(), nullable=True),
            sa.Column('verified_by_user_id', sa.Integer(), nullable=True),
            sa.Column('document_type', sa.String(length=64), nullable=False),
            sa.Column('status', sa.String(length=32), nullable=False, server_default='submitted'),
            sa.Column('file_url', sa.String(length=500), nullable=False),
            sa.Column('document_reference', sa.String(length=120), nullable=True),
            sa.Column('issued_at', sa.DateTime(), nullable=True),
            sa.Column('expires_at', sa.DateTime(), nullable=True),
            sa.Column('verified_at', sa.DateTime(), nullable=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('metadata_json', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['driver_user_id'], ['users.id']),
            sa.ForeignKeyConstraint(['uploaded_by_user_id'], ['users.id']),
            sa.ForeignKeyConstraint(['verified_by_user_id'], ['users.id']),
        )

    inspector = sa.inspect(bind)
    for index_name, columns in [
        ('ix_driver_compliance_documents_driver_user_id', ['driver_user_id']),
        ('ix_driver_compliance_documents_uploaded_by_user_id', ['uploaded_by_user_id']),
        ('ix_driver_compliance_documents_verified_by_user_id', ['verified_by_user_id']),
        ('ix_driver_compliance_documents_document_type', ['document_type']),
        ('ix_driver_compliance_documents_status', ['status']),
        ('ix_driver_compliance_documents_expires_at', ['expires_at']),
        ('ix_driver_compliance_documents_verified_at', ['verified_at']),
    ]:
        if not _has_index(inspector, table_name, index_name):
            op.create_index(index_name, table_name, columns, unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = 'driver_compliance_documents'

    if not _has_table(inspector, table_name):
        return

    for index_name in [
        'ix_driver_compliance_documents_verified_at',
        'ix_driver_compliance_documents_expires_at',
        'ix_driver_compliance_documents_status',
        'ix_driver_compliance_documents_document_type',
        'ix_driver_compliance_documents_verified_by_user_id',
        'ix_driver_compliance_documents_uploaded_by_user_id',
        'ix_driver_compliance_documents_driver_user_id',
    ]:
        if _has_index(inspector, table_name, index_name):
            op.drop_index(index_name, table_name=table_name)

    op.drop_table(table_name)
