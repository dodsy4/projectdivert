"""Reference datasets (suppliers, sites, offsets) and DB seeding."""

import os
import csv
from datetime import datetime
import pandas as pd
from flask import current_app
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError
from project_divert_functions import carbon_equivalencies, divert_output, recycle_offset, reuse_offset, sites, suppliers
from projectdivert.extensions import db
from projectdivert.models.catalog import Material
from projectdivert.models.reference import CarbonEquivalencyReference, DivertOutputReference, RecycleOffsetReference, ReuseOffsetReference, SiteReference, SupplierReference
from projectdivert.services.utils import _to_float_or_none, _to_int_or_none
import logging

logger = logging.getLogger(__name__)


_reference_data_refresh_attempted = False


def _clean_reference_value(value):
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    if hasattr(value, 'item'):
        try:
            value = value.item()
        except Exception:
            pass

    if isinstance(value, datetime):
        return value.isoformat()

    return value


def _clean_reference_row(row):
    row_data = row.to_dict() if hasattr(row, 'to_dict') else dict(row)
    return {str(key): _clean_reference_value(value) for key, value in row_data.items()}


def _normalize_material_column(frame):
    if 'material' not in frame.columns:
        return frame
    normalized = frame.copy()
    normalized['material'] = (
        normalized['material']
        .astype(str)
        .str.replace('\xa0', ' ', regex=False)
        .str.strip()
    )
    return normalized


def _build_supplier_reference_row(source_row_index, row):
    row_data = _clean_reference_row(row)
    return SupplierReference(
        source_row_index=int(source_row_index),
        sup_type=(str(row_data.get('sup_type') or '').strip()[:120] or None),
        name=(str(row_data.get('name') or '').strip()[:255] or None),
        address_street=(str(row_data.get('address_street') or '').strip()[:255] or None),
        city=(str(row_data.get('city') or '').strip()[:120] or None),
        postcode=(str(row_data.get('postcode') or '').strip()[:32] or None),
        lat=_to_float_or_none(row_data.get('lat')),
        long=_to_float_or_none(row_data.get('long')),
        website=(str(row_data.get('website') or '').strip()[:255] or None),
        email=(str(row_data.get('email') or '').strip()[:255] or None),
        telephone=(str(row_data.get('telephone') or '').strip()[:120] or None),
        supplier_contact=(str(row_data.get('supplier_contact') or '').strip()[:255] or None),
        supplier_contact_email=(str(row_data.get('supplier_contact_email') or '').strip()[:255] or None),
        supplier_contact_telephone=(str(row_data.get('supplier_contact_telephone') or '').strip()[:120] or None),
        percent_recyclablenum=_to_float_or_none(row_data.get('percent_recyclablenum')),
        percent_efwnum=_to_float_or_none(row_data.get('percent_efwnum')),
        provides_a_rebateyn=_to_float_or_none(row_data.get('provides_a_rebateyn')),
        supplier_auditislist_yes_no_na=(
            str(row_data.get('supplier_auditislist_yes_no_na') or '').strip()[:32] or None
        ),
        supplier_audit_date_completed=(
            str(row_data.get('supplier_audit_date_completed') or '').strip()[:64] or None
        ),
        notes=(str(row_data.get('notes') or '').strip() or None),
        hierarchy=(str(row_data.get('hierarchy') or '').strip()[:120] or None),
        origin=(str(row_data.get('origin') or '').strip()[:120] or None),
        row_data=row_data,
    )


def _seed_reference_model_from_frame(model, frame, row_builder, force=False):
    existing = model.query.count()
    if existing and not force:
        return {'inserted': 0, 'existing': existing, 'skipped': True}

    if existing:
        model.query.delete()
        db.session.flush()

    objects = [row_builder(index, row) for index, row in frame.iterrows()]
    if objects:
        db.session.bulk_save_objects(objects)

    return {'inserted': len(objects), 'existing': existing, 'skipped': False}


