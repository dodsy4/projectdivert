"""Waste models."""

from datetime import datetime
from projectdivert.extensions import db


class WasteRemovalRequest(db.Model):
    __tablename__ = 'waste_removal_requests'

    id = db.Column(db.Integer, primary_key=True)
    requester_name = db.Column(db.String(120), nullable=False)
    requester_email = db.Column(db.String(255), nullable=False)
    material_type = db.Column(db.String(120), nullable=False)
    waste_amount = db.Column(db.Float, nullable=False)
    waste_unit = db.Column(db.String(32), nullable=False)
    pickup_address = db.Column(db.String(255), nullable=False)
    pickup_city = db.Column(db.String(120))
    pickup_county = db.Column(db.String(120))
    pickup_postcode = db.Column(db.String(32), nullable=False)
    scheduled_pickup_at = db.Column(db.DateTime, nullable=False)
    notes = db.Column(db.Text)
    status = db.Column(db.String(32), nullable=False, default='pending')
    assigned_driver_user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        index=True,
    )
    incident_state = db.Column(db.String(32), index=True)
    incident_severity = db.Column(db.String(16), index=True)
    incident_owner_admin_user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        index=True,
    )
    incident_acknowledged_at = db.Column(db.DateTime, index=True)
    incident_resolved_at = db.Column(db.DateTime, index=True)
    incident_notes = db.Column(db.Text)
    incident_updated_at = db.Column(db.DateTime, index=True)
    incident_last_escalation_key = db.Column(db.String(120), index=True)
    incident_last_escalated_at = db.Column(db.DateTime, index=True)
    billing_state = db.Column(db.String(32), index=True)
    billing_reference = db.Column(db.String(120))
    billing_notes = db.Column(db.Text)
    billing_updated_at = db.Column(db.DateTime, index=True)
    billing_updated_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        index=True,
    )
    billing_followup_state = db.Column(db.String(32), index=True)
    billing_followup_notes = db.Column(db.Text)
    billing_followup_updated_at = db.Column(db.DateTime, index=True)
    billing_followup_updated_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        index=True,
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return '<WasteRemovalRequest {} {}>'.format(self.id, self.material_type)


class WasteRequestCommunicationLog(db.Model):
    __tablename__ = 'waste_request_communication_logs'

    id = db.Column(db.Integer, primary_key=True)
    waste_removal_request_id = db.Column(
        db.Integer,
        db.ForeignKey('waste_removal_requests.id'),
        nullable=False,
        index=True,
    )
    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        index=True,
    )
    direction = db.Column(db.String(32), nullable=False, index=True)
    channel = db.Column(db.String(32), nullable=False, index=True)
    subject = db.Column(db.String(255))
    message = db.Column(db.Text, nullable=False)
    outcome = db.Column(db.String(120))
    contact_name = db.Column(db.String(120))
    contact_email = db.Column(db.String(255))
    contact_phone = db.Column(db.String(120))
    customer_visible = db.Column(db.Boolean, nullable=False, default=False, index=True)
    occurred_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return '<WasteRequestCommunicationLog request={} direction={} channel={}>'.format(
            self.waste_removal_request_id,
            self.direction,
            self.channel,
        )


class WasteRemovalMatch(db.Model):
    __tablename__ = 'waste_removal_matches'

    id = db.Column(db.Integer, primary_key=True)
    waste_removal_request_id = db.Column(
        db.Integer,
        db.ForeignKey('waste_removal_requests.id'),
        nullable=False,
        index=True,
    )
    provider_name = db.Column(db.String(255), nullable=False)
    provider_type = db.Column(db.String(120))
    provider_city = db.Column(db.String(120))
    provider_postcode = db.Column(db.String(32))
    provider_latitude = db.Column(db.Float, nullable=False)
    provider_longitude = db.Column(db.Float, nullable=False)
    distance_miles = db.Column(db.Float, nullable=False)
    match_radius_miles = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return '<WasteRemovalMatch request={} provider={}>'.format(
            self.waste_removal_request_id,
            self.provider_name,
        )


class WasteRemovalDispatchOffer(db.Model):
    __tablename__ = 'waste_removal_dispatch_offers'

    id = db.Column(db.Integer, primary_key=True)
    waste_removal_request_id = db.Column(
        db.Integer,
        db.ForeignKey('waste_removal_requests.id'),
        nullable=False,
        index=True,
    )
    provider_name = db.Column(db.String(255), nullable=False)
    provider_type = db.Column(db.String(120))
    provider_city = db.Column(db.String(120))
    provider_postcode = db.Column(db.String(32))
    provider_latitude = db.Column(db.Float, nullable=False)
    provider_longitude = db.Column(db.Float, nullable=False)
    provider_email = db.Column(db.String(255))
    provider_phone = db.Column(db.String(120))
    distance_miles = db.Column(db.Float, nullable=False)
    match_radius_miles = db.Column(db.Float, nullable=False)
    offer_rank = db.Column(db.Integer, nullable=False)
    offer_token = db.Column(db.String(64), nullable=False, unique=True, index=True)
    status = db.Column(db.String(32), nullable=False, default='offered', index=True)
    notified_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    responded_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return '<WasteRemovalDispatchOffer request={} provider={} status={}>'.format(
            self.waste_removal_request_id,
            self.provider_name,
            self.status,
        )


class WasteRemovalVehicleLocation(db.Model):
    __tablename__ = 'waste_removal_vehicle_locations'

    id = db.Column(db.Integer, primary_key=True)
    waste_removal_request_id = db.Column(
        db.Integer,
        db.ForeignKey('waste_removal_requests.id'),
        nullable=False,
        index=True,
    )
    driver_id = db.Column(db.String(120))
    vehicle_id = db.Column(db.String(120))
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    recorded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    source = db.Column(db.String(32), nullable=False, default='mobile')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return '<WasteRemovalVehicleLocation request={} lat={} lon={}>'.format(
            self.waste_removal_request_id,
            self.latitude,
            self.longitude,
        )


class DispatchIncidentEvent(db.Model):
    __tablename__ = 'dispatch_incident_events'

    id = db.Column(db.Integer, primary_key=True)
    waste_removal_request_id = db.Column(
        db.Integer,
        db.ForeignKey('waste_removal_requests.id'),
        nullable=False,
        index=True,
    )
    event_type = db.Column(db.String(64), nullable=False, index=True)
    actor_user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        index=True,
    )
    actor_email = db.Column(db.String(255), index=True)
    source = db.Column(db.String(64), nullable=False, default='system')
    details_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    def __repr__(self):
        return '<DispatchIncidentEvent request={} event={} actor={}>'.format(
            self.waste_removal_request_id,
            self.event_type,
            self.actor_user_id,
        )
