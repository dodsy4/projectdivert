"""Rename core marketplace models (c/m/r/output) and tighten estimate column types.

Renames the legacy single-letter tables to descriptive names and converts the
free-text numeric columns on the diversion-estimate table to real numeric types:

    c       -> charities
    m       -> materials
    r       -> material_requests
    output  -> diversion_estimates
        diversion_estimates.amount           TEXT -> NUMERIC(12, 3)
        diversion_estimates.traditional_cost TEXT -> NUMERIC(12, 2)
        diversion_estimates.divert_cost      TEXT -> NUMERIC(12, 2)

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-09-07 22:20:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5e6f7a8b9c0'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


RENAMES = [
    ('c', 'charities'),
    ('m', 'materials'),
    ('r', 'material_requests'),
    ('output', 'diversion_estimates'),
]

# (column, new type, USING cast expression, old type)
ESTIMATE_NUMERIC_COLUMNS = [
    ('amount', sa.Numeric(12, 3), 'amount::numeric', sa.String(length=120)),
    ('traditional_cost', sa.Numeric(12, 2), 'traditional_cost::numeric', sa.String(length=120)),
    ('divert_cost', sa.Numeric(12, 2), 'divert_cost::numeric', sa.String(length=120)),
]


def _has_table(inspector, name):
    return name in inspector.get_table_names()


def _is_postgres(bind):
    return bind.dialect.name == 'postgresql'


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for old_name, new_name in RENAMES:
        if _has_table(inspector, old_name) and not _has_table(inspector, new_name):
            op.rename_table(old_name, new_name)
            inspector = sa.inspect(bind)

    if not _has_table(inspector, 'diversion_estimates'):
        return

    # Column-type tightening is only meaningful on the production engine
    # (PostgreSQL). SQLite dev/test databases are built from the models via
    # ``db.create_all()`` and never run this migration.
    if not _is_postgres(bind):
        return

    # Blank strings become NULL first so the ``::numeric`` cast does not choke.
    for column_name, _new_type, _using_expr, _old_type in ESTIMATE_NUMERIC_COLUMNS:
        op.execute(
            "UPDATE diversion_estimates SET {col} = NULL "
            "WHERE {col} IS NOT NULL AND btrim({col}) = ''".format(col=column_name)
        )

    for column_name, new_type, using_expr, old_type in ESTIMATE_NUMERIC_COLUMNS:
        op.alter_column(
            'diversion_estimates',
            column_name,
            existing_type=old_type,
            type_=new_type,
            existing_nullable=True,
            postgresql_using=using_expr,
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, 'diversion_estimates') and _is_postgres(bind):
        for column_name, new_type, _using_expr, old_type in ESTIMATE_NUMERIC_COLUMNS:
            op.alter_column(
                'diversion_estimates',
                column_name,
                existing_type=new_type,
                type_=old_type,
                existing_nullable=True,
                postgresql_using='{}::text'.format(column_name),
            )

    for old_name, new_name in reversed(RENAMES):
        if _has_table(inspector, new_name) and not _has_table(inspector, old_name):
            op.rename_table(new_name, old_name)
            inspector = sa.inspect(bind)
