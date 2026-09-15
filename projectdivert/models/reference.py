"""Reference models."""

from projectdivert.extensions import db


class SupplierReference(db.Model):
    __tablename__ = 'supplier_reference'

    id = db.Column(db.Integer, primary_key=True)
    source_row_index = db.Column(db.Integer, nullable=False, unique=True, index=True)
    sup_type = db.Column(db.String(120), index=True)
    name = db.Column(db.String(255), index=True)
    address_street = db.Column(db.String(255))
    city = db.Column(db.String(120))
    postcode = db.Column(db.String(32), index=True)
    lat = db.Column(db.Float)
    long = db.Column(db.Float)
    website = db.Column(db.String(255))
    email = db.Column(db.String(255))
    telephone = db.Column(db.String(120))
    supplier_contact = db.Column(db.String(255))
    supplier_contact_email = db.Column(db.String(255))
    supplier_contact_telephone = db.Column(db.String(120))
    percent_recyclablenum = db.Column(db.Float)
    percent_efwnum = db.Column(db.Float)
    provides_a_rebateyn = db.Column(db.Float)
    supplier_auditislist_yes_no_na = db.Column(db.String(32))
    supplier_audit_date_completed = db.Column(db.String(64))
    notes = db.Column(db.Text)
    hierarchy = db.Column(db.String(120))
    origin = db.Column(db.String(120))
    row_data = db.Column(db.JSON, nullable=False, default=dict)

    def __repr__(self):
        return '<SupplierReference {} {}>'.format(self.id, self.name)


class SiteReference(db.Model):
    __tablename__ = 'site_reference'

    id = db.Column(db.Integer, primary_key=True)
    source_row_index = db.Column(db.Integer, nullable=False, unique=True, index=True)
    row_data = db.Column(db.JSON, nullable=False, default=dict)

    def __repr__(self):
        return '<SiteReference {}>'.format(self.id)


class DivertOutputReference(db.Model):
    __tablename__ = 'divert_output_reference'

    id = db.Column(db.Integer, primary_key=True)
    source_row_index = db.Column(db.Integer, nullable=False, unique=True, index=True)
    row_data = db.Column(db.JSON, nullable=False, default=dict)

    def __repr__(self):
        return '<DivertOutputReference {}>'.format(self.id)


class ReuseOffsetReference(db.Model):
    __tablename__ = 'reuse_offset_reference'

    id = db.Column(db.Integer, primary_key=True)
    source_row_index = db.Column(db.Integer, nullable=False, unique=True, index=True)
    material = db.Column(db.String(255), index=True)
    emission_factor = db.Column(db.Float)
    source = db.Column(db.String(255))
    explanation = db.Column(db.Text)
    row_data = db.Column(db.JSON, nullable=False, default=dict)

    def __repr__(self):
        return '<ReuseOffsetReference {}>'.format(self.material)


class RecycleOffsetReference(db.Model):
    __tablename__ = 'recycle_offset_reference'

    id = db.Column(db.Integer, primary_key=True)
    source_row_index = db.Column(db.Integer, nullable=False, unique=True, index=True)
    material = db.Column(db.String(255), index=True)
    emission_factor = db.Column(db.Float)
    source = db.Column(db.String(255))
    explanation = db.Column(db.Text)
    row_data = db.Column(db.JSON, nullable=False, default=dict)

    def __repr__(self):
        return '<RecycleOffsetReference {}>'.format(self.material)


class CarbonEquivalencyReference(db.Model):
    __tablename__ = 'carbon_equivalency_reference'

    id = db.Column(db.Integer, primary_key=True)
    source_row_index = db.Column(db.Integer, nullable=False, unique=True, index=True)
    equivalency = db.Column(db.String(255), index=True)
    emission_factor = db.Column(db.Float)
    row_data = db.Column(db.JSON, nullable=False, default=dict)

    def __repr__(self):
        return '<CarbonEquivalencyReference {}>'.format(self.equivalency)
