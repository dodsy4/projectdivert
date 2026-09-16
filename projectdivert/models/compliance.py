"""Compliance models."""

from datetime import datetime
from projectdivert.extensions import db


class WasteComplianceDocument(db.Model):
    __tablename__ = 'waste_compliance_documents'

    id = db.Column(db.Integer, primary_key=True)
    waste_removal_request_id = db.Column(
        db.Integer,
        db.ForeignKey('waste_removal_requests.id'),
        nullable=False,
        index=True,
    )
    uploaded_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        index=True,
    )
    verified_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        index=True,
    )
    document_type = db.Column(db.String(64), nullable=False, index=True)
    status = db.Column(db.String(32), nullable=False, default='submitted', index=True)
    file_url = db.Column(db.String(500), nullable=False)
    document_reference = db.Column(db.String(120))
    issued_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime, index=True)
    verified_at = db.Column(db.DateTime, index=True)
    notes = db.Column(db.Text)
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    def __repr__(self):
        return '<WasteComplianceDocument request={} type={} status={}>'.format(
            self.waste_removal_request_id,
            self.document_type,
            self.status,
        )


class CarrierCompany(db.Model):
    __tablename__ = 'carrier_companies'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True, index=True)
    contact_email = db.Column(db.String(255), index=True)
    contact_phone = db.Column(db.String(120))
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    def __repr__(self):
        return '<CarrierCompany {} {}>'.format(self.id, self.name)


class DriverComplianceDocument(db.Model):
    __tablename__ = 'driver_compliance_documents'

    id = db.Column(db.Integer, primary_key=True)
    driver_user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        nullable=False,
        index=True,
    )
    uploaded_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        index=True,
    )
    verified_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        index=True,
    )
    document_type = db.Column(db.String(64), nullable=False, index=True)
    status = db.Column(db.String(32), nullable=False, default='submitted', index=True)
    file_url = db.Column(db.String(500), nullable=False)
    document_reference = db.Column(db.String(120))
    issued_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime, index=True)
    verified_at = db.Column(db.DateTime, index=True)
    notes = db.Column(db.Text)
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    def __repr__(self):
        return '<DriverComplianceDocument driver={} type={} status={}>'.format(
            self.driver_user_id,
            self.document_type,
            self.status,
        )


class CompanyComplianceDocument(db.Model):
    __tablename__ = 'company_compliance_documents'

    id = db.Column(db.Integer, primary_key=True)
    carrier_company_id = db.Column(
        db.Integer,
        db.ForeignKey('carrier_companies.id'),
        nullable=False,
        index=True,
    )
    uploaded_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        index=True,
    )
    verified_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        index=True,
    )
    document_type = db.Column(db.String(64), nullable=False, index=True)
    status = db.Column(db.String(32), nullable=False, default='submitted', index=True)
    file_url = db.Column(db.String(500), nullable=False)
    document_reference = db.Column(db.String(120))
    issued_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime, index=True)
    verified_at = db.Column(db.DateTime, index=True)
    notes = db.Column(db.Text)
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    def __repr__(self):
        return '<CompanyComplianceDocument company={} type={} status={}>'.format(
            self.carrier_company_id,
            self.document_type,
            self.status,
        )
