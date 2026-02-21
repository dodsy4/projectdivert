#----------------------------------------------------------------------------#
# Imports
#----------------------------------------------------------------------------#
import sys
import json
import os
import csv
import uuid
import dateutil.parser
import babel
import requests
from flask import Flask, render_template, request, flash, redirect, url_for
from flask_moment import Moment
from forms import *
import logging
from logging import Formatter, FileHandler
from sqlalchemy import func
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from project_divert_functions import *
import math
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
#----------------------------------------------------------------------------#
# App Config.
#----------------------------------------------------------------------------#
app = Flask(__name__)
app.config.from_object('config')
db = SQLAlchemy(app)
moment = Moment(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login_page'
login_manager.login_message = 'Please log in to continue.'

class c(db.Model):
    __tablename__ = 'c'

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


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120))
    is_active_user = db.Column(db.Boolean, nullable=False, default=True)

    def __repr__(self):
        return '<User {}>'.format(self.email)

    @property
    def is_active(self):
        return self.is_active_user

class m(db.Model):
    __tablename__ = 'm'

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

class output(db.Model):
    __tablename__ = 'output'

    id = db.Column(db.Integer, primary_key=True)
    material = db.Column(db.String(120))
    amount = db.Column(db.String(120))
    unit = db.Column(db.String(120))
    site_address = db.Column(db.String(120))
    traditional_address = db.Column(db.String(120))
    divert_address = db.Column(db.String(120))
    traditional_cost = db.Column(db.String(120))
    divert_cost = db.Column(db.String(120))

    # TODO: implement any missing fields, as a database migration using Flask-Migrate
    def __repr__(self):
        return '<Output {}>'.format(self.material)

class r(db.Model):
    __tablename__ = 'r'
    id = db.Column(db.Integer, primary_key=True)
    mat_id = db.Column(db.Integer, nullable=False)
    e_id = db.Column(db.String(120), nullable=False)
    message = db.Column(db.String(120))

    def __repr__(self):
        return '<Request {}>'.format(self.mat_id)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def _to_int_or_none(value):
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float_or_none(value):
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _require_form_fields(form_data, required_fields):
    """Return stripped field values and raise ValueError for missing required fields."""
    cleaned = {}
    missing = []
    for field in required_fields:
        value = (form_data.get(field) or '').strip()
        cleaned[field] = value
        if not value:
            missing.append(field)
    if missing:
        raise ValueError('Missing required field(s): {}.'.format(', '.join(missing)))
    return cleaned


def _normalize_material_name(value):
    if value is None:
        return ''
    cleaned = str(value).replace('\xa0', ' ').strip().lower()
    return ' '.join(cleaned.split())


def _material_factor_key(frame, material_name):
    target = _normalize_material_name(material_name)
    if not target:
        return None
    for key in frame.index.to_list():
        if _normalize_material_name(key) == target:
            return key
    return None


def _factor_value(frame, row_key, column_name):
    value = frame.loc[row_key, column_name]
    if hasattr(value, 'iloc'):
        value = value.iloc[0]
    return float(value)