def _seed_reference_data_from_files(force=False):
    supplier_frame = pd.read_csv('data/df3.csv')
    site_frame = pd.read_excel('sites.xlsx')
    divert_output_frame = pd.read_csv('divert_db.csv')
    reuse_frame = _normalize_material_column(pd.read_csv('reuse_offset.csv'))
    recycle_frame = _normalize_material_column(pd.read_excel('recycle_offset.csv'))
    carbon_frame = pd.read_excel('carbon_equivalencies.csv')

    summary = {
        'supplier_reference': _seed_reference_model_from_frame(
            SupplierReference,
            supplier_frame,
            _build_supplier_reference_row,
            force=force,
        ),
        'site_reference': _seed_reference_model_from_frame(
            SiteReference,
            site_frame,
            lambda index, row: SiteReference(source_row_index=int(index), row_data=_clean_reference_row(row)),
            force=force,
        ),
        'divert_output_reference': _seed_reference_model_from_frame(
            DivertOutputReference,
            divert_output_frame,
            lambda index, row: DivertOutputReference(
                source_row_index=int(index),
                row_data=_clean_reference_row(row),
            ),
            force=force,
        ),
        'reuse_offset_reference': _seed_reference_model_from_frame(
            ReuseOffsetReference,
            reuse_frame,
            lambda index, row: ReuseOffsetReference(
                source_row_index=int(index),
                material=(str(row.get('material') or '').strip()[:255] or None),
                emission_factor=_to_float_or_none(row.get('Emission Factor (kg CO2 equivalents/ tonne)')),
                source=(str(row.get('Source') or '').strip()[:255] or None),
                explanation=(str(row.get('Explanation') or '').strip() or None),
                row_data=_clean_reference_row(row),
            ),
            force=force,
        ),
        'recycle_offset_reference': _seed_reference_model_from_frame(
            RecycleOffsetReference,
            recycle_frame,
            lambda index, row: RecycleOffsetReference(
                source_row_index=int(index),
                material=(str(row.get('material') or '').strip()[:255] or None),
                emission_factor=_to_float_or_none(row.get('Emission Factor (kg CO2 equivalents/ tonne)')),
                source=(str(row.get('Source') or '').strip()[:255] or None),
                explanation=(str(row.get('Explanation') or '').strip() or None),
                row_data=_clean_reference_row(row),
            ),
            force=force,
        ),
        'carbon_equivalency_reference': _seed_reference_model_from_frame(
            CarbonEquivalencyReference,
            carbon_frame,
            lambda index, row: CarbonEquivalencyReference(
                source_row_index=int(index),
                equivalency=(str(row.get('equivalency') or '').strip()[:255] or None),
                emission_factor=_to_float_or_none(
                    row.get('emission factor (kg co2 equivalents/ tonne)')
                ),
                row_data=_clean_reference_row(row),
            ),
            force=force,
        ),
    }
    db.session.commit()
    return summary


