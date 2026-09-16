"""Charity models."""

from projectdivert.extensions import db


class Charity(db.Model):
    __tablename__ = 'charities'

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(120))
    name = db.Column(db.String(120))
    email = db.Column(db.String(120))
    reg_num = db.Column(db.String(120))
    address1 = db.Column(db.String(120))
    city1 = db.Column(db.String(120))
    county1 = db.Column(db.String(120))
    postcode1 = db.Column(db.String(120))
    address2 = db.Column(db.String(120))
    city2 = db.Column(db.String(120))
    county2 = db.Column(db.String(120))
    postcode2 = db.Column(db.String(120))
    address3 = db.Column(db.String(120))
    city3 = db.Column(db.String(120))
    county3 = db.Column(db.String(120))
    postcode3 = db.Column(db.String(120))
    phone = db.Column(db.String(120))
    facebook_link = db.Column(db.String(120))
    linkedin_link = db.Column(db.String(120))
    website = db.Column(db.String(120))

    def __repr__(self):
        return '<Charity {}>'.format(self.name)