def _seed_materials_if_empty():
    try:
        if m.query.first() is not None:
            return

        csv_path = os.path.join(app.root_path, 'material_sheet.csv')
        if not os.path.exists(csv_path):
            app.logger.warning('No material seed file found at %s', csv_path)
            return

        seeded_count = 0
        with open(csv_path, newline='', encoding='utf-8-sig') as handle:
            for row in csv.DictReader(handle):
                waste_stream = (row.get('waste_stream') or '').strip()
                if not waste_stream:
                    continue

                db.session.add(
                    m(
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
            app.logger.info('Seeded %s materials from material_sheet.csv', seeded_count)
    except Exception:
        db.session.rollback()
        app.logger.exception('Failed to seed materials from material_sheet.csv.')


@app.before_request
def ensure_core_tables():
    # Create core tables on first request if missing.
    if getattr(app, '_core_tables_checked', False):
        return
    try:
        db.create_all()
        _seed_materials_if_empty()
        app._core_tables_checked = True
    except Exception:
        app.logger.exception('Failed creating core tables on startup.')
#----------------------------------------------------------------------------#
# Filters.
#----------------------------------------------------------------------------#

def format_datetime(value, format='medium'):
    date = dateutil.parser.parse(value)
    if format == 'full':
        format="EEEE MMMM, d, y 'at' h:mma"
    elif format == 'medium':
        format="EE MM, dd, y h:mma"
    return babel.dates.format_datetime(date, format)

app.jinja_env.filters['datetime'] = format_datetime

ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}
MAX_MATERIAL_IMAGES = 10


def normalize_image_filename(image_ref):
    value = str(image_ref or '').strip()
    if not value:
        return ''
    basename = os.path.basename(value)
    if '.' in basename:
        return basename
    return basename + '.png'


app.jinja_env.filters['image_file'] = normalize_image_filename


def _save_material_image(uploaded_file):
    if not uploaded_file or not uploaded_file.filename:
        return ''

    original_name = secure_filename(uploaded_file.filename)
    _stem, ext = os.path.splitext(original_name)
    ext = ext.lower()

    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError('Only PNG, JPG, JPEG, and WEBP images are supported.')

    unique_name = '{}{}'.format(uuid.uuid4().hex[:12], ext)
    target_dir = os.path.join(app.static_folder, 'img')
    os.makedirs(target_dir, exist_ok=True)
    uploaded_file.save(os.path.join(target_dir, unique_name))
    return unique_name


def _save_material_images(uploaded_files, limit=MAX_MATERIAL_IMAGES):
    saved = []
    for uploaded_file in uploaded_files[:limit]:
        saved_name = _save_material_image(uploaded_file)
        if saved_name:
            saved.append(saved_name)
    return saved


def _send_material_request_email(to_email, subject, text_body, html_body=None):
    provider = (app.config.get('MAIL_PROVIDER') or 'console').strip().lower()

    if provider == 'console':
        app.logger.info('MAIL(console) to=%s subject=%s body=%s', to_email, subject, text_body)
        return True

    if provider == 'sendgrid':
        api_key = app.config.get('SENDGRID_API_KEY', '')
        from_email = app.config.get('MAIL_FROM_EMAIL', 'noreply@example.com')
        if not api_key:
            app.logger.error('SENDGRID_API_KEY missing; email not sent.')
            return False

        payload = {
            'personalizations': [{'to': [{'email': to_email}], 'subject': subject}],
            'from': {'email': from_email},
            'content': [{'type': 'text/plain', 'value': text_body}],
        }
        if html_body:
            payload['content'].append({'type': 'text/html', 'value': html_body})

        try:
            response = requests.post(
                'https://api.sendgrid.com/v3/mail/send',
                headers={
                    'Authorization': 'Bearer {}'.format(api_key),
                    'Content-Type': 'application/json',
                },
                data=json.dumps(payload),
                timeout=15,
            )
            if 200 <= response.status_code < 300:
                return True
            app.logger.error('SendGrid email failed status=%s body=%s', response.status_code, response.text[:500])
            return False
        except Exception:
            app.logger.exception('SendGrid email request failed.')
            return False

    app.logger.error('Unknown MAIL_PROVIDER=%s', provider)
    return False


def _decode_material_images(image_link1, image_link2, image_link3):
    refs = [
        str(image_link1 or '').strip(),
        str(image_link2 or '').strip(),
        str(image_link3 or '').strip(),
    ]
    if not any(refs):
        return []

    combined = ''.join(refs)
    images = []
    if combined.startswith('multi:'):
        payload = combined[len('multi:'):]
        images = [normalize_image_filename(item) for item in payload.split(',') if item.strip()]
    else:
        images = [normalize_image_filename(item) for item in refs if item]

    return images[:MAX_MATERIAL_IMAGES]


def _encode_material_images(image_refs):
    normalized = [normalize_image_filename(item) for item in image_refs if str(item or '').strip()]
    normalized = normalized[:MAX_MATERIAL_IMAGES]
    if not normalized:
        return '', '', ''

    payload = 'multi:' + ','.join(normalized)
    if len(payload) > 360:
        raise ValueError('Image filenames are too long. Please use fewer images or shorter filenames.')

    part1 = payload[:120]
    part2 = payload[120:240] if len(payload) > 120 else ''
    part3 = payload[240:360] if len(payload) > 240 else ''
    return part1, part2, part3


def _serialize_material(material):
    image_links = _decode_material_images(material.image_link1, material.image_link2, material.image_link3)
    return {
        "id": material.id,
        "material": material.waste_stream,
        "amount": material.amount,
        "condition": material.condition,
        "postcode": material.postcode,
        "image_link1": material.image_link1,
        "image_link2": material.image_link2,
        "image_link3": material.image_link3,
        "image_links": image_links,
    }


def _group_materials(materials):
    grouped = {}
    for material in materials:
        city = material.city if material.city else "Unknown"
        county = material.county if material.county else "Unknown"
        key = (city, county)
        grouped.setdefault(key, []).append(_serialize_material(material))

    data = []
    for city, county in sorted(grouped.keys()):
        data.append(
            {
                "city": city,
                "county": county,
                "materials": grouped[(city, county)],
            }
        )
    return data

#----------------------------------------------------------------------------#
# Controllers.
#----------------------------------------------------------------------------#
@app.route('/first', methods=['GET'])
def first_get():
    form = FilterForm()
    return render_template('forms/first.html', form=form)

@app.route('/first', methods=['POST'])
def first_post():
    postcode = request.form.get('postcode', '').strip()
    radius = request.form.get('radius', '').strip()
    if not postcode or not radius:
        flash('Please provide both postcode and radius.')
        return redirect('/first')
    return redirect(f"/materials?postcode={postcode}&radius={radius}")

@app.route('/map')
def map():
    postcode = request.args.get('postcode', '').strip()
    radius_raw = request.args.get('radius', '').strip()
    filter_applied = False

    materials_query = m.query.filter(m.latitude.isnot(None), m.longitude.isnot(None))
    materials_with_coords = materials_query.all()

    if postcode and radius_raw:
        try:
            radius_miles = int(radius_raw)
            if radius_miles <= 0:
                raise ValueError
            endpoint = "http://api.postcodes.io/postcodes/{}".format(postcode)
            resp = requests.get(endpoint, timeout=10)
            payload = resp.json()
            result = payload.get('result')
            if not result:
                raise ValueError

            target_long = result.get('longitude')
            target_lat = result.get('latitude')
            radius_km = radius_miles * 1.60934
            materials_with_coords = materials_query.filter(
                func.acos(
                    func.sin(func.radians(target_lat)) * func.sin(func.radians(m.latitude))
                    + func.cos(func.radians(target_lat))
                    * func.cos(func.radians(m.latitude))
                    * func.cos(func.radians(m.longitude) - (func.radians(target_long)))
                )
                * 6371
                <= radius_km
            ).all()
            filter_applied = True
        except Exception:
            flash('Could not apply postcode/radius map filter. Showing all mapped materials.')

    markers = []
    for material in materials_with_coords:
        image_links = _decode_material_images(material.image_link1, material.image_link2, material.image_link3)
        markers.append(
            {
                "id": material.id,
                "material": material.waste_stream,
                "amount": material.amount,
                "city": material.city,
                "county": material.county,
                "postcode": material.postcode,
                "lat": material.latitude,
                "lng": material.longitude,
                "preview_image": image_links[0] if image_links else '',
            }
        )
    return render_template(
        'pages/map.html',
        markers=markers,
        google_maps_api_key=app.config.get('GOOGLE_MAPS_API_KEY') or globals().get('API_KEY', ''),
        filter_postcode=postcode,
        filter_radius=radius_raw,
        filter_applied=filter_applied,
    )

@app.route('/')
def index():
    return redirect('/materials')

@app.route('/home')
def home():
    return render_template('pages/home.html')

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    setup_form = CharityForm1()

    if current_user.is_authenticated:
        return redirect('/materials')

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()

        if not email or not password:
            flash('Please enter both email and password.')
            return render_template('pages/login.html', form=setup_form), 400

        user = User.query.filter(func.lower(User.email) == email).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash('Invalid email or password.')
            return render_template('pages/login.html', form=setup_form), 401

        login_user(user)
        flash('Logged in successfully.')
        next_url = request.args.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('/materials')

    return render_template('pages/login.html', form=setup_form)


@app.route('/register', methods=['GET', 'POST'])
def register_page():
    if current_user.is_authenticated:
        return redirect('/materials')

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        if not name or not email or not password:
            flash('Please complete all required fields.')
            return render_template('pages/register.html'), 400
        if password != confirm_password:
            flash('Passwords do not match.')
            return render_template('pages/register.html'), 400
        if len(password) < 8:
            flash('Password must be at least 8 characters.')
            return render_template('pages/register.html'), 400
        if User.query.filter(func.lower(User.email) == email).first():
            flash('An account with that email already exists.')
            return render_template('pages/register.html'), 409

        try:
            user = User(
                name=name[:120],
                email=email,
                password_hash=generate_password_hash(password, method='pbkdf2:sha256'),
            )
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash('Account created successfully.')
            return redirect('/materials')
        except Exception:
            db.session.rollback()
            app.logger.exception('Registration failed.')
            flash('Could not create account right now.')
            return render_template('pages/register.html'), 500

    return render_template('pages/register.html')


@app.route('/logout', methods=['POST'])
@login_required
def logout_page():
    logout_user()
    flash('You have been logged out.')
    return redirect('/materials')

@app.route('/output', methods=['GET'])
def create_output_form():
    form = OutputForm()
    return render_template('forms/calculator.html', form=form)

@app.route('/output', methods=['POST'])
def create_output_submission():
    # TODO: insert form data as a new Venue record in the db, instead
    # TODO: modify data to be the data object returned from db insertion
    error=False
    try:
        form = _require_form_fields(
            request.form,
            [
                'material',
                'amount',
                'unit',
                'site_address',
                'traditional_address',
                'divert_address',
                'traditional_cost',
                'divert_cost',
            ],
        )

        material = form['material']
        if material == 'Other':
            custom_material = request.form.get('custom_output_material', '').strip()
            if not custom_material:
                raise ValueError('Please enter a material when selecting Other.')
            material = custom_material[:120]
        amount = form['amount']
        unit = form['unit']
        site_address = form['site_address']
        traditional_address = form['traditional_address']
        divert_address = form['divert_address']
        traditional_cost = form['traditional_cost']
        divert_cost = form['divert_cost']

        g = output(material=material, amount=amount, unit=unit, site_address=site_address, traditional_address=traditional_address, 
                        divert_address=divert_address, traditional_cost=traditional_cost, divert_cost=divert_cost)
        db.session.add(g)
        db.session.commit()
    
    except ValueError as exc:
        error=True
        db.session.rollback()
        flash(str(exc))
    except Exception:
        error=True
        db.session.rollback()
        app.logger.exception('Output submission failed.')

    finally:
        db.session.close()
    
    if error:
        flash('An error occurred. Output for ' + request.form.get('material', 'material')+ ' could not be calculated.')

    if not error:
        flash('Output for ' + material + ' was successfully listed.')
    
    return redirect("/result")

def fun(material, amount, unit, site_address, traditional_address, divert_address, traditional_cost):
    
    if _normalize_material_name(material) == 'carpet tiles':
        if unit == 'Square Meters':
            amount=(amount*4.3)/1000

    reuse_key = _material_factor_key(reuse_offset, material)
    if reuse_key is None:
        raise ValueError('No reuse factor configured for material "{}".'.format(material))
    reuse_factor = _factor_value(reuse_offset, reuse_key, 'Emission Factor (kg CO2 equivalents/ tonne)')
    reuse_embodied_carbon = amount * reuse_factor

    recycle_key = _material_factor_key(recycle_offset, material)
    if recycle_key is not None:
        recycle_column = 'Emission Factor (kg CO2 equivalents/ tonne or sq m)'
        if recycle_column not in recycle_offset.columns:
            recycle_column = 'Emission Factor (kg CO2 equivalents/ tonne)'
        recycle_factor = _factor_value(recycle_offset, recycle_key, recycle_column)
        recycle_embodied_carbon = amount * recycle_factor
    else:
        recycle_embodied_carbon = reuse_embodied_carbon * 0.85

    traditional_distance = numeric_distance(
        traditional_address,
        site_address,
        return_none_on_failure=True,
    )
    divert_distance = numeric_distance(
        divert_address,
        site_address,
        return_none_on_failure=True,
    )
    if traditional_distance is None or divert_distance is None:
        raise ValueError(
            'Could not calculate transport distance because the Google Maps API is unavailable. '
            'Please check API key and billing.'
        )

    mrf_transport_carbon  = traditional_distance * 0.85
    landfill_transport_carbon = mrf_transport_carbon * 1.2
    landfill_monetary_cost = traditional_cost + 114
    mrf_to_reprocessor_cost = traditional_cost
    mrf_to_reprocessor_transport_carbon = mrf_transport_carbon * 1.2
    divert_transport_carbon  = divert_distance * 0.85
        
    return mrf_transport_carbon, landfill_transport_carbon, landfill_monetary_cost, mrf_to_reprocessor_cost, mrf_to_reprocessor_transport_carbon, divert_transport_carbon, reuse_embodied_carbon, recycle_embodied_carbon


@app.route('/result')
def show_output():
  output_query = db.session.query(output).order_by(output.id.desc()).first()
  

  if not output_query: 
    return render_template('errors/404.html')

  try:
    g = fun(
      output_query.material,
      float(output_query.amount),
      output_query.unit,
      output_query.site_address,
      output_query.traditional_address,
      output_query.divert_address,
      float(output_query.traditional_cost),
    )
  except ValueError as exc:
    flash(str(exc))
    return redirect('/output')
  
  mrf_transport_carbon = g[0]
  landfill_transport_carbon = g[1]
  landfill_monetary_cost = g[2]
  mrf_to_reprocessor_cost = g[3]
  mrf_to_reprocessor_transport_carbon = g[4]
  divert_transport_carbon = g[5]
  reuse_embodied_carbon = g[6]
  recycle_embodied_carbon = g[7]

  

  data = {
    "mrf_transport_carbon": mrf_transport_carbon,
    "landfill_transport_carbon": landfill_transport_carbon,
    "landfill_monetary_cost": landfill_monetary_cost,
    "mrf_to_reprocessor_cost": mrf_to_reprocessor_cost,
    "mrf_to_reprocessor_transport_carbon": mrf_to_reprocessor_transport_carbon,
    "mrf_to_reprocessor_embodied_carbon": (recycle_embodied_carbon * 0.7),
    "divert_transport_carbon": divert_transport_carbon,
    "reuse_embodied_carbon": reuse_embodied_carbon,
    "recycle_embodied_carbon": recycle_embodied_carbon,
    "divert_cost": output_query.divert_cost,
    "traditional_cost": output_query.traditional_cost,
    "traditional_carbon": (mrf_transport_carbon - (recycle_embodied_carbon * 0.7)),
    "divert_recycle_total_carbon": (-recycle_embodied_carbon + divert_transport_carbon),
    "divert_reuse_total_carbon": (-reuse_embodied_carbon + divert_transport_carbon),
    "mrf_to_reprocessor_carbon": (mrf_to_reprocessor_transport_carbon - (recycle_embodied_carbon * 0.7))
  }

  return render_template('pages/output.html', output=data)
#  Create Account
#  ----------------------------------------------------------------

def _create_account_submission(account_type):
    error = False
    try:
        form = request.form
        selected_type = form.get('account_type', '').strip()
        if selected_type == 'Other':
            selected_type = (
                form.get('other_description', '').strip()
                or form.get('other_type', '').strip()
                or form.get('other', '').strip()
                or 'Other'
            )
            selected_type = selected_type[:120]
        if not selected_type:
            selected_type = account_type
        if not selected_type:
            selected_type = 'Charity'

        charity = c(
            name=form.get('name'),
            type=selected_type,
            email=form.get('email'),
            reg_num=form.get('reg_num'),
            address1=form.get('address1'),
            city1=form.get('city1'),
            county1=form.get('county1'),
            postcode1=form.get('postcode1'),
            address2=form.get('address2'),
            city2=form.get('city2'),
            county2=form.get('county2'),
            postcode2=form.get('postcode2'),
            address3=form.get('address3'),
            city3=form.get('city3'),
            county3=form.get('county3'),
            postcode3=form.get('postcode3'),
            phone=form.get('phone'),
            facebook_link=form.get('facebook_link'),
            website=form.get('website'),
        )
        db.session.add(charity)
        db.session.commit()
    except Exception:
        error = True
        db.session.rollback()
        app.logger.exception('Account submission failed.')
    finally:
        db.session.close()

    if error:
        flash('Error. Account was not uploaded.')
    else:
        flash('Account was successfully uploaded.')

    return redirect('/first')


@app.route('/submitdetails1', methods=['GET'])
@app.route('/submit_details1', methods=['GET'])
def create_account_form1():
    form = CharityForm1()
    return render_template('forms/new_account.html', form=form)


@app.route('/submit_details1', methods=['POST'])
def create_account_submission1():
    return _create_account_submission('Charity')


@app.route('/submit_details2', methods=['GET'])
def create_account_form2():
    form = CharityForm2()
    return render_template('forms/new_account.html', form=form)


@app.route('/submit_details2', methods=['POST'])
def create_account_submission2():
    return _create_account_submission('Community Group')


@app.route('/submit_details3', methods=['GET'])
def create_account_form3():
    form = CharityForm3()
    return render_template('forms/new_account.html', form=form)


@app.route('/submit_details3', methods=['POST'])
def create_account_submission3():
    return _create_account_submission('Education')


@app.route('/submit_details4', methods=['GET'])
def create_account_form4():
    form = CharityForm4()
    return render_template('forms/new_account.html', form=form)


@app.route('/submit_details4', methods=['POST'])
def create_account_submission4():
    return _create_account_submission('Social Enterprise')


@app.route('/submit_details5', methods=['GET'])
def create_account_form5():
    form = CharityForm5()
    return render_template('forms/new_account_other.html', form=form)


@app.route('/submit_details5', methods=['POST'])
def create_account_submission5():
    return _create_account_submission(request.form.get('other'))



#----------------------------------------------------------------------------#
# Materials Dashboard
#----------------------------------------------------------------------------#
@app.route('/material_input', methods=['GET'])
def create_material_form():
    form = MaterialForm()
    return render_template('forms/new_material.html', form=form)

@app.route('/material_input', methods=['POST'])
def create_material_submission():
    
    error=False
    try:
        form = _require_form_fields(
            request.form,
            ['waste_stream', 'amount', 'county', 'postcode'],
        )

        waste_stream = form['waste_stream']
        if waste_stream == 'Other':
            custom_waste_stream = request.form.get('custom_waste_stream', '').strip()
            if not custom_waste_stream:
                raise ValueError('Please enter a custom material type when selecting Other.')
            waste_stream = custom_waste_stream[:120]
        amount = form['amount']
        address = request.form.get('address', '').strip()
        city = request.form.get('city', '').strip()
        county = form['county']
        postcode = form['postcode']
        endpoint = "http://api.postcodes.io/postcodes/{}".format(postcode)
        response = requests.get(endpoint, timeout=10)
        payload = response.json()
        result = payload.get('result') if isinstance(payload, dict) else None
        if not result:
            raise ValueError('Please enter a valid postcode.')
        longitude = result.get('longitude')
        latitude = result.get('latitude')
        if longitude is None or latitude is None:
            raise ValueError('Please enter a valid postcode.')
        dimensions = request.form.get('dimensions', '').strip()
        condition = request.form.get('condition', '').strip()
        uploaded_images = request.files.getlist('image_files')
        if uploaded_images:
            image_refs = _save_material_images(uploaded_images, limit=MAX_MATERIAL_IMAGES)
        else:
            image_refs = [
                request.form.get('image_link1', '').strip(),
                request.form.get('image_link2', '').strip(),
                request.form.get('image_link3', '').strip(),
            ]

        image_link1, image_link2, image_link3 = _encode_material_images(image_refs)


        charity = m(waste_stream=waste_stream, amount=amount, address=address, city=city, county=county, postcode=postcode, dimensions=dimensions, condition=condition, 
                    image_link1=image_link1, image_link2=image_link2, image_link3=image_link3, longitude=longitude, latitude=latitude)
        
        db.session.add(charity)
        db.session.commit()
    
    except ValueError as exc:
        error=True
        db.session.rollback()
        flash(str(exc))
    except Exception:
        error=True
        db.session.rollback()
        app.logger.exception('Material submission failed.')

    finally:
        db.session.close()
    
    if error:
        flash('Error. Material was not uploaded.')

    if not error:
        flash('Material was successfully uploaded.')
        
    return redirect('/materials')
  

@app.route('/materials')
def materials():
    search_term = request.args.get('search_term', '').strip()
    postcode = request.args.get('postcode', '').strip()
    radius_raw = request.args.get('radius', '').strip()
    filter_applied = False
    materials_data = []
    base_query = m.query

    if search_term:
        base_query = base_query.filter(m.waste_stream.ilike(f'%{search_term}%'))
        filter_applied = True

    if postcode and radius_raw:
        try:
            radius_miles = int(radius_raw)
            if radius_miles <= 0:
                raise ValueError
            endpoint = "http://api.postcodes.io/postcodes/{}".format(postcode)
            resp = requests.get(endpoint, timeout=10)
            payload = resp.json()
            result = payload.get('result')
            if not result:
                raise ValueError

            target_long = result.get('longitude')
            target_lat = result.get('latitude')
            radius_km = radius_miles * 1.60934
            filtered_materials = base_query.filter(
                func.acos(
                    func.sin(func.radians(target_lat)) * func.sin(func.radians(m.latitude))
                    + func.cos(func.radians(target_lat))
                    * func.cos(func.radians(m.latitude))
                    * func.cos(func.radians(m.longitude) - (func.radians(target_long)))
                )
                * 6371
                <= radius_km
            ).all()
            materials_data = [_serialize_material(material) for material in filtered_materials]
            filter_applied = True
        except Exception:
            flash('Could not apply postcode/radius filter. Showing all materials.')

    if not filter_applied:
        all_materials = base_query.all()
        materials_data = [_serialize_material(material) for material in all_materials]

    return render_template(
        'pages/materials.html',
        materials=materials_data,
        search_term=search_term,
        filter_postcode=postcode,
        filter_radius=radius_raw,
        filter_applied=filter_applied,
    )


@app.route('/materials/search', methods=['POST'])
def search_materials():

    search_term = request.form.get('search_term', '')
    search_result = db.session.query(m).filter(m.waste_stream.ilike(f'%{search_term}%')).all()
    data = []

    for result in search_result:
        data.append({
            "id": result.id,
            "name": result.waste_stream,
        })
  
    response={
        "count": len(search_result),
        "data": data
    }
  
    return render_template('pages/search_materials.html', results=response, search_term=request.form.get('search_term', ''))


@app.route('/materials/<int:material_id>')
def show_material(material_id):
  
    material = m.query.get(material_id)

    if not material: 
        return render_template('errors/404.html')

    data = {
        "id": material.id,
        "material": material.waste_stream,
        "amount": material.amount,
        "city": material.city,
        "county": material.county,
        "address": material.address,
        "dimensions": material.dimensions,
        "condition": material.condition,
        "image_link1": material.image_link1,
        "image_link2": material.image_link2,
        "image_link3": material.image_link3,
        "image_links": _decode_material_images(material.image_link1, material.image_link2, material.image_link3),
    }

    return render_template('pages/show_material.html', material=data)


@app.route('/materials_filtered/<string:location_id>')
def show_site_material(location_id):
    all_areas = m.query.filter(m.city == location_id)
    all_areas = m.query.with_entities(func.count(m.id), m.city, m.county).group_by(m.city, m.county).all()
    data = []

    for area in all_areas:
        if area.city == location_id:
            area_projects = m.query.filter_by(county=area.county).filter_by(city=area.city).all()
        
            project_data = []
        
            for material in area_projects:
                project_data.append({
                    "id": material.id,
                    "material": material.waste_stream, 
                    "amount": material.amount,
                    "condition": material.condition,
                    "postcode": material.postcode,
                    })
        
        
            data.append({
                "city": area.city,
                "county": area.county, 
                "materials": project_data
                })

    
    return render_template('pages/materials.html', areas=data)

#  Create Request
#  ----------------------------------------------------------------
@app.route('/material/<int:mat_id>/request', methods=['GET'])
def create_material_request(mat_id):
    form = RequestForm()
    return render_template('forms/new_request.html', form=form)

@app.route('/material/<int:mat_id>/request', methods=['POST'])
def request_material_form(mat_id):

    error=False
    email_sent = False
    try:
        mat_id = mat_id
        material = m.query.get(mat_id)
        if not material:
            return render_template('errors/404.html'), 404

        email = request.form.get('email', '').strip()
        if not email and current_user.is_authenticated:
            email = current_user.email
        if not email:
            raise ValueError('Requester email is required.')

        message = request.form['message']
        
        qui = r(mat_id=mat_id, e_id=email, message=message)
        db.session.add(qui)
        db.session.commit()

        company_email = (app.config.get('REQUEST_NOTIFICATION_EMAIL') or '').strip()
        if company_email:
            base_url = (app.config.get('APP_BASE_URL') or request.url_root.rstrip('/')).rstrip('/')
            listing_url = '{}{}'.format(base_url, url_for('show_material', material_id=mat_id))
            subject = 'New material request: {}'.format(material.waste_stream or 'Material')
            body = (
                'You received a new material request.\n\n'
                'Material: {material}\n'
                'Material ID: {mat_id}\n'
                'Requester Email: {email}\n'
                'Message: {message}\n'
                'Listing URL: {listing_url}\n'
            ).format(
                material=material.waste_stream or 'Material',
                mat_id=mat_id,
                email=email,
                message=message or '(no message)',
                listing_url=listing_url,
            )
            email_sent = _send_material_request_email(company_email, subject, body)
        else:
            app.logger.warning('REQUEST_NOTIFICATION_EMAIL not set; request email notification skipped.')
    
    except ValueError as exc:
        error=True
        db.session.rollback()
        flash(str(exc))
    except Exception:
        error=True
        db.session.rollback()
        app.logger.exception('Material request submission failed.')

    finally:
        db.session.close()
    
    if error:
        flash('Error. Request was not sent.')

    if not error:
        if email_sent:
            flash('Request sent and emailed to the company.')
        else:
            flash('Request saved. Email notification is not configured yet.')
        
    return redirect('/materials')

#  Error Handling and Initializing
#  ----------------------------------------------------------------
@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def server_error(error):
    return render_template('errors/500.html'), 500


if not app.debug:
    file_handler = FileHandler('error.log')
    file_handler.setFormatter(
        Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]')
    )
    app.logger.setLevel(logging.INFO)
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.info('errors')


# Default port:
if __name__ == '__main__':
    app.run()

# Or specify port manually:
'''
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
'''