def _refresh_reference_dataframes_from_db():
    global suppliers, sites, divert_output, reuse_offset, recycle_offset, carbon_equivalencies

    required_tables = {
        'supplier_reference',
        'site_reference',
        'divert_output_reference',
        'reuse_offset_reference',
        'recycle_offset_reference',
        'carbon_equivalency_reference',
    }

    try:
        table_names = set(inspect(db.engine).get_table_names())
    except SQLAlchemyError:
        return False

    if not required_tables.issubset(table_names):
        return False

    loaded_any = False

    supplier_rows = SupplierReference.query.order_by(SupplierReference.source_row_index.asc()).all()
    if supplier_rows:
        supplier_records = []
        for row in supplier_rows:
            record = dict(row.row_data or {})
            record.setdefault('sup_type', row.sup_type)
            record.setdefault('name', row.name)
            record.setdefault('address_street', row.address_street)
            record.setdefault('city', row.city)
            record.setdefault('postcode', row.postcode)
            record.setdefault('lat', row.lat)
            record.setdefault('long', row.long)
            record.setdefault('website', row.website)
            record.setdefault('email', row.email)
            record.setdefault('telephone', row.telephone)
            record.setdefault('supplier_contact', row.supplier_contact)
            record.setdefault('supplier_contact_email', row.supplier_contact_email)
            record.setdefault('supplier_contact_telephone', row.supplier_contact_telephone)
            record.setdefault('percent_recyclablenum', row.percent_recyclablenum)
            record.setdefault('percent_efwnum', row.percent_efwnum)
            record.setdefault('provides_a_rebateyn', row.provides_a_rebateyn)
            record.setdefault('supplier_auditislist_yes_no_na', row.supplier_auditislist_yes_no_na)
            record.setdefault('supplier_audit_date_completed', row.supplier_audit_date_completed)
            record.setdefault('notes', row.notes)
            record.setdefault('hierarchy', row.hierarchy)
            record.setdefault('origin', row.origin)
            supplier_records.append(record)
        suppliers = pd.DataFrame(supplier_records)
        loaded_any = True

    site_rows = SiteReference.query.order_by(SiteReference.source_row_index.asc()).all()
    if site_rows:
        sites = pd.DataFrame([dict(row.row_data or {}) for row in site_rows])
        loaded_any = True

    divert_rows = DivertOutputReference.query.order_by(DivertOutputReference.source_row_index.asc()).all()
    if divert_rows:
        divert_output = pd.DataFrame([dict(row.row_data or {}) for row in divert_rows])
        if 'reuse_offset' not in divert_output.columns:
            divert_output['reuse_offset'] = ''
        if 'recycle_offset' not in divert_output.columns:
            divert_output['recycle_offset'] = ''
        divert_output['reuse_offset'] = pd.to_numeric(divert_output['reuse_offset'], errors='coerce')
        divert_output['recycle_offset'] = pd.to_numeric(divert_output['recycle_offset'], errors='coerce')
        loaded_any = True

    reuse_rows = ReuseOffsetReference.query.order_by(ReuseOffsetReference.source_row_index.asc()).all()
    if reuse_rows:
        reuse_records = []
        for row in reuse_rows:
            record = dict(row.row_data or {})
            record.setdefault('material', row.material)
            record.setdefault('Emission Factor (kg CO2 equivalents/ tonne)', row.emission_factor)
            record.setdefault('Source', row.source)
            record.setdefault('Explanation', row.explanation)
            reuse_records.append(record)
        reuse_offset = _normalize_material_column(pd.DataFrame(reuse_records))
        if 'material' in reuse_offset.columns:
            reuse_offset.set_index(keys='material', inplace=True)
        loaded_any = True

    recycle_rows = RecycleOffsetReference.query.order_by(RecycleOffsetReference.source_row_index.asc()).all()
    if recycle_rows:
        recycle_records = []
        for row in recycle_rows:
            record = dict(row.row_data or {})
            record.setdefault('material', row.material)
            record.setdefault('Emission Factor (kg CO2 equivalents/ tonne)', row.emission_factor)
            record.setdefault('Source', row.source)
            record.setdefault('Explanation', row.explanation)
            recycle_records.append(record)
        recycle_offset = _normalize_material_column(pd.DataFrame(recycle_records))
        if 'material' in recycle_offset.columns:
            recycle_offset.set_index(keys='material', inplace=True)
        loaded_any = True

    carbon_rows = CarbonEquivalencyReference.query.order_by(
        CarbonEquivalencyReference.source_row_index.asc()
    ).all()
    if carbon_rows:
        carbon_equivalencies = pd.DataFrame([dict(row.row_data or {}) for row in carbon_rows])
        loaded_any = True

    return loaded_any


def _ensure_reference_data_loaded():
    global _reference_data_refresh_attempted
    if _reference_data_refresh_attempted:
        return
    _reference_data_refresh_attempted = True
    try:
        _refresh_reference_dataframes_from_db()
    except Exception:
        logger.exception('Failed to refresh reference data from database.')


def _seed_materials_if_empty():
    try:
        if Material.query.first() is not None:
            return

        csv_path = os.path.join(current_app.root_path, 'material_sheet.csv')
        if not os.path.exists(csv_path):
            logger.warning('No material seed file found at %s', csv_path)
            return

        seeded_count = 0
        with open(csv_path, newline='', encoding='utf-8-sig') as handle:
            for row in csv.DictReader(handle):
                waste_stream = (row.get('waste_stream') or '').strip()
                if not waste_stream:
                    continue

                db.session.add(
                    Material(
                        waste_stream=waste_stream,
                        amount=_to_int_or_none(row.get('amount')),
                        address=(row.get('address') or '').strip() or None,
                        city=(row.get('city') or '').strip() or None,
                        county=(row.get('county') or '').strip() or None,
                        postcode=(row.get('postcode') or '').strip() or None,
                        condition=(row.get('condition') or '').strip() or None,
                        dimensions=(row.get('dimensions') or '').strip() or None,
                        image_link1=(row.get('image_link1') or '').strip() or None,
                        image_link2=(row.get('image_link2') or '').strip() or None,
                        image_link3=(row.get('image_link3') or '').strip() or None,
                        longitude=_to_float_or_none(row.get('longitude')),
                        latitude=_to_float_or_none(row.get('latitude')),
                    )
                )
                seeded_count += 1

        if seeded_count:
            db.session.commit()
            logger.info('Seeded %s materials from material_sheet.csv', seeded_count)
    except Exception:
        db.session.rollback()
        logger.exception('Failed to seed materials from material_sheet.csv.')
