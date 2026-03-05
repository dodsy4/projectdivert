"""Add reference data tables for CSV/XLSX-backed datasets.

Revision ID: c2f8f5664d13
Revises: 5adbb35bb9f8
Create Date: 2026-02-27 12:55:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c2f8f5664d13'
down_revision = '5adbb35bb9f8'
branch_labels = None
depends_on = None


def _has_index(inspector, table_name, index_name):
    return any(index.get('name') == index_name for index in inspector.get_indexes(table_name))


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if 'supplier_reference' not in table_names:
        op.create_table(
            'supplier_reference',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('source_row_index', sa.Integer(), nullable=False),
            sa.Column('sup_type', sa.String(length=120), nullable=True),
            sa.Column('name', sa.String(length=255), nullable=True),
            sa.Column('address_street', sa.String(length=255), nullable=True),
            sa.Column('city', sa.String(length=120), nullable=True),
            sa.Column('postcode', sa.String(length=32), nullable=True),
            sa.Column('lat', sa.Float(), nullable=True),
            sa.Column('long', sa.Float(), nullable=True),
            sa.Column('website', sa.String(length=255), nullable=True),
            sa.Column('email', sa.String(length=255), nullable=True),
            sa.Column('telephone', sa.String(length=120), nullable=True),
            sa.Column('supplier_contact', sa.String(length=255), nullable=True),
            sa.Column('supplier_contact_email', sa.String(length=255), nullable=True),
            sa.Column('supplier_contact_telephone', sa.String(length=120), nullable=True),
            sa.Column('percent_recyclablenum', sa.Float(), nullable=True),
            sa.Column('percent_efwnum', sa.Float(), nullable=True),
            sa.Column('provides_a_rebateyn', sa.Float(), nullable=True),
            sa.Column('supplier_auditislist_yes_no_na', sa.String(length=32), nullable=True),
            sa.Column('supplier_audit_date_completed', sa.String(length=64), nullable=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('hierarchy', sa.String(length=120), nullable=True),
            sa.Column('origin', sa.String(length=120), nullable=True),
            sa.Column('row_data', sa.JSON(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
        table_names.add('supplier_reference')

    if 'site_reference' not in table_names:
        op.create_table(
            'site_reference',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('source_row_index', sa.Integer(), nullable=False),
            sa.Column('row_data', sa.JSON(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
        table_names.add('site_reference')

    if 'divert_output_reference' not in table_names:
        op.create_table(
            'divert_output_reference',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('source_row_index', sa.Integer(), nullable=False),
            sa.Column('row_data', sa.JSON(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
        table_names.add('divert_output_reference')

    if 'reuse_offset_reference' not in table_names:
        op.create_table(
            'reuse_offset_reference',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('source_row_index', sa.Integer(), nullable=False),
            sa.Column('material', sa.String(length=255), nullable=True),
            sa.Column('emission_factor', sa.Float(), nullable=True),
            sa.Column('source', sa.String(length=255), nullable=True),
            sa.Column('explanation', sa.Text(), nullable=True),
            sa.Column('row_data', sa.JSON(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
        table_names.add('reuse_offset_reference')

    if 'recycle_offset_reference' not in table_names:
        op.create_table(
            'recycle_offset_reference',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('source_row_index', sa.Integer(), nullable=False),
            sa.Column('material', sa.String(length=255), nullable=True),
            sa.Column('emission_factor', sa.Float(), nullable=True),
            sa.Column('source', sa.String(length=255), nullable=True),
            sa.Column('explanation', sa.Text(), nullable=True),
            sa.Column('row_data', sa.JSON(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
        table_names.add('recycle_offset_reference')

    if 'carbon_equivalency_reference' not in table_names:
        op.create_table(
            'carbon_equivalency_reference',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('source_row_index', sa.Integer(), nullable=False),
            sa.Column('equivalency', sa.String(length=255), nullable=True),
            sa.Column('emission_factor', sa.Float(), nullable=True),
            sa.Column('row_data', sa.JSON(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
        table_names.add('carbon_equivalency_reference')

    if not _has_index(inspector, 'supplier_reference', 'ix_supplier_reference_source_row_index'):
        op.create_index(
            'ix_supplier_reference_source_row_index',
            'supplier_reference',
            ['source_row_index'],
            unique=True,
        )
    if not _has_index(inspector, 'supplier_reference', 'ix_supplier_reference_name'):
        op.create_index('ix_supplier_reference_name', 'supplier_reference', ['name'], unique=False)
    if not _has_index(inspector, 'supplier_reference', 'ix_supplier_reference_postcode'):
        op.create_index('ix_supplier_reference_postcode', 'supplier_reference', ['postcode'], unique=False)
    if not _has_index(inspector, 'supplier_reference', 'ix_supplier_reference_sup_type'):
        op.create_index('ix_supplier_reference_sup_type', 'supplier_reference', ['sup_type'], unique=False)

    if not _has_index(inspector, 'site_reference', 'ix_site_reference_source_row_index'):
        op.create_index('ix_site_reference_source_row_index', 'site_reference', ['source_row_index'], unique=True)

    if not _has_index(inspector, 'divert_output_reference', 'ix_divert_output_reference_source_row_index'):
        op.create_index(
            'ix_divert_output_reference_source_row_index',
            'divert_output_reference',
            ['source_row_index'],
            unique=True,
        )

    if not _has_index(inspector, 'reuse_offset_reference', 'ix_reuse_offset_reference_source_row_index'):
        op.create_index(
            'ix_reuse_offset_reference_source_row_index',
            'reuse_offset_reference',
            ['source_row_index'],
            unique=True,
        )
    if not _has_index(inspector, 'reuse_offset_reference', 'ix_reuse_offset_reference_material'):
        op.create_index(
            'ix_reuse_offset_reference_material',
            'reuse_offset_reference',
            ['material'],
            unique=False,
        )

    if not _has_index(inspector, 'recycle_offset_reference', 'ix_recycle_offset_reference_source_row_index'):
        op.create_index(
            'ix_recycle_offset_reference_source_row_index',
            'recycle_offset_reference',
            ['source_row_index'],
            unique=True,
        )
    if not _has_index(inspector, 'recycle_offset_reference', 'ix_recycle_offset_reference_material'):
        op.create_index(
            'ix_recycle_offset_reference_material',
            'recycle_offset_reference',
            ['material'],
            unique=False,
        )

    if not _has_index(inspector, 'carbon_equivalency_reference', 'ix_carbon_equivalency_reference_source_row_index'):
        op.create_index(
            'ix_carbon_equivalency_reference_source_row_index',
            'carbon_equivalency_reference',
            ['source_row_index'],
            unique=True,
        )
    if not _has_index(inspector, 'carbon_equivalency_reference', 'ix_carbon_equivalency_reference_equivalency'):
        op.create_index(
            'ix_carbon_equivalency_reference_equivalency',
            'carbon_equivalency_reference',
            ['equivalency'],
            unique=False,
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if 'carbon_equivalency_reference' in table_names:
        if _has_index(
            inspector,
            'carbon_equivalency_reference',
            'ix_carbon_equivalency_reference_equivalency',
        ):
            op.drop_index(
                'ix_carbon_equivalency_reference_equivalency',
                table_name='carbon_equivalency_reference',
            )
        if _has_index(
            inspector,
            'carbon_equivalency_reference',
            'ix_carbon_equivalency_reference_source_row_index',
        ):
            op.drop_index(
                'ix_carbon_equivalency_reference_source_row_index',
                table_name='carbon_equivalency_reference',
            )
        op.drop_table('carbon_equivalency_reference')

    if 'recycle_offset_reference' in table_names:
        if _has_index(
            inspector,
            'recycle_offset_reference',
            'ix_recycle_offset_reference_material',
        ):
            op.drop_index('ix_recycle_offset_reference_material', table_name='recycle_offset_reference')
        if _has_index(
            inspector,
            'recycle_offset_reference',
            'ix_recycle_offset_reference_source_row_index',
        ):
            op.drop_index(
                'ix_recycle_offset_reference_source_row_index',
                table_name='recycle_offset_reference',
            )
        op.drop_table('recycle_offset_reference')

    if 'reuse_offset_reference' in table_names:
        if _has_index(inspector, 'reuse_offset_reference', 'ix_reuse_offset_reference_material'):
            op.drop_index('ix_reuse_offset_reference_material', table_name='reuse_offset_reference')
        if _has_index(
            inspector,
            'reuse_offset_reference',
            'ix_reuse_offset_reference_source_row_index',
        ):
            op.drop_index(
                'ix_reuse_offset_reference_source_row_index',
                table_name='reuse_offset_reference',
            )
        op.drop_table('reuse_offset_reference')

    if 'divert_output_reference' in table_names:
        if _has_index(
            inspector,
            'divert_output_reference',
            'ix_divert_output_reference_source_row_index',
        ):
            op.drop_index(
                'ix_divert_output_reference_source_row_index',
                table_name='divert_output_reference',
            )
        op.drop_table('divert_output_reference')

    if 'site_reference' in table_names:
        if _has_index(inspector, 'site_reference', 'ix_site_reference_source_row_index'):
            op.drop_index('ix_site_reference_source_row_index', table_name='site_reference')
        op.drop_table('site_reference')

    if 'supplier_reference' in table_names:
        if _has_index(inspector, 'supplier_reference', 'ix_supplier_reference_sup_type'):
            op.drop_index('ix_supplier_reference_sup_type', table_name='supplier_reference')
        if _has_index(inspector, 'supplier_reference', 'ix_supplier_reference_postcode'):
            op.drop_index('ix_supplier_reference_postcode', table_name='supplier_reference')
        if _has_index(inspector, 'supplier_reference', 'ix_supplier_reference_name'):
            op.drop_index('ix_supplier_reference_name', table_name='supplier_reference')
        if _has_index(inspector, 'supplier_reference', 'ix_supplier_reference_source_row_index'):
            op.drop_index('ix_supplier_reference_source_row_index', table_name='supplier_reference')
        op.drop_table('supplier_reference')
