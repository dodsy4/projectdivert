"""Add carrier company compliance tables.

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-03-12 19:15:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f7a8b9c0d1e2'
down_revision = 'e6f7a8b9c0d1'
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def _has_index(inspector, table_name, index_name):
    return any(index.get('name') == index_name for index in inspector.get_indexes(table_name))


def _has_column(inspector, table_name, column_name):
    return any(column.get('name') == column_name for column in inspector.get_columns(table_name))


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    company_table = 'carrier_companies'
    if not _has_table(inspector, company_table):
        op.create_table(
            company_table,
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('contact_email', sa.String(length=255), nullable=True),
            sa.Column('contact_phone', sa.String(length=120), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.UniqueConstraint('name', name='uq_carrier_companies_name'),
        )

    inspector = sa.inspect(bind)
    for index_name, columns in [
        ('ix_carrier_companies_name', ['name']),
        ('ix_carrier_companies_contact_email', ['contact_email']),
        ('ix_carrier_companies_is_active', ['is_active']),
    ]:
        if not _has_index(inspector, company_table, index_name):
            op.create_index(index_name, company_table, columns, unique=False)

    users_table = 'users'
    inspector = sa.inspect(bind)
    if not _has_column(inspector, users_table, 'carrier_company_id'):
        op.add_column(users_table, sa.Column('carrier_company_id', sa.Integer(), nullable=True))
        op.create_foreign_key(
            'fk_users_carrier_company_id_carrier_companies',
            users_table,
            company_table,
            ['carrier_company_id'],
            ['id'],
        )

    inspector = sa.inspect(bind)
    if _has_column(inspector, users_table, 'carrier_company_id') and not _has_index(
        inspector, users_table, 'ix_users_carrier_company_id'
    ):
        op.create_index('ix_users_carrier_company_id', users_table, ['carrier_company_id'], unique=False)

    doc_table = 'company_compliance_documents'
    inspector = sa.inspect(bind)
    if not _has_table(inspector, doc_table):
        op.create_table(
            doc_table,
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('carrier_company_id', sa.Integer(), nullable=False),
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
            sa.ForeignKeyConstraint(['carrier_company_id'], [f'{company_table}.id']),
            sa.ForeignKeyConstraint(['uploaded_by_user_id'], ['users.id']),
            sa.ForeignKeyConstraint(['verified_by_user_id'], ['users.id']),
        )

    inspector = sa.inspect(bind)
    for index_name, columns in [
        ('ix_company_compliance_documents_carrier_company_id', ['carrier_company_id']),
        ('ix_company_compliance_documents_uploaded_by_user_id', ['uploaded_by_user_id']),
        ('ix_company_compliance_documents_verified_by_user_id', ['verified_by_user_id']),
        ('ix_company_compliance_documents_document_type', ['document_type']),
        ('ix_company_compliance_documents_status', ['status']),
        ('ix_company_compliance_documents_expires_at', ['expires_at']),
        ('ix_company_compliance_documents_verified_at', ['verified_at']),
    ]:
        if not _has_index(inspector, doc_table, index_name):
            op.create_index(index_name, doc_table, columns, unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    doc_table = 'company_compliance_documents'
    if _has_table(inspector, doc_table):
        for index_name in [
            'ix_company_compliance_documents_verified_at',
            'ix_company_compliance_documents_expires_at',
            'ix_company_compliance_documents_status',
            'ix_company_compliance_documents_document_type',
            'ix_company_compliance_documents_verified_by_user_id',
            'ix_company_compliance_documents_uploaded_by_user_id',
            'ix_company_compliance_documents_carrier_company_id',
        ]:
            if _has_index(inspector, doc_table, index_name):
                op.drop_index(index_name, table_name=doc_table)
        op.drop_table(doc_table)

    inspector = sa.inspect(bind)
    users_table = 'users'
    if _has_column(inspector, users_table, 'carrier_company_id'):
        if _has_index(inspector, users_table, 'ix_users_carrier_company_id'):
            op.drop_index('ix_users_carrier_company_id', table_name=users_table)
        op.drop_constraint('fk_users_carrier_company_id_carrier_companies', users_table, type_='foreignkey')
        op.drop_column(users_table, 'carrier_company_id')

    inspector = sa.inspect(bind)
    company_table = 'carrier_companies'
    if _has_table(inspector, company_table):
        for index_name in [
            'ix_carrier_companies_is_active',
            'ix_carrier_companies_contact_email',
            'ix_carrier_companies_name',
        ]:
            if _has_index(inspector, company_table, index_name):
                op.drop_index(index_name, table_name=company_table)
        op.drop_table(company_table)
