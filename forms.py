from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, SelectField
from wtforms.validators import DataRequired, Optional


class OutputForm(FlaskForm):
    material = StringField('Material', validators=[Optional()])
    city = FloatField('Amount', validators=[Optional()])
    state = SelectField('Unit', choices=[('kg', 'kg'), ('tonne', 'tonne'), ('sqm', 'sqm')], validators=[Optional()])
    address = StringField('Site Address', validators=[Optional()])
    phone = StringField('Traditional Address', validators=[Optional()])
    image_link = StringField('Divert Address', validators=[Optional()])
