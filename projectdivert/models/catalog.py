"""Catalog models."""

from projectdivert.extensions import db


class Material(db.Model):
    __tablename__ = 'materials'

    id = db.Column(db.Integer, primary_key=True)
    waste_stream = db.Column(db.String)
    amount = db.Column(db.Integer)
    address = db.Column(db.String(120))
    city = db.Column(db.String(120))
    county = db.Column(db.String(120))
    postcode = db.Column(db.String(120))
    condition = db.Column(db.String(120))
    dimensions = db.Column(db.String(120))
    image_link1 = db.Column(db.String(120))
    image_link2 = db.Column(db.String(120))
    image_link3 = db.Column(db.String(120))
    longitude = db.Column(db.Float(5))
    latitude = db.Column(db.Float(5))

    def __repr__(self):
        return '<Material {}>'.format(self.waste_stream)


class DiversionEstimate(db.Model):
    __tablename__ = 'diversion_estimates'

    id = db.Column(db.Integer, primary_key=True)
    material = db.Column(db.String(120))
    amount = db.Column(db.Numeric(12, 3))
    unit = db.Column(db.String(120))
    site_address = db.Column(db.String(120))
    traditional_address = db.Column(db.String(120))
    divert_address = db.Column(db.String(120))
    traditional_cost = db.Column(db.Numeric(12, 2))
    divert_cost = db.Column(db.Numeric(12, 2))

    def __repr__(self):
        return '<DiversionEstimate {}>'.format(self.material)


class MaterialRequest(db.Model):
    __tablename__ = 'material_requests'

    id = db.Column(db.Integer, primary_key=True)
    mat_id = db.Column(db.Integer, nullable=False)
    e_id = db.Column(db.String(120), nullable=False)
    message = db.Column(db.String(120))

    def __repr__(self):
        return '<MaterialRequest {}>'.format(self.mat_id)
