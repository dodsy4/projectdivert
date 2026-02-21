from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, FloatField, TextAreaField
from wtforms.validators import DataRequired, NumberRange, URL

COUNTY_CHOICES = [
    'Bath and North East Somerset',
    'Bedfordshire',
    'Berkshire',
    'Bristol',
    'Buckinghamshire',
    'Cambridgeshire',
    'Cheshire',
    'Cornwall',
    'County Durham',
    'Cumbria',
    'Derbyshire',
    'Devon',
    'Dorset',
    'East Riding of Yorkshire',
    'East Sussex',
    'Essex',
    'Gloucestershire',
    'Greater London',
    'Greater Manchester',
    'Hampshire',
    'Herefordshire',
    'Hertfordshire',
    'Isle of Wight',
    'Isles of Scilly',
    'Kent',
    'Lancashire',
    'Leicestershire',
    'Lincolnshire',
    'Merseyside',
    'Norfolk',
    'North Somerset',
    'North Yorkshire',
    'Northamptonshire',
    'Northumberland',
    'Nottinghamshire',
    'Oxfordshire',
    'Rutland',
    'Shropshire',
    'Somerset',
    'South Gloucestershire',
    'South Yorkshire',
    'Staffordshire',
    'Suffolk',
    'Surrey',
    'Tyne & Wear',
    'Warwickshire',
    'West Midlands',
    'West Sussex',
    'West Yorkshire',
    'Wiltshire',
    'Worcestershire',
]

MATERIAL_CHOICES = [
    'AC Unit',
    'Carpet Tiles',
    'Chair',
    'Ceiling Tiles',
    'Cycle Stands',
    'Desk',
    'Drawer',
    'Electric Heater',
    'Fridge',
    'Glass',
    'Glazed Partitions',
    'Kitchen Set',
    'Lockers',
    'Microwave',
    'Paving Slabs',
    'Pedestals',
    'Printer',
    'Rock/Boulders',
    'Power Sockets',
    'Sand',
    'Shelving',
    'Soap Dispenser',
    'Tambour Unit',
    'Task Chair',
    'Waste Paper Bin',
    'Whiteboard',
    'Other',
]

OUTPUT_MATERIAL_CHOICES = [
    'Carpet Tiles',
    'Pallets',
    'Correx',
    'Sand',
    'Glass',
    'Task Chair',
    'Paper and card',
    'Other',
]

WASTE_AMOUNT_UNIT_CHOICES = [
    'Tonnes',
    'Kilograms',
    'Cubic Meters',
    'Bags',
    'Items',
]


class FilterForm(FlaskForm):
    postcode = StringField('postcode', validators=[DataRequired()])
    radius = SelectField('radius', validators=[DataRequired()], choices=['10', '20', '30', '40', '50'])


class BaseCharityForm(FlaskForm):
    name = StringField('name', validators=[DataRequired()])
    reg_num = StringField('reg_num')
    email = StringField('email', validators=[DataRequired()])

    city1 = StringField('city1', validators=[DataRequired()])
    city2 = StringField('city2')
    city3 = StringField('city3')

    address1 = StringField('address1', validators=[DataRequired()])
    address2 = StringField('address2')
    address3 = StringField('address3')

    postcode1 = StringField('postcode1', validators=[DataRequired()])
    postcode2 = StringField('postcode2')
    postcode3 = StringField('postcode3')

    county1 = SelectField('county1', validators=[DataRequired()], choices=COUNTY_CHOICES)
    county2 = SelectField('county2', validators=[DataRequired()], choices=COUNTY_CHOICES)
    county3 = SelectField('county3', validators=[DataRequired()], choices=COUNTY_CHOICES)

    phone = StringField('phone')
    facebook_link = StringField('facebook_link', validators=[URL()])
    linkedin_link = StringField('linkedin_link', validators=[URL()])
    website = StringField('website', validators=[URL()])


class CharityForm1(BaseCharityForm):
    reg_num = StringField('reg_num')


class CharityForm2(BaseCharityForm):
    pass


class CharityForm3(BaseCharityForm):
    pass


class CharityForm4(BaseCharityForm):
    pass


class CharityForm5(BaseCharityForm):
    other = StringField('other', validators=[DataRequired()])


class MaterialForm(FlaskForm):
    waste_stream = SelectField('waste_stream', choices=MATERIAL_CHOICES)
    amount = FloatField('amount', validators=[DataRequired()])
    address = StringField('address')
    city = StringField('city')
    postcode = StringField('postcode')
    county = SelectField('county', validators=[DataRequired()], choices=COUNTY_CHOICES)
    dimensions = StringField('dimensions')
    condition = TextAreaField('condition')
    image_link1 = StringField('image_link1')
    image_link2 = StringField('image_link2')
    image_link3 = StringField('image_link3')


class RequestForm(FlaskForm):
    email = StringField('email', validators=[DataRequired()])
    message = TextAreaField('message', validators=[DataRequired()])


class OutputForm(FlaskForm):
    material = SelectField('material', validators=[DataRequired()], choices=OUTPUT_MATERIAL_CHOICES)
    amount = StringField('amount', validators=[DataRequired()])
    unit = SelectField('unit', validators=[DataRequired()], choices=['Tonnes', 'Square Meters', 'Per Item'])
    traditional_cost = StringField('traditional_cost', validators=[DataRequired()])
    divert_cost = StringField('divert_cost', validators=[DataRequired()])
    site_address = StringField('site_address', validators=[DataRequired()])
    traditional_address = StringField('traditional_address', validators=[DataRequired()])
    divert_address = StringField('divert_address', validators=[DataRequired()])


class WasteRemovalRequestForm(FlaskForm):
    requester_name = StringField('requester_name', validators=[DataRequired()])
    requester_email = StringField('requester_email', validators=[DataRequired()])
    material_type = SelectField('material_type', validators=[DataRequired()], choices=MATERIAL_CHOICES)
    waste_amount = FloatField('waste_amount', validators=[DataRequired(), NumberRange(min=0.01)])
    waste_unit = SelectField('waste_unit', validators=[DataRequired()], choices=WASTE_AMOUNT_UNIT_CHOICES)
    match_radius_miles = FloatField('match_radius_miles', validators=[DataRequired(), NumberRange(min=1, max=500)])
    pickup_address = StringField('pickup_address', validators=[DataRequired()])
    pickup_city = StringField('pickup_city')
    pickup_county = SelectField('pickup_county', choices=COUNTY_CHOICES)
    pickup_postcode = StringField('pickup_postcode', validators=[DataRequired()])
    scheduled_pickup_at = StringField('scheduled_pickup_at', validators=[DataRequired()])
    notes = TextAreaField('notes')
